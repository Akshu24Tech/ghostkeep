"""Deterministic checker: compares what agents claimed with what git shows. No LLM."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import gitio, ledger, sources
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


def _content_delta(root: Path, base: str | None, path: str) -> tuple[int, int] | None:
    """Line counts measured the way claims are measured (splitlines), so a missing newline at the end
    of a file or CRLF vs LF doesn't read as an extra changed line."""
    old = gitio.show(root, base, path) or ""
    try:
        new = (root / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        new = ""
    if old == new:
        return None
    return sources.line_delta(old, new)


def _recreated_after(root: Path, claim: Claim, path: str) -> bool:
    """A deleted file that is back: committed after the session's base, or written after the session ended."""
    last = gitio.last_commit_touching(root, path)
    if last and claim.base and not gitio.is_ancestor(root, last, claim.base):
        return True
    try:
        ended = datetime.fromisoformat(claim.ts.replace("Z", "+00:00")).timestamp()
        return (root / path).stat().st_mtime > ended + 60
    except (ValueError, OSError, AttributeError):
        return False


def _matches(actual: tuple, options: list[tuple]) -> bool:
    a, r = actual
    return any((ea is None or ea == a) and (er is None or er == r) for ea, er in options)


def check_claim(root: Path, claim: Claim, newest_for: dict[str, str], dirty: dict[str, str],
                chain: dict[str, tuple[int, int]] | None = None) -> Result:
    findings: list[Finding] = []
    any_uncommitted = False
    strict_files = [f for f in claim.files if newest_for.get(f.path) == claim.id]
    if not claim.files:
        return Result(claim.id, "no_files", claim=claim)  # interrupted before changing anything
    if not strict_files:
        return Result(claim.id, "superseded", claim=claim)

    for f in strict_files:
        if gitio.outside_git(root, f.path):
            # git can't see this file (.git/hooks, ignored files), so "no change in git" proves nothing.
            # Only say what the disk shows; never call it missing when it's there.
            if (root / f.path).exists():
                findings.append(Finding(f.path, "outside_git", f.expected(), "on disk, git doesn't track it"))
            else:
                findings.append(Finding(f.path, "claimed_not_found", f.expected(), "not on disk"))
            continue
        if f.added == 0 and f.removed is None:  # the session deleted this file
            if (root / f.path).exists():
                if _recreated_after(root, claim, f.path):
                    findings.append(Finding(f.path, "changed_later", "deleted", "re-created after this session"))
                else:
                    findings.append(Finding(f.path, "claimed_not_found", "deleted", "still on disk"))
            elif f.path in dirty:
                any_uncommitted = True
                findings.append(Finding(f.path, "not_committed", "deleted", "deleted"))
            continue
        actual = gitio.numstat(root, claim.base, f.path)
        if actual is None:
            findings.append(Finding(f.path, "claimed_not_found", f.expected(), "no change"))
            continue
        a, r = actual
        # What the file should show: this session's own counts, or, when earlier sessions edited the
        # same uncommitted file from the same commit, the sum of every session's counts.
        options = [(f.added, f.removed)]
        if chain and f.path in chain:
            options.append(chain[f.path])
        if a is not None and not _matches(actual, options):
            alt = _content_delta(root, claim.base, f.path)
            if alt is not None and _matches(alt, options):
                actual, (a, r) = alt, alt
            else:
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


def _chains(all_claims: list[Claim], newest_for: dict[str, str]) -> dict[str, dict[str, tuple[int, int]]]:
    """For the newest claim on each file: the summed counts of every claim on that file made from the
    same base commit, when there is more than one and all of them reported counts."""
    by_id = {c.id: c for c in all_claims}
    out: dict[str, dict[str, tuple[int, int]]] = {}
    for path, newest_id in newest_for.items():
        newest = by_id[newest_id]
        same = [fc for c in all_claims if c.base == newest.base for fc in c.files if fc.path == path]
        if len(same) > 1 and all(fc.added is not None and fc.removed is not None for fc in same):
            out.setdefault(newest_id, {})[path] = (sum(fc.added for fc in same), sum(fc.removed for fc in same))
    return out


def covering_claims(root: Path, claims: list[Claim], results: list[Result],
                    paths) -> dict[str, list[Claim]]:
    """Which claims account for each changed file, newest first.

    A claim accounts for a change when it names the file, its edit is actually on disk, and nobody has
    committed that file since the claim's base commit (so the change on disk is still the one it made).
    """
    gone = {(r.entry, f.path) for r in results for f in r.findings if f.code == "claimed_not_found"}
    out: dict[str, list[Claim]] = {}
    for path in paths:
        last = gitio.last_commit_touching(root, path)
        for c in claims:
            if path not in {f.path for f in c.files} or (c.id, path) in gone:
                continue
            if last is None or c.base is None or gitio.is_ancestor(root, last, c.base):
                out.setdefault(path, []).append(c)
        if path in out:
            out[path].reverse()
    return out


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
    chains = _chains(all_claims, newest_for)

    results = [check_claim(root, c, newest_for, dirty, chains.get(c.id)) for c in all_claims]

    # Orphans: changed files that no claim accounts for.
    covered = covering_claims(root, all_claims, results, dirty)
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
