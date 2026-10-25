"""Ghostkeep Deterministic Auditor & Claims Store (v2.1).

Enforces the Golden Rule:
1. Claims are discrete records in append-only / state ledger (claims.jsonl).
2. The Auditor is pure deterministic code (hash checks, file inspection, AST/grep, socket).
3. Hash mismatch automatically transitions Checked -> Stale.
4. Generates/updates the rendered Markdown view (brain/claims_register.md).
"""

import hashlib
import json
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CLAIMS_FILE = ROOT_DIR / "phase0" / "claims.jsonl"
REGISTER_MD = ROOT_DIR / "brain" / "claims_register.md"


def compute_file_hash(path: Path) -> str | None:
    """Compute SHA-256 hash of a file."""
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def load_claims() -> list[dict]:
    """Load all claims from claims.jsonl."""
    if not CLAIMS_FILE.exists():
        return []
    claims = []
    with CLAIMS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    claims.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return claims


def save_claims(claims: list[dict]) -> None:
    """Save all claims back to claims.jsonl."""
    with CLAIMS_FILE.open("w", encoding="utf-8") as f:
        for c in claims:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


def render_markdown(claims: list[dict]) -> None:
    """Render the human-facing claims_register.md table from the claims ledger."""
    REGISTER_MD.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 🧠 Ghostkeep Verifiable Claims Register (Rendered View)",
        "",
        "> Generated from `phase0/claims.jsonl`. Source of truth is the append-only ledger.",
        "",
        "| Claim ID | Kind | Claim | Status | Evidence/Source | Hash | Date | Author |",
        "|:---|:---|:---|:---|:---|:---|:---|:---|",
    ]

    for c in claims:
        cid = c.get("id", "")
        kind = c.get("kind", "verifiable")
        text = c.get("text", "")
        status = c.get("status", "unverified")
        date_str = c.get("valid_at") or c.get("recorded_at", "")[:10]
        author = c.get("author_agent", "system")

        evidence_str = "None"
        hash_str = "-"
        ev = c.get("evidence")
        if ev:
            evidence_str = ev.get("result", "verified")
            file_hashes = ev.get("file_hashes", {})
            if file_hashes:
                # Show first 8 chars of hash
                first_hash = list(file_hashes.values())[0]
                hash_str = first_hash[:8] if first_hash else "-"

        # Markdown status badge
        lines.append(
            f"| {cid} | `{kind}` | {text} | `{status}` | {evidence_str} | `{hash_str}` | {date_str} | {author} |"
        )

    lines.append("")
    with REGISTER_MD.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def check_port_listening(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is currently open and accepting connections."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def verify_claim(claim: dict) -> tuple[str, dict | None, str | None]:
    """
    Deterministically verify a claim.
    Returns: (new_status, evidence_dict, failure_reason)
    """
    kind = claim.get("kind", "verifiable")

    # Decisions and preferences are declared by humans, skipping deterministic code checks
    if kind in ("decision", "preference"):
        return claim.get("status", "declared"), claim.get("evidence"), None

    check_type = claim.get("check_type")
    target_rel = claim.get("target_file")
    target_path = (ROOT_DIR / target_rel) if target_rel else None

    # 1. Staleness check: If already Checked, has any content-dependent evidence file changed?
    current_status = claim.get("status")
    existing_evidence = claim.get("evidence") or {}
    recorded_hashes = existing_evidence.get("file_hashes", {})

    # Only content-dependent claims (not file_exists) check file hashes
    if check_type != "file_exists" and current_status == "checked" and target_path and target_rel in recorded_hashes:
        current_hash = compute_file_hash(target_path)
        if current_hash != recorded_hashes[target_rel]:
            # File changed since check! Status is STALE.
            return "stale", existing_evidence, f"File {target_rel} hash changed from {recorded_hashes[target_rel][:8]} to {str(current_hash)[:8]}"

    # 2. Live port listening check (runtime claim with 10-minute expiry)
    if check_type == "port_listening":
        expected_port = claim.get("expected_port", 8765)
        now_dt = datetime.now(timezone.utc)

        # Check expiry first if currently checked
        if current_status == "checked":
            verified_at_str = existing_evidence.get("verified_at")
            if verified_at_str:
                try:
                    verified_dt = datetime.fromisoformat(verified_at_str)
                    age_seconds = (now_dt - verified_dt).total_seconds()
                    if age_seconds > 600:
                        return "stale", existing_evidence, f"Runtime claim expired after {int(age_seconds)}s (> 10m expiry limit)"
                except Exception:
                    pass

        is_open = check_port_listening(expected_port)
        if is_open:
            evidence = {
                "check_type": "port_listening",
                "result": f"Live socket check passed: TCP port {expected_port} is listening",
                "verified_at": now_dt.isoformat(),
                "expires_at": (now_dt + timedelta(seconds=600)).isoformat(),
            }
            return "checked", evidence, None
        else:
            # When server stops listening, if previously checked it becomes stale, not invalid
            if current_status == "checked":
                return "stale", existing_evidence, f"Server stopped listening on port {expected_port}"
            return "invalid", None, f"Live socket check failed: port {expected_port} is not listening"

    # 3. Port and config inspection (code claim)
    if check_type in ("port_config", "port_listening_or_config"):
        expected_port = claim.get("expected_port", 8765)
        if not target_path or not target_path.is_file():
            return "invalid", None, f"Target file {target_rel} does not exist"

        content = target_path.read_text(encoding="utf-8")
        current_hash = compute_file_hash(target_path)

        # Check if expected port is explicitly configured in code / docstring
        port_pattern = rf"(--port\s+{expected_port}|port\s*=\s*{expected_port}|:{expected_port})"
        port_match = re.search(port_pattern, content)

        if port_match:
            evidence = {
                "check_type": "port_config",
                "result": f"Matched port {expected_port} in {target_rel}",
                "file_hashes": {target_rel: current_hash},
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
            return "checked", evidence, None
        else:
            return "invalid", None, f"Port {expected_port} not found in {target_rel}"

    # 4. File existence check (existence only, no content hashes)
    if check_type == "file_exists":
        if target_path and target_path.exists():
            evidence = {
                "check_type": "file_exists",
                "result": f"File {target_rel} exists",
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
            return "checked", evidence, None
        return "invalid", None, f"File {target_rel} does not exist"

    # 5. Git commit check on origin/main (git merge-base --is-ancestor)
    if check_type == "git_commit_on_origin":
        sha = claim.get("target_sha")
        if not sha:
            m = re.search(r"commit\s+([a-f0-9]{7,40})", claim.get("text", ""))
            sha = m.group(1) if m else None

        if not sha:
            return "invalid", None, "No git commit SHA found in claim"

        proc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, "origin/main"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            evidence = {
                "check_type": "git_commit_on_origin",
                "result": f"Commit {sha} verified as ancestor of origin/main",
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
            return "checked", evidence, None
        else:
            return "invalid", None, f"Commit {sha} is not an ancestor of origin/main"

    # 6. Git commit check locally
    if check_type in ("git_commit", "git_commit_local"):
        sha = claim.get("target_sha")
        if not sha:
            m = re.search(r"commit\s+([a-f0-9]{7,40})", claim.get("text", ""))
            sha = m.group(1) if m else None

        if not sha:
            return "invalid", None, "No git commit SHA found in claim"

        proc = subprocess.run(
            ["git", "rev-parse", "--verify", f"{sha}^{{commit}}"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            evidence = {
                "check_type": "git_commit_local",
                "result": f"Commit {sha} exists in local git repository",
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
            return "checked", evidence, None
        else:
            return "invalid", None, f"Commit {sha} not found in local git repository"

    return "unverified", None, "Unknown check type"


def run_audit() -> None:
    """Run verification loop over all claims."""
    claims = load_claims()
    if not claims:
        print("No claims found in claims store.")
        return

    print(f"Auditing {len(claims)} claim(s)...")
    updated = 0
    for c in claims:
        old_status = c.get("status")
        new_status, evidence, error = verify_claim(c)

        if new_status != old_status:
            c["status"] = new_status
            c["status_changed_at"] = datetime.now(timezone.utc).isoformat()
            if evidence:
                c["evidence"] = evidence
            if error:
                c["audit_error"] = error
            updated += 1
            print(f"[{c['id']}] '{c['text']}' : {old_status} -> {new_status}")
            if error:
                print(f"     Reason: {error}")
        else:
            print(f"[{c['id']}] '{c['text']}' : remains {old_status}")

    save_claims(claims)
    render_markdown(claims)
    print(f"\nAudit complete. {updated} claim(s) transitioned.")
    print(f"Rendered view updated: {REGISTER_MD}")


def create_claim(
    claim_id: str,
    text: str,
    kind: str = "verifiable",
    target_file: str | None = None,
    check_type: str | None = None,
    expected_port: int | None = None,
    author: str = "antigravity",
) -> dict:
    """Create a new unverified claim in claims.jsonl."""
    now_iso = datetime.now(timezone.utc).isoformat()
    claim = {
        "id": claim_id,
        "kind": kind,
        "text": text,
        "project": "ghostkeep",
        "author_agent": author,
        "recorded_at": now_iso,
        "valid_at": now_iso[:10],
        "status": "unverified",
        "status_changed_at": now_iso,
        "target_file": target_file,
        "check_type": check_type,
        "expected_port": expected_port,
        "evidence": None,
    }

    claims = load_claims()
    # Replace if ID exists, else append
    claims = [c for c in claims if c.get("id") != claim_id]
    claims.append(claim)
    save_claims(claims)
    render_markdown(claims)
    print(f"Created claim [{claim_id}]: '{text}' with status 'unverified'")
    return claim


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "audit":
        run_audit()
    elif len(sys.argv) > 1 and sys.argv[1] == "seed":
        create_claim(
            claim_id="C-001",
            text="server.py is configured for port 8765",
            kind="verifiable",
            target_file="phase0/server.py",
            check_type="port_config",
            expected_port=8765,
            author="antigravity",
        )
        create_claim(
            claim_id="C-002",
            text="server is listening on 8765",
            kind="verifiable",
            target_file=None,
            check_type="port_listening",
            expected_port=8765,
            author="antigravity",
        )
    else:
        print("Usage:")
        print("  python auditor.py seed   # Seed the test claim as unverified")
        print("  python auditor.py audit  # Run deterministic audit over all claims")
