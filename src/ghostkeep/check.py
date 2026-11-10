"""Deterministic checker: compares what agents claimed with what git shows. No LLM."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import gitio, ledger
from .ledger import LEDGER_DIR, Claim, new_id, now


@dataclass
class Finding:
    path: str
    code: str
    expected: str | None = None
    actual: str | None = None


@dataclass
class Result:
    entry: str | None
    status: str
    findings: list[Finding] = field(default_factory=list)
    claim: Claim | None = None

    def record(self, head: str | None) -> dict:
        return {
            "v": ledger.SCHEMA_VERSION, "kind": "check", "id": new_id("c"), "ts": now(),
            "head": head, "entry": self.entry, "status": self.status,
            "findings": [f.__dict__ for f in self.findings],
        }


def _fmt(added: int | None, removed: int | None) -> str:
    if added is None and removed is None:
        return "binary"
    return f"+{added} -{removed}"


def check_claim(root: Path, claim: Claim, newest_for: dict[str, str], dirty: dict[str, str]) -> Result:
    findings: list[Finding] = []
    any_uncommitted = False
    strict_files = [f for f in claim.files if newest_for.get(f.path) == claim.id]
    if claim.files and not strict_files:
        return Result(claim.id, "superseded", claim=claim)

    for f in strict_files:
        actual = gitio.numstat(root, claim.base, f.path)
        if actual is None:
            findings.append(Finding(f.path, "claimed_not_found", f.expected(), "no change"))
            continue
        a, r = actual
        if a is not None and (
            (f.added is not None and f.added != a) or (f.removed is not None and f.removed != r)
        ):
            findings.append(Finding(f.path, "count_mismatch", f.expected(), _fmt(a, r)))
            continue
        if f.path in dirty:
            any_uncommitted = True
            code = "untracked" if dirty[f.path] == "??" else "not_committed"
            findings.append(Finding(f.path, code, f.expected(), _fmt(a, r)))

    if any(fd.code in ("claimed_not_found", "count_mismatch") for fd in findings):
        status = "mismatch"
    elif any_uncommitted:
        status = "uncommitted"
    else:
        status = "verified"
    return Result(claim.id, status, findings, claim)


def run(root: Path, write: bool = True) -> list[Result]:
    records = ledger.read(root)
    all_claims = ledger.claims(records)
    head = gitio.head(root)
    dirty = {p: c for p, c in gitio.changed_paths(root).items()
             if not p.startswith(LEDGER_DIR + "/")}

    # Newest claim per file is the one checked strictly.
    newest_for: dict[str, str] = {}
    for c in all_claims:
        for f in c.files:
            newest_for[f.path] = c.id

    results = [check_claim(root, c, newest_for, dirty) for c in all_claims]

    # Orphans: working-tree changes that no claim on the current HEAD mentions.
    covered = {f.path for c in all_claims if c.base == head for f in c.files}
    orphans = sorted(p for p in dirty if p not in covered)
    if orphans:
        results.append(Result(None, "orphan", [
            Finding(p, "no_claim", None, "untracked" if dirty[p] == "??" else "modified")
            for p in orphans
        ]))

    corrupt = [r for r in records if r.get("kind") == "corrupt"]
    for r in corrupt:
        results.append(Result(None, "corrupt", [Finding(f"ledger line {r['line']}", "bad_json", None, r["error"])]))

    if write:
        # Append-only, but don't repeat a check whose outcome hasn't changed.
        last = ledger.latest_status(records)
        last_orphan = next((r for r in reversed(records)
                            if r.get("kind") == "check" and r.get("status") == "orphan"), None)
        for res in results:
            if res.status == "corrupt":
                continue
            prev = last.get(res.entry) if res.entry else last_orphan
            same = prev is not None and prev.get("status") == res.status and \
                prev.get("findings") == [f.__dict__ for f in res.findings] and prev.get("head") == head
            if not same:
                ledger.append(root, res.record(head))
    return results
