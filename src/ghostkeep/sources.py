"""Read the session logs that AI tools already keep on disk. No agent cooperation needed.

Formats were mapped from real files on Windows (10 Nov 2026):
- Claude Code:  ~/.claude/projects/<repo-path-slug>/<session>.jsonl
- Antigravity:  ~/.gemini/antigravity/brain/<id>/.system_generated/logs/transcript.jsonl      (IDE agent)
                ~/.gemini/antigravity-cli/brain/<id>/.system_generated/logs/transcript.jsonl  (CLI)
These are internal formats and can change in any update, so every reader is defensive.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath, PurePosixPath

MAX_TEXT = 500

# --- small helpers -----------------------------------------------------------------

_SECRET_RES = [
    re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
               r"|AIza[0-9A-Za-z_-]{30,}|xox[abpr]-[A-Za-z0-9-]{10,}|gsk_[A-Za-z0-9]{20,})"),
    re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"\b[A-Za-z0-9+_-]{40,}={0,2}\b"),
]


def redact(text: str) -> str:
    for rx in _SECRET_RES:
        text = rx.sub("[redacted]", text)
    return text


def clip(text: str, n: int = MAX_TEXT) -> str:
    text = redact(" ".join(text.split()))
    return text if len(text) <= n else text[: n - 1] + "…"


def line_delta(old: str, new: str) -> tuple[int, int]:
    """(added, removed) lines when `old` is replaced by `new`, like git counts them."""
    a, b = old.splitlines(), new.splitlines()
    added = removed = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            removed += i2 - i1
        if tag in ("replace", "insert"):
            added += j2 - j1
    return added, removed


def to_local(ts: str | None) -> str | None:
    """'2026-11-10T15:56:00.123Z' -> local ISO with offset, so ledger times sort and read consistently."""
    if not ts:
        return ts
    from datetime import datetime
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().isoformat(timespec="seconds")
    except ValueError:
        return ts


def count_lines(text: str) -> int:
    return len(text.splitlines())


def relpath(path: str, root: Path) -> str | None:
    """Repo-relative POSIX path, or None if `path` is outside `root`."""
    if not path:
        return None
    p = path.strip().strip('"')
    win = PureWindowsPath(p)
    if win.drive or p.startswith("\\"):
        parts, rparts = win.parts, PureWindowsPath(str(root)).parts
        if not PureWindowsPath(str(root)).drive:  # root is posix (tests on linux)
            return None
        lower = [x.lower() for x in parts]
        rlower = [x.lower() for x in rparts]
        if lower[: len(rlower)] != rlower:
            return None
        return "/".join(parts[len(rparts):]) or None
    pp = PurePosixPath(p.replace("\\", "/"))
    if pp.is_absolute():
        try:
            return pp.relative_to(PurePosixPath(str(root).replace("\\", "/"))).as_posix()
        except ValueError:
            return None
    return pp.as_posix()  # already relative to the repo


# --- the common session shape --------------------------------------------------------

@dataclass
class Edit:
    path: str
    added: int | None
    removed: int | None


@dataclass
class Session:
    tool: str
    session: str
    source: str
    rev: str
    started: str | None = None
    ended: str | None = None
    model: str | None = None
    prompts: list[tuple[str | None, str]] = field(default_factory=list)
    final: str | None = None
    edits: list[Edit] = field(default_factory=list)
    interrupted: bool = False
    status_note: str | None = None
    touches_root: bool = False
    base: str | None = None  # Codex records the exact base commit; others leave it None

    def files(self) -> list[tuple[str, int | None, int | None]]:
        """One entry per file. Counts only when the session made exactly one edit to it."""
        by: dict[str, list[Edit]] = {}
        for e in self.edits:
            by.setdefault(e.path, []).append(e)
        out = []
        for path, es in by.items():
            if len(es) == 1:
                out.append((path, es[0].added, es[0].removed))
            else:
                out.append((path, None, None))
        return out


# --- Claude Code ---------------------------------------------------------------------

def claude_dir() -> Path:
    return Path(os.environ.get("GHOSTKEEP_CLAUDE_DIR", Path.home() / ".claude" / "projects"))


def claude_slug(root: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(root))


def _claude_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(x.get("text", "") for x in content
                         if isinstance(x, dict) and x.get("type") == "text")
    return ""


def read_claude(path: Path, root: Path) -> Session:
    st = path.stat()
    s = Session("claude-code", path.stem, str(path), f"{st.st_size}:{int(st.st_mtime)}")
    s.touches_root = True  # Claude keeps one folder per project, found by its path slug
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        t, ts = o.get("type"), o.get("timestamp")
        if t not in ("user", "assistant"):
            continue
        if ts:
            s.started = s.started or ts
            s.ended = ts
        msg = o.get("message") or {}
        if t == "user":
            if o.get("toolUseResult") is not None:
                continue
            text = _claude_text(msg.get("content")).strip()
            if o.get("interruptedMessageId") or text.startswith("[Request interrupted"):
                s.interrupted = True
                continue
            human = (o.get("origin") or {}).get("kind") == "human" or isinstance(msg.get("content"), str)
            if text and human and not text.startswith("<"):
                s.prompts.append((ts, text))
                s.interrupted = False  # a new prompt after an interruption resumes the work
        else:
            s.model = msg.get("model") or s.model
            for item in msg.get("content") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and item.get("text", "").strip():
                    s.final = item["text"]
                if item.get("type") != "tool_use":
                    continue
                name, inp = item.get("name"), item.get("input") or {}
                rel = relpath(inp.get("file_path") or inp.get("notebook_path") or "", root)
                if not rel:
                    continue
                s.touches_root = True
                if name == "Edit":
                    a, r = line_delta(inp.get("old_string", ""), inp.get("new_string", ""))
                    s.edits.append(Edit(rel, a, r))
                elif name == "MultiEdit":
                    s.edits.append(Edit(rel, None, None))
                elif name == "Write":
                    s.edits.append(Edit(rel, None, None))  # can't tell new vs overwrite from the call
                elif name == "NotebookEdit":
                    s.edits.append(Edit(rel, None, None))
    return s


def claude_sessions(root: Path, since: float) -> list[Session]:
    d = claude_dir() / claude_slug(root)
    if not d.is_dir():
        return []
    return [read_claude(p, root) for p in sorted(d.glob("*.jsonl")) if p.stat().st_mtime >= since]


# --- Antigravity (IDE agent and CLI share one format) ----------------------------------

def antigravity_dirs() -> list[tuple[str, Path]]:
    env = os.environ.get("GHOSTKEEP_ANTIGRAVITY_DIRS")
    if env:  # "tool=path;tool=path"
        return [(t, Path(p)) for t, p in (x.split("=", 1) for x in env.split(";") if "=" in x)]
    g = Path.home() / ".gemini"
    return [("antigravity-ide", g / "antigravity" / "brain"),
            ("antigravity-ide", g / "antigravity-ide" / "brain"),
            ("antigravity-cli", g / "antigravity-cli" / "brain")]


_REQ = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.S)
_PATH_KEYS = ("Path", "TargetFile", "AbsolutePath", "FilePath", "file_path", "path")


def _ag_request(content: str) -> str:
    m = _REQ.search(content or "")
    return (m.group(1) if m else content or "").strip()


def read_antigravity(path: Path, tool: str, root: Path) -> Session:
    st = path.stat()
    sid = path.parents[2].name  # brain/<id>/.system_generated/logs/transcript.jsonl
    s = Session(tool, sid, str(path), f"{st.st_size}:{int(st.st_mtime)}")
    last_status = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        t, ts = o.get("type"), o.get("created_at")
        if ts:
            s.started = s.started or ts
            s.ended = ts
        last_status = o.get("status") or last_status
        if t == "USER_INPUT":
            text = _ag_request(o.get("content", ""))
            if text:
                s.prompts.append((ts, text))
            if str(root).lower() in (o.get("content") or "").lower():
                s.touches_root = True
        elif t == "PLANNER_RESPONSE":
            if (o.get("content") or "").strip() and not o.get("tool_calls"):
                s.final = o["content"]
            truncated = set(o.get("truncated_fields") or [])
            for tc in o.get("tool_calls") or []:
                name, args = (tc.get("name") or "").lower(), tc.get("args") or {}
                if not any(k in name for k in ("edit", "write", "replace", "create_file")):
                    continue
                raw = next((args[k] for k in _PATH_KEYS if args.get(k)), "")
                rel = relpath(str(raw), root)
                if not rel:
                    continue
                s.touches_root = True
                if "Target" in args and "Replacement" in args and not truncated & {"Target", "Replacement"}:
                    a, r = line_delta(str(args["Target"]), str(args["Replacement"]))
                    s.edits.append(Edit(rel, a, r))
                elif "Content" in args and "Content" not in truncated and str(args.get("Overwrite", "")).lower() != "true":
                    s.edits.append(Edit(rel, count_lines(str(args["Content"])), 0))
                else:
                    s.edits.append(Edit(rel, None, None))
    if last_status and last_status != "DONE":
        s.interrupted = True
        s.status_note = f"last step status {last_status}"
    return s


def antigravity_sessions(root: Path, since: float) -> list[Session]:
    out, needle = [], root.name.lower()
    for tool, base in antigravity_dirs():
        if not base.is_dir():
            continue
        for p in base.glob("*/.system_generated/logs/transcript.jsonl"):
            try:
                if p.stat().st_mtime < since:
                    continue
                if needle not in p.read_text(encoding="utf-8", errors="replace").lower():
                    continue  # cheap prefilter
                s = read_antigravity(p, tool, root)
            except OSError:
                continue
            if s.touches_root:
                out.append(s)
    return out


# --- Codex CLI -----------------------------------------------------------------------
# ~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<id>.jsonl (newest) or .jsonl.zst (older).
# session_meta carries cwd + git.commit_hash (the base commit, no git call needed).
# Codex edits via shell (exec_command {"cmd": "..."}), so files are sniffed from the
# command and line counts are usually unknown — the checker verifies changed-vs-git anyway.

def codex_dir() -> Path:
    return Path(os.environ.get("GHOSTKEEP_CODEX_DIR", Path.home() / ".codex" / "sessions"))


# apply_patch headers, and common PowerShell/shell writes to a path.
_CODEX_PATCH = re.compile(r"\*\*\*\s+(?:Update|Add|Delete)\s+File:\s+(.+)")
_CODEX_WRITES = [
    re.compile(r"(?:Set-Content|Out-File|Add-Content)\b[^\n|]*?-Path\s+(?P<p>\"[^\"]+\"|'[^']+'|\S+)", re.I),
    re.compile(r"\b(?:tee|sed\s+-i[^\s]*|dd\s+of=)\s+(?P<p>\"[^\"]+\"|'[^']+'|\S+)"),
    re.compile(r"(?<![>\d])>>?\s*(?P<p>\"[^\"]+\"|'[^']+'|[^\s;|&]+)"),  # redirection to a file
]


def _codex_edits_from_cmd(cmd: str, root: Path) -> list[Edit]:
    edits: list[Edit] = []
    # apply_patch: count +/- lines per file section.
    if "apply_patch" in cmd:
        cur, add, rem = None, 0, 0
        for ln in cmd.splitlines():
            m = _CODEX_PATCH.match(ln.strip())
            if m:
                if cur:
                    edits.append(Edit(cur, add, rem))
                cur, add, rem = relpath(m.group(1).strip(), root), 0, 0
            elif cur and ln[:1] == "+" and not ln.startswith("+++"):
                add += 1
            elif cur and ln[:1] == "-" and not ln.startswith("---"):
                rem += 1
        if cur:
            edits.append(Edit(cur, add, rem))
    if edits:
        return [e for e in edits if e.path]
    # shell writes: path known, counts unknown.
    for rx in _CODEX_WRITES:
        for m in rx.finditer(cmd):
            rel = relpath(m.group("p").strip("\"'"), root)
            if rel and "." in Path(rel).name:  # looks like a file, not a redirect to /dev/null etc.
                edits.append(Edit(rel, None, None))
    return edits


def _codex_text(content) -> str:
    if isinstance(content, list):
        return "\n".join(x.get("text", "") for x in content
                         if isinstance(x, dict) and x.get("type") in ("input_text", "output_text", "text"))
    return content if isinstance(content, str) else ""


def _read_zst(path: Path) -> list[str]:
    try:
        import zstandard
    except ImportError:
        return []  # can't read compressed sessions without the optional dep
    data = zstandard.ZstdDecompressor().decompress(path.read_bytes(), max_output_size=80_000_000)
    return data.decode("utf-8", "replace").splitlines()


def read_codex(path: Path, root: Path) -> Session | None:
    st = path.stat()
    lines = _read_zst(path) if path.suffix == ".zst" else \
        path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return None
    s = Session("codex", path.name, str(path), f"{st.st_size}:{int(st.st_mtime)}")
    had_task = done_task = cwd_match = False
    for line in lines:
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
        ts = o.get("timestamp")
        if ts:
            s.started = s.started or ts
            s.ended = ts
        if o.get("type") == "session_meta":
            cwd = p.get("cwd", "")
            cwd_match = cwd == str(root) or relpath(cwd, root) in ("", ".")
            if cwd_match:
                s.touches_root = True
                s.base = (p.get("git") or {}).get("commit_hash") or s.base
            s.model = p.get("model") or s.model
        elif p.get("type") == "message" and p.get("role") == "user":
            text = _codex_text(p.get("content")).strip()
            if text and not text.startswith("<"):
                s.prompts.append((ts, text))
        elif p.get("type") == "message" and p.get("role") == "assistant":
            text = _codex_text(p.get("content")).strip()
            if text:
                s.final = text
        elif cwd_match and p.get("type") == "function_call" and p.get("name") in ("exec_command", "shell", "local_shell"):
            try:
                a = json.loads(p.get("arguments") or "{}")
            except json.JSONDecodeError:
                a = {}
            cmd = a.get("cmd") or a.get("command") or ""
            if isinstance(cmd, list):
                cmd = " ".join(str(x) for x in cmd)
            s.edits.extend(_codex_edits_from_cmd(cmd, root))
        t = o.get("type")
        if t == "event_msg" and p.get("type") == "task_started":
            had_task = True
        if t == "event_msg" and p.get("type") == "task_complete":
            done_task = True
    if had_task and not done_task:
        s.interrupted = True
        s.status_note = "no task_complete recorded"
    return s


def codex_sessions(root: Path, since: float) -> list[Session]:
    base = codex_dir()
    if not base.is_dir():
        return []
    out, needle = [], str(root).lower()
    for p in base.glob("*/*/*/rollout-*.jsonl*"):
        if p.suffix not in (".jsonl", ".zst"):
            continue
        try:
            if p.stat().st_mtime < since:
                continue
            s = read_codex(p, root)
        except OSError:
            continue
        if s and s.touches_root:
            out.append(s)
    return out


def all_sessions(root: Path, days: float = 14) -> list[Session]:
    since = time.time() - days * 86400
    sessions = claude_sessions(root, since) + antigravity_sessions(root, since) + codex_sessions(root, since)
    seen, unique = set(), []
    for s in sessions:  # the same Antigravity id can appear under two folders
        if (s.tool, s.session) not in seen:
            seen.add((s.tool, s.session))
            unique.append(s)
    return sorted(unique, key=lambda s: s.ended or "")
