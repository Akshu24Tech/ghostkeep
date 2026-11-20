"""`ghostkeep doctor`: prove the pieces are working instead of assuming it. No silent pass.

A reader that quietly finds nothing looks exactly like a project nobody worked on. So for each tool we
count the log files that mention this repo and how many of them we could actually understand. A file
that mentions the repo but yields no prompt and no edit at all means the tool's format probably changed:
that is reported, never skipped.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from . import ledger, setup, sources

OK, WARN, INFO = "ok", "warn", "--"


@dataclass
class Line:
    level: str
    what: str
    msg: str


def _mentions(path: Path, needles: list[str]) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return False
    return any(n in text for n in needles)


# Event types each reader knows. A log made only of these is understood even when it holds no prompt
# (a session opened and closed). One that has JSON lines but none of these is a format we can't read.
KNOWN = {
    "claude-code": {"user", "assistant", "summary", "system", "file-history-snapshot", "attachment"},
    "antigravity-ide": {"USER_INPUT", "PLANNER_RESPONSE", "GENERIC"},
    "antigravity-cli": {"USER_INPUT", "PLANNER_RESPONSE", "GENERIC"},
    "codex": {"session_meta", "response_item", "event_msg", "turn_context"},
}


def _understood(tool: str, path: Path, s) -> bool:
    if s is not None and (s.prompts or s.edits):
        return True
    rows = 0
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(o, dict):
                rows += 1
                if o.get("type") in KNOWN.get(tool, ()):
                    return True
    except OSError:
        return False
    return rows == 0  # an empty log has nothing to misread


def _bad_json(path: Path) -> tuple[int, int]:
    """(bad lines, total lines) for a .jsonl file."""
    bad = total = 0
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            total += 1
            try:
                json.loads(line)
            except json.JSONDecodeError:
                bad += 1
    except OSError:
        pass
    return bad, total


def _tool_line(tool: str, folder: Path, files: list[Path], read, root: Path) -> Line:
    if not folder.is_dir():
        return Line(INFO, tool, f"no log folder at {folder} (not installed, or it moved)")
    if not files:
        return Line(OK, tool, "no sessions for this repo in the time window")
    lost = []
    for p in files:
        try:
            s = read(p)
        except Exception as exc:  # a reader crash is a finding, not a reason to stop the doctor
            lost.append(f"{p.name} ({type(exc).__name__})")
            continue
        if not _understood(tool, p, s):
            lost.append(p.name)
    if lost:
        return Line(WARN, tool, f"{len(lost)} of {len(files)} log(s) for this repo could not be read; "
                                f"the log format may have changed: {', '.join(lost[:3])}")
    return Line(OK, tool, f"{len(files)} session log(s) read")


def check(root: Path, days: float = 14) -> list[Line]:
    since = time.time() - days * 86400
    fresh = lambda p: p.stat().st_mtime >= since  # noqa: E731
    out: list[Line] = []

    d = sources.claude_dir() / sources.claude_slug(root)
    files = sorted(p for p in d.glob("*.jsonl") if fresh(p)) if d.is_dir() else []
    out.append(_tool_line("claude-code", d if d.is_dir() else sources.claude_dir(), files,
                          lambda p: sources.read_claude(p, root), root))

    groups: dict[str, list[Path]] = {}
    for tool, base in sources.antigravity_dirs():  # the IDE has a current and an old folder
        groups.setdefault(tool, []).append(base)
    for tool, bases in groups.items():
        live = [b for b in bases if b.is_dir()]
        hits = [p for b in live for p in b.glob("*/.system_generated/logs/transcript.jsonl")
                if fresh(p) and _mentions(p, [root.name.lower()])]
        out.append(_tool_line(tool, live[0] if live else bases[0], hits,
                              lambda p, t=tool: sources.read_antigravity(p, t, root), root))

    cx = sources.codex_dir()
    needles = [str(root).lower(), json.dumps(str(root))[1:-1].lower()]
    hits = [p for p in cx.glob("*/*/*/rollout-*.jsonl") if fresh(p) and _mentions(p, needles)] if cx.is_dir() else []
    out.append(_tool_line("codex", cx, hits, lambda p: sources.read_codex(p, root), root))
    out.append(Line(INFO, "gemini-cli", "not read yet (its log folder isn't reachable on the machines tested)"))

    lp = ledger.ledger_path(root)
    if lp.exists():
        bad, total = _bad_json(lp)
        out.append(Line(WARN if bad else OK, "ledger",
                        f"{total} records" + (f", {bad} unreadable line(s): run `ghostkeep check`" if bad else "")))
    else:
        out.append(Line(INFO, "ledger", "none yet: `ghostkeep handoff` creates it"))

    st = setup.status(root)
    hooked = [t for t in setup.TOOLS if st[t]["installed"]]
    if not hooked:
        out.append(Line(WARN, "auto-handoff", "no session-start hook, so the next agent only sees HANDOFF.md if you "
                                              "tell it to: run `ghostkeep setup`"))
    for tool in hooked:
        h, name = st[tool], setup.TOOLS[tool][1]
        if h.get("last_run") is None:
            out.append(Line(WARN, "auto-handoff", f"{name} hook installed but has never run: "
                                                  f"start a new {name} session here"))
        elif not h.get("ok", True):
            out.append(Line(WARN, "auto-handoff", f"{name} hook failed on {h['last_run'][:16]}: {h.get('error')}"))
        else:
            out.append(Line(OK, "auto-handoff", f"{name} hook ran {h['last_run'][:16].replace('T', ' ')}"))
    out.append(Line(OK if st["agents-md"]["installed"] else INFO, "AGENTS.md",
                    "has the read-the-handoff block (advice for Codex and others)" if st["agents-md"]["installed"]
                    else "no ghostkeep block (Codex reads AGENTS.md: `ghostkeep setup` adds one)"))
    return out


def problems(lines: list[Line]) -> list[Line]:
    """Warnings worth putting at the top of HANDOFF.md: anything that makes the handoff less complete.
    Setup advice stays in `doctor`, so the handoff doesn't nag."""
    return [ln for ln in lines if ln.level == WARN and ln.what != "auto-handoff"]


def render(root: Path, lines: list[Line]) -> str:
    out = [f"ghostkeep doctor ({root})"]
    out += [f"[{ln.level:<4}] {ln.what:<16} {ln.msg}" for ln in lines]
    return "\n".join(out)
