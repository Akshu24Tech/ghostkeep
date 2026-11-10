"""ghostkeep: verified handoffs between free AI tools."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, check, gitio, handoff, ledger, sync

PROBLEM = {"mismatch", "orphan", "corrupt"}
MARK = {"verified": "OK ", "uncommitted": "UNC", "mismatch": "BAD", "superseded": "OLD",
        "orphan": "???", "unverified": "...", "corrupt": "ERR"}


def _root() -> Path:
    try:
        return gitio.repo_root(Path.cwd())
    except gitio.GitError:
        sys.exit("ghostkeep: not inside a git repository")


def cmd_init(_: argparse.Namespace) -> int:
    root = _root()
    p = ledger.init(root)
    print(f"Ledger ready: {p.relative_to(root)}")
    print("Tip: commit it to share the history, or add .ghostkeep/ to .gitignore to keep it private.")
    return 0


def cmd_log(a: argparse.Namespace) -> int:
    root = _root()
    if a.tool not in ledger.TOOLS:
        print(f"ghostkeep: unknown tool '{a.tool}'. Use one of: {', '.join(sorted(ledger.TOOLS))}",
              file=sys.stderr)
        return 2
    claim = ledger.Claim(
        tool=a.tool, asked=a.asked, claimed=a.claimed,
        files=[ledger.FileClaim.parse(s) for s in a.file], open=a.open or [],
        model=a.model, session=a.session, source=a.source, base=gitio.head(root),
    )
    ledger.append(root, claim.to_json())
    print(f"Logged {claim.id} ({claim.tool}, {len(claim.files)} file(s)). Status: unverified")
    return 0


def cmd_check(a: argparse.Namespace) -> int:
    root = _root()
    results = check.run(root, write=not a.dry_run)
    if a.json:
        print(json.dumps([{
            "entry": r.entry, "status": r.status,
            "tool": r.claim.tool if r.claim else None,
            "findings": [f.__dict__ for f in r.findings],
        } for r in results], indent=2, ensure_ascii=False))
    else:
        if not results:
            print("Nothing to check: no claims and no uncommitted changes.")
        for r in results:
            who = f"{r.entry} {r.claim.tool}" if r.claim else "no claim"
            print(f"[{MARK.get(r.status, r.status)}] {r.status:<11} {who}")
            if r.claim:
                print(f"      asked:   {r.claim.asked[:100]}")
            for f in r.findings:
                detail = f"expected {f.expected}, actual {f.actual}" if f.expected else f.actual
                print(f"      {f.code:<17} {f.path}  ({detail})")
    return 1 if any(r.status in PROBLEM for r in results) else 0


def cmd_sync(a: argparse.Namespace) -> int:
    root = _root()
    if not ledger.ledger_path(root).exists():
        ledger.init(root)
    rep, new = sync.run(root, days=a.days, write=not a.dry_run)
    print(f"Sessions touching this repo (last {a.days:g} days): {rep.sessions_seen}")
    print(f"  new claims: {rep.claims_added}   decisions/preferences: {rep.decisions_added}   "
          f"unchanged: {rep.skipped_unchanged}   no file edits: {rep.skipped_no_edits}")
    for r in new:
        if r["kind"] == "claim":
            files = ", ".join(f["path"] for f in r["files"])[:90]
            flag = "  [interrupted]" if r.get("interrupted") else ""
            print(f"  + {r['tool']:<16} {r['ts'][:16]}  {files}{flag}")
    return 0


def cmd_handoff(a: argparse.Namespace) -> int:
    root = _root()
    if not ledger.ledger_path(root).exists():
        ledger.init(root)
    if not a.no_sync:
        sync.run(root, days=a.days)
    results = check.run(root)
    text = handoff.build(root, results)
    p = handoff.write(root, text)
    print(text)
    print(f"(written to {p.relative_to(root)})", file=sys.stderr)
    return 0


def cmd_show(a: argparse.Namespace) -> int:
    root = _root()
    records = ledger.read(root)
    status = ledger.latest_status(records)
    for c in ledger.claims(records)[-a.n:]:
        s = status.get(c.id, {}).get("status", "unverified")
        print(f"[{MARK.get(s, s)}] {c.ts}  {c.tool:<16} {s}")
        print(f"      asked:   {c.asked[:100]}")
        print(f"      claimed: {c.claimed[:100]}")
        for f in c.files:
            print(f"      file:    {f.path} {f.expected()}")
        for o in c.open:
            print(f"      open:    {o}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ghostkeep", description=__doc__)
    p.add_argument("--version", action="version", version=f"ghostkeep {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create .ghostkeep/ledger.jsonl").set_defaults(fn=cmd_init)

    lg = sub.add_parser("log", help="record what an agent claims it did")
    lg.add_argument("--tool", required=True)
    lg.add_argument("--asked", required=True, help="the user's request, verbatim")
    lg.add_argument("--claimed", required=True, help="what the agent says it did")
    lg.add_argument("--file", action="append", default=[],
                    help="claimed file, optionally with counts: path:+3-1 (repeatable)")
    lg.add_argument("--open", action="append", help="something still left to do (repeatable)")
    lg.add_argument("--model")
    lg.add_argument("--session")
    lg.add_argument("--source")
    lg.set_defaults(fn=cmd_log)

    ck = sub.add_parser("check", help="verify claims against git (no LLM)")
    ck.add_argument("--json", action="store_true")
    ck.add_argument("--dry-run", action="store_true", help="don't write check records")
    ck.set_defaults(fn=cmd_check)

    sy = sub.add_parser("sync", help="read Claude Code / Antigravity session logs into the ledger")
    sy.add_argument("--days", type=float, default=14)
    sy.add_argument("--dry-run", action="store_true")
    sy.set_defaults(fn=cmd_sync)

    ho = sub.add_parser("handoff", help="sync, check, and write .ghostkeep/HANDOFF.md for the next agent")
    ho.add_argument("--days", type=float, default=14)
    ho.add_argument("--no-sync", action="store_true")
    ho.set_defaults(fn=cmd_handoff)

    sh = sub.add_parser("show", help="recent claims with their latest status")
    sh.add_argument("-n", type=int, default=10)
    sh.set_defaults(fn=cmd_show)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
