#!/usr/bin/env python3
"""
Ghostkeep Unified CLI (Phase 1).

One unified command for:
  - ghostkeep audit    : Run deterministic auditor and render MEMORY.md + claims_register.md
  - ghostkeep extract  : Run claim extractor over new events
  - ghostkeep sync     : Extract new claims -> Run audit -> Render memory (All-in-one pass)
  - ghostkeep status   : Print concise memory statistics
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
PHASE0_DIR = ROOT_DIR / "phase0"
CLAIMS_FILE = PHASE0_DIR / "claims.jsonl"
EVENTS_FILE = PHASE0_DIR / "events.jsonl"
MEMORY_MD = ROOT_DIR / "MEMORY.md"


def run_cmd(cmd: list[str]) -> int:
    """Run a sub-command using Python."""
    res = subprocess.run([sys.executable] + cmd, cwd=str(ROOT_DIR))
    return res.returncode


def cmd_audit():
    """Run deterministic auditor and update MEMORY.md."""
    print("--- [Ghostkeep] Running Deterministic Auditor ---")
    ret = run_cmd(["phase0/auditor.py", "audit"])
    if ret == 0:
        print("\n--- [Ghostkeep] Rendering MEMORY.md ---")
        run_cmd(["phase0/render_memory.py"])
    return ret


def cmd_extract():
    """Run claim extractor over events.jsonl."""
    print("--- [Ghostkeep] Running Claim Extractor ---")
    return run_cmd(["phase0/extractor.py"])


def cmd_sync():
    """Run full sync: Extract -> Audit -> Render."""
    print("==================================================")
    print("  Ghostkeep Memory Pipeline: Full Sync")
    print("==================================================")
    cmd_extract()
    print()
    cmd_audit()
    print("\n[OK] Ghostkeep sync complete. Memory is up-to-date.")


def cmd_status():
    """Display memory statistics."""
    import json
    if not CLAIMS_FILE.exists():
        print("[!] No claims found. Run: python ghostkeep.py sync")
        return

    claims = []
    with CLAIMS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    claims.append(json.loads(line))
                except Exception:
                    pass

    total = len(claims)
    by_status = {}
    by_kind = {}
    for c in claims:
        status = c.get("status", "unknown")
        kind = c.get("kind", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        by_kind[kind] = by_kind.get(kind, 0) + 1

    print("==================================================")
    print(f"  Ghostkeep Memory Status (Total Claims: {total})")
    print("==================================================")
    print("Statuses:")
    for s, count in sorted(by_status.items()):
        badge = "[OK]" if s in ("checked", "declared") else "[!]"
        print(f"  {badge} {s.upper():<12}: {count}")
    print("\nKinds:")
    for k, count in sorted(by_kind.items()):
        print(f"  - {k:<12}: {count}")

    if MEMORY_MD.exists():
        lines = len(MEMORY_MD.read_text(encoding="utf-8").splitlines())
        print(f"\nRendered MEMORY.md size: {lines} lines")


def main():
    parser = argparse.ArgumentParser(description="Ghostkeep Unified Memory Engine")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("sync", help="Extract new events, run audit, and render MEMORY.md")
    subparsers.add_parser("audit", help="Run auditor on claims and render MEMORY.md")
    subparsers.add_parser("extract", help="Extract claims from recent events")
    subparsers.add_parser("status", help="Show current claims and verification stats")

    args = parser.parse_args()

    if not args.command:
        cmd_status()
    elif args.command == "sync":
        cmd_sync()
    elif args.command == "audit":
        cmd_audit()
    elif args.command == "extract":
        cmd_extract()
    elif args.command == "status":
        cmd_status()


if __name__ == "__main__":
    main()
