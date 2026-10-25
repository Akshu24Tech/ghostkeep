"""Ghostkeep Rule-Based Claim Extractor (Phase 0 v1).

Reads events.jsonl with a persistent cursor and extracts candidate claims
using deterministic rule-based pattern matching (Python standard library only).

Rules:
- USER_INPUT with decision wording -> kind "decision", status "declared"
- USER_INPUT with preference wording -> kind "preference", status "declared"
- RUN_COMMAND with git commit/push exit code 0 -> kind "verifiable", status "unverified"
- CODE_ACTION creating a file -> kind "verifiable", status "unverified" ("<path> exists")

Constraints:
- Extractor only sets "declared" or "unverified". Never checked, invalid or stale.
- Dedupes by normalized text.
- Max 20 new claims per run.
"""

import argparse
import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
EVENTS_FILE = ROOT_DIR / "phase0" / "events.jsonl"
CLAIMS_FILE = ROOT_DIR / "phase0" / "claims.jsonl"
STATE_FILE = ROOT_DIR / "phase0" / ".extractor_state.json"
REGISTER_MD = ROOT_DIR / "brain" / "claims_register.md"

MAX_CLAIMS_PER_RUN = 20

# Decision & Preference Triggers (rule-based v1)
DECISION_PATTERNS = [
    r"\blet'?s\s+(?:use|work)\b",
    r"\bwe\s+will\s+use\b",
    r"\bwe'?ll\s+use\b",
    r"\bdecided\b",
    r"\bdecision\b",
    r"\bdecisions\b",
    r"\binstead\s+of\b",
    r"\bdon'?t\s+(?:use|build)\b",
    r"\bdo\s+not\s+(?:use|invent|change)\b",
    r"\bsupersedes\b",
    r"\bwe\s+should\s+use\b",
    r"\bswitch\s+to\b",
]

PREFERENCE_PATTERNS = [
    r"\balways\b",
    r"\bnever\b",
    r"\bprefer\b",
    r"\bpreference\b",
    r"\bfrom\s+now\s+on\b",
    r"\bonly\s+when\b",
]


def normalize_text(text: str) -> str:
    """Normalize text for deduplication."""
    return re.sub(r"\s+", " ", text.strip().lower())


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_line": 0}


def save_state(state: dict) -> None:
    try:
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def load_existing_claims() -> list[dict]:
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
    with CLAIMS_FILE.open("w", encoding="utf-8") as f:
        for c in claims:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


def render_markdown(claims: list[dict]) -> None:
    """Render brain/claims_register.md from claims ledger."""
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
                first_hash = list(file_hashes.values())[0]
                hash_str = first_hash[:8] if first_hash else "-"
        elif c.get("source_event"):
            evidence_str = f"event:{c['source_event']}"

        lines.append(
            f"| {cid} | `{kind}` | {text} | `{status}` | {evidence_str} | `{hash_str}` | {date_str} | {author} |"
        )

    lines.append("")
    with REGISTER_MD.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def get_next_claim_id(existing_claims: list[dict]) -> int:
    max_id = 0
    for c in existing_claims:
        cid = c.get("id", "")
        m = re.match(r"C-(\d+)", cid)
        if m:
            val = int(m.group(1))
            if val > max_id:
                max_id = val
    return max_id + 1


def clean_statement(sentence: str, max_len: int = 140) -> str:
    """Clean markdown artifacts, bullet prefixes, and trim."""
    s = sentence.strip()
    # Strip leading markdown lists/bullets
    s = re.sub(r"^(\d+\.|\*|-|•)\s*", "", s)
    s = re.sub(r"^[`'\"]+|[`'\"]+$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[:max_len].rsplit(" ", 1)[0] + "..."
    return s


def extract_sentences(text: str) -> list[str]:
    """Split text into sentences and bullet clauses."""
    # Split by newlines, periods followed by space/newline, or semicolons
    raw_parts = re.split(r"(?:\r?\n|(?<=[.!?])\s+|;\s*)", text)
    sentences = []
    for part in raw_parts:
        cleaned = clean_statement(part)
        if len(cleaned) >= 8:
            sentences.append(cleaned)
    return sentences


def extract_candidate_claims(event: dict) -> list[dict]:
    """Apply rule-based extraction patterns to a single event."""
    candidates = []
    event_type = event.get("event")
    summary = event.get("summary") or ""
    source_hash = event.get("dedupe_hash")
    source_ts = event.get("source_ts") or ""
    agent = event.get("agent") or "antigravity"
    project = event.get("project") or "ghostkeep"

    # Rule 1: CODE_ACTION file creation -> "<path> exists" (skip ephemeral scratch/temp files)
    if event_type == "CODE_ACTION":
        # Check for Created file pattern
        m = re.search(r"Created file (?:file:///)?([^\s]+)", summary)
        if m:
            raw_path = urllib.parse.unquote(m.group(1).replace("\\", "/"))
            if "ghostkeep/" in raw_path:
                rel_path = raw_path.split("ghostkeep/")[1]
            elif raw_path.startswith("e:/") or raw_path.startswith("E:/"):
                rel_path = "/".join(raw_path.split("/")[3:])
            else:
                rel_path = raw_path.lstrip("./")

            file_name = Path(rel_path).name
            if not file_name.startswith(("scratch_", "temp_", "tmp_", "_")):
                candidates.append({
                    "kind": "verifiable",
                    "text": f"{rel_path} exists",
                    "status": "unverified",
                    "target_file": rel_path,
                    "check_type": "file_exists",
                    "source_event": source_hash,
                    "source_ts": source_ts,
                    "author_agent": agent,
                    "project": project,
                })

    # Rule 2: RUN_COMMAND git commit / push exited with 0
    elif event_type == "RUN_COMMAND" and "exited with code 0" in summary:
        # Check commit patterns [branch sha] or commit <sha>
        m_commit = re.search(r"\[([a-zA-Z0-9_\-\.\/]+)\s+([a-f0-9]{7,40})\]", summary)
        m_commit2 = re.search(r"commit\s+([a-f0-9]{7,40})", summary)

        sha = None
        if m_commit:
            sha = m_commit.group(2)[:7]
        elif m_commit2:
            sha = m_commit2.group(1)[:7]

        if sha:
            # Check if this same event also shows a push to origin/main
            has_push = bool(re.search(r"(?:->\s*origin/main|pushed\s+to\s+origin/main|main\s*->\s*main|To\s+.*origin)", summary, re.IGNORECASE))
            if has_push:
                candidates.append({
                    "kind": "verifiable",
                    "text": f"commit {sha} exists on origin/main",
                    "status": "unverified",
                    "target_sha": sha,
                    "check_type": "git_commit_on_origin",
                    "source_event": source_hash,
                    "source_ts": source_ts,
                    "author_agent": agent,
                    "project": project,
                })
            else:
                candidates.append({
                    "kind": "verifiable",
                    "text": f"commit {sha} exists locally",
                    "status": "unverified",
                    "target_sha": sha,
                    "check_type": "git_commit_local",
                    "source_event": source_hash,
                    "source_ts": source_ts,
                    "author_agent": agent,
                    "project": project,
                })

    # Rule 3: USER_INPUT decision wording -> kind "decision", status "proposed"
    # Rule 4: USER_INPUT preference wording -> kind "preference", status "proposed"
    elif event_type == "USER_INPUT":
        sentences = extract_sentences(summary)
        for sent in sentences:
            # Check decision triggers
            is_decision = any(re.search(pat, sent, re.IGNORECASE) for pat in DECISION_PATTERNS)
            if is_decision:
                candidates.append({
                    "kind": "decision",
                    "text": sent,
                    "status": "proposed",
                    "check_type": None,
                    "target_file": None,
                    "source_event": source_hash,
                    "source_ts": source_ts,
                    "author_agent": agent,
                    "project": project,
                })
                continue

            # Check preference triggers
            is_preference = any(re.search(pat, sent, re.IGNORECASE) for pat in PREFERENCE_PATTERNS)
            if is_preference:
                candidates.append({
                    "kind": "preference",
                    "text": sent,
                    "status": "proposed",
                    "check_type": None,
                    "target_file": None,
                    "source_event": source_hash,
                    "source_ts": source_ts,
                    "author_agent": agent,
                    "project": project,
                })

    return candidates


def run_extractor(from_start: bool = False, dry_run: bool = False) -> list[dict]:
    if not EVENTS_FILE.exists():
        print(f"Error: {EVENTS_FILE} does not exist.")
        return []

    state = load_state()
    last_line = 0 if from_start else state.get("last_line", 0)

    existing_claims = load_existing_claims()
    seen_normalized = {normalize_text(c.get("text", "")) for c in existing_claims if c.get("text")}

    next_id_num = get_next_claim_id(existing_claims)

    new_claims = []
    processed_lines = 0

    now_iso = datetime.now(timezone.utc).isoformat()
    today_date = now_iso[:10]

    with EVENTS_FILE.open("r", encoding="utf-8", errors="replace") as f:
        for idx, line in enumerate(f):
            if idx < last_line:
                continue

            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            extracted = extract_candidate_claims(event)
            for cand in extracted:
                norm = normalize_text(cand["text"])
                if not norm or norm in seen_normalized:
                    continue

                cid = f"C-{next_id_num:03d}"
                next_id_num += 1
                cand["id"] = cid
                cand["recorded_at"] = now_iso
                cand["valid_at"] = today_date
                cand["evidence"] = None

                new_claims.append(cand)
                seen_normalized.add(norm)

                if len(new_claims) >= MAX_CLAIMS_PER_RUN:
                    break

            processed_lines = idx + 1
            if len(new_claims) >= MAX_CLAIMS_PER_RUN:
                break

    if not dry_run and new_claims:
        all_claims = existing_claims + new_claims
        save_claims(all_claims)
        render_markdown(all_claims)
        state["last_line"] = processed_lines
        save_state(state)
    elif not dry_run:
        state["last_line"] = processed_lines
        save_state(state)

    return new_claims


def declare_claim(text: str) -> dict:
    """Manually declare a decision claim (author: human, source: manual)."""
    existing_claims = load_existing_claims()
    norm = normalize_text(text)
    seen_normalized = {normalize_text(c.get("text", "")) for c in existing_claims if c.get("text")}

    if norm in seen_normalized:
        for c in existing_claims:
            if normalize_text(c.get("text", "")) == norm:
                print(f"Claim already exists [{c.get('id')}]: '{text}'")
                return c

    next_id_num = get_next_claim_id(existing_claims)
    cid = f"C-{next_id_num:03d}"
    now_iso = datetime.now(timezone.utc).isoformat()
    today_date = now_iso[:10]

    claim = {
        "id": cid,
        "kind": "decision",
        "text": text,
        "status": "declared",
        "author": "human",
        "author_agent": "human",
        "source": "manual",
        "source_event": "manual",
        "source_ts": now_iso,
        "recorded_at": now_iso,
        "valid_at": today_date,
        "project": "ghostkeep",
        "evidence": None,
        "declared_by": "human",
        "declared_at": now_iso,
    }

    all_claims = existing_claims + [claim]
    save_claims(all_claims)
    render_markdown(all_claims)
    print(f"Declared new claim [{cid}]: '{text}' (status: declared, author: human, source: manual)")
    return claim


def review_claims(accept_ids: list[str] | None = None, reject_ids: list[str] | None = None) -> None:
    """Interactive review of proposed claims. Press y to declare, n to reject. Never deletes."""
    claims = load_existing_claims()
    proposed = [c for c in claims if c.get("status") == "proposed"]
    if not proposed:
        print("No proposed claims found to review.")
        return

    print(f"=== Reviewing {len(proposed)} proposed claim(s) ===")
    print("Commands: 'y' = declare (declared_by: human), 'n' = reject, 's' = skip, 'q' = quit\n")
    now_iso = datetime.now(timezone.utc).isoformat()
    updated = 0

    accept_set = set(accept_ids or [])
    reject_set = set(reject_ids or [])

    for c in proposed:
        cid = c.get("id")
        kind = c.get("kind")
        text = c.get("text")
        src_hash = c.get("source_event")
        src_ts = c.get("source_ts")

        print(f"[{cid}] Kind: {kind} | Source Event: {src_hash} ({src_ts})")
        print(f"  Source Text: \"{text}\"")

        choice = None
        if cid in accept_set:
            choice = "y"
            print("  Automated input: y")
        elif cid in reject_set:
            choice = "n"
            print("  Automated input: n")
        else:
            try:
                choice = input("  Declare this claim? [y/n/s/q]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nReview interrupted.")
                break

        if choice == "y":
            c["status"] = "declared"
            c["declared_by"] = "human"
            c["status_changed_at"] = now_iso
            c["declared_at"] = now_iso
            updated += 1
            print("  -> Status updated: DECLARED\n")
        elif choice == "n":
            c["status"] = "rejected"
            c["status_changed_at"] = now_iso
            updated += 1
            print("  -> Status updated: REJECTED\n")
        elif choice == "q":
            print("Quitting review.")
            break
        else:
            print("  -> Skipped (remains proposed)\n")

    if updated > 0:
        save_claims(claims)
        render_markdown(claims)
        print(f"Review complete. {updated} claim(s) updated and saved.")
    else:
        print("No claims updated.")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "declare":
        if len(sys.argv) < 3:
            print("Usage: python phase0/extractor.py declare \"<text>\"")
            sys.exit(1)
        declare_claim(sys.argv[2])
        return

    parser = argparse.ArgumentParser(description="Ghostkeep Rule-Based Claim Extractor (Phase 0 v1)")
    parser.add_argument("command", nargs="?", default="extract", choices=["extract", "review", "declare"], help="Command to run ('extract', 'review', or 'declare')")
    parser.add_argument("text", nargs="?", default=None, help="Text for declare command")
    parser.add_argument("--from-start", action="store_true", help="Reprocess events.jsonl from line 0")
    parser.add_argument("--dry-run", action="store_true", help="Extract without persisting to claims.jsonl")
    parser.add_argument("--review", action="store_true", help="Launch interactive review of proposed claims")
    parser.add_argument("--accept", nargs="*", default=None, help="Claim IDs to accept as declared in review")
    parser.add_argument("--reject", nargs="*", default=None, help="Claim IDs to reject in review")
    args = parser.parse_args()

    if args.command == "declare":
        if not args.text:
            print("Usage: python phase0/extractor.py declare \"<text>\"")
            sys.exit(1)
        declare_claim(args.text)
        return

    if args.command == "review" or args.review:
        review_claims(accept_ids=args.accept, reject_ids=args.reject)
        return

    print(f"Running Extractor on: {EVENTS_FILE}")
    new_claims = run_extractor(from_start=args.from_start, dry_run=args.dry_run)
    print(f"Extracted {len(new_claims)} new claim(s).\n")

    for idx, c in enumerate(new_claims, 1):
        cid = c.get("id")
        kind = c.get("kind")
        text = c.get("text")
        status = c.get("status")
    # Print summary statistics across all claims in the store
    all_claims = load_existing_claims()
    from collections import Counter
    kind_counts = Counter(c.get("kind") for c in all_claims)
    status_counts = Counter(c.get("status") for c in all_claims)

    print("========================================")
    print("=== Claim Counts per Kind ===")
    for k, v in sorted(kind_counts.items()):
        print(f"  {k}: {v}")

    print("\n=== Claim Counts per Status ===")
    for s, v in sorted(status_counts.items()):
        print(f"  {s}: {v}")

    proposed = [c for c in all_claims if c.get("status") == "proposed"]
    print(f"\n=== 5 Proposed Claims (out of {len(proposed)}) ===")
    for i, c in enumerate(proposed[:5], 1):
        print(f"[{i}] {c.get('id')} | Kind: {c.get('kind')}")
        print(f"    Claim: \"{c.get('text')}\"")
        print(f"    Source: {c.get('source_event')} ({c.get('source_ts')})")
    print("========================================\n")


if __name__ == "__main__":
    main()
