"""Check "tests pass" claims by running a test command YOU pinned. No LLM.

Agents say "all tests pass" more easily than they run the tests. When a session's final message claims
that, `ghostkeep handoff` runs the pinned command on the current files and puts the real result next to
the claim. Rules (from Baton's L4, adapted):

- Only a command you pinned with `ghostkeep pin-test` ever runs. It lives in .ghostkeep/config.json, which
  stays out of git, so a command written by an agent, a log or the repo can never get run this way.
- "No tests ran" is not a pass. Fewer passing tests than the last run is called out, not called clean.
- The run checks the files as they are NOW, which may include later changes. The handoff says so.
- The session-start hook never runs tests (it has to be quick); it shows the last result, or "not checked".
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from . import gitio, ledger
from .ledger import LEDGER_DIR, new_id, now

CONFIG = "config.json"
DEFAULT_TIMEOUT = 300

_CLAIM = re.compile(
    r"\b(?:all\s+)?(?:the\s+)?(?:unit\s+|integration\s+)?tests?\s+(?:now\s+|still\s+)?(?:all\s+)?"
    r"(?:pass(?:es|ed|ing)?|are\s+(?:all\s+)?(?:passing|green)|succeed(?:ed)?|went\s+green)\b"
    r"|\b\d+\s+(?:tests?\s+)?passed\b|\ball\s+green\b|\btest\s+suite\s+(?:passes|passed|is\s+green)\b", re.I)
_NEG = re.compile(r"\b(?:not|n't|never|no)\b[^.\n]{0,25}$|\bfail"
                  r"|\b(?:make|get|to|will|'ll|should|until|once|if|so|when)\s+(?:the\s+|all\s+)*$", re.I)
_COUNTS = re.compile(r"(\d+)\s+(passed|failed|skipped|errors?|error|xfailed|xpassed|deselected)", re.I)
_UNITTEST = re.compile(r"\bRan\s+(\d+)\s+tests?\b")


def claims_tests(text: str | None) -> bool:
    """True when an agent's message says tests pass. Negated or mixed sentences ("tests don't pass yet",
    "3 passed, 2 failed") don't count: only a plain claim of passing is checked."""
    for sentence in re.split(r"(?<=[.!?\n])\s+", text or ""):
        for m in _CLAIM.finditer(sentence):
            before = sentence[: m.start()]
            if not _NEG.search(before) and "fail" not in sentence.lower():
                return True
    return False


def config_path(root: Path) -> Path:
    return root / LEDGER_DIR / CONFIG


def load_config(root: Path) -> dict:
    p = config_path(root)
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def pin(root: Path, command: str | None, timeout: int = DEFAULT_TIMEOUT) -> None:
    cfg = load_config(root)
    if command:
        cfg["test_command"], cfg["test_timeout"] = command, timeout
    else:
        cfg.pop("test_command", None)
        cfg.pop("test_timeout", None)
    config_path(root).parent.mkdir(exist_ok=True)
    config_path(root).write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def parse(output: str) -> dict:
    """Counts from a test runner's summary (pytest, unittest, jest-like). Empty dict if none found."""
    counts: dict[str, int] = {}
    tail = "\n".join(output.strip().splitlines()[-15:])
    for n, kind in _COUNTS.findall(tail):
        key = kind.lower().rstrip("s") if kind.lower().startswith("error") else kind.lower()
        counts[key] = counts.get(key, 0) + int(n)
    m = _UNITTEST.search(tail)
    if m and "passed" not in counts:
        counts["ran"] = int(m.group(1))
    return counts


def run_pinned(root: Path) -> dict | None:
    cfg = load_config(root)
    cmd = cfg.get("test_command")
    if not cmd:
        return None
    timeout = int(cfg.get("test_timeout") or DEFAULT_TIMEOUT)
    try:
        proc = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace")
        out, code = (proc.stdout or "") + (proc.stderr or ""), proc.returncode
    except subprocess.TimeoutExpired:
        out, code = f"timed out after {timeout}s", None
    counts = parse(out)
    last = next((ln for ln in reversed(out.strip().splitlines()) if ln.strip()), "")[:200]
    return {"command": cmd, "exit": code, "counts": counts, "summary": last}


def verdict(run: dict, previous: dict | None) -> tuple[bool, str]:
    """(passed, why). A pass needs exit 0 AND at least one test that ran."""
    c, code = run.get("counts", {}), run.get("exit")
    if code is None:
        return False, run.get("summary") or "timed out"
    if code != 0:
        bad = ", ".join(f"{c[k]} {k}" for k in ("failed", "error") if c.get(k))
        if bad:
            return False, f"exit {code}, {bad}"
        # No test counts: the command itself probably didn't run (wrong Python, missing package). Say why.
        return False, f"exit {code}, the command itself failed: {run.get('summary') or 'no output'}"
    ran = c.get("passed", 0) + c.get("ran", 0)
    if ran == 0:
        return False, "exit 0 but no tests ran"
    prev = (previous or {}).get("counts", {})
    prev_ran = prev.get("passed", 0) + prev.get("ran", 0)
    if prev_ran and ran < prev_ran:
        return False, f"{ran} passed, fewer than last run ({prev_ran})"
    return True, f"{ran} passed" + (f", {c['skipped']} skipped" if c.get("skipped") else "")


def runs(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("kind") == "test_run"]


def run(root: Path) -> dict | None:
    """If the newest test claim hasn't been checked on the current HEAD and files, run the pinned command
    once and append the result to the ledger. Returns the new record, or None."""
    records = ledger.read(root)
    claim = next((c for c in reversed(ledger.claims(records)) if c.tests_claimed), None)
    if claim is None:
        return None
    state = f"{gitio.head(root)}|{sorted(gitio.changed_paths(root).items())}"
    if any(r.get("claim") == claim.id and r.get("state") == state for r in runs(records)):
        return None  # already checked this claim on exactly these files
    res = run_pinned(root)
    if res is None:
        return None
    prev = next((r for r in reversed(runs(records)) if r.get("exit") == 0), None)
    ok, why = verdict(res, prev)
    rec = {"v": ledger.SCHEMA_VERSION, "kind": "test_run", "id": new_id("t"), "ts": now(), "claim": claim.id,
           "state": state, **res, "ok": ok, "why": why}
    ledger.append(root, rec)
    return rec
