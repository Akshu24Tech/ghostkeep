"""Build throwaway worlds for evals: a git repo plus fake session logs in each tool's real format.

Formats match files mapped on a real Windows machine (Nov 2026). Every world lives in its own temp dir
and points Ghostkeep at it through env vars, so evals never touch the user's real logs.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from ghostkeep import sources


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


class World:
    def __init__(self, base: Path):
        self.base = base
        self.repo = base / "teamcaptain"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "eval@example.com")
        git(self.repo, "config", "user.name", "eval")
        git(self.repo, "config", "core.autocrlf", "false")
        home = base / "home"
        self.claude = home / ".claude/projects" / sources.claude_slug(self.repo)
        self.ide = home / ".gemini/antigravity/brain"
        self.cli = home / ".gemini/antigravity-cli/brain"
        self.codex = home / ".codex/sessions"
        self.env = {
            "GHOSTKEEP_CLAUDE_DIR": str(home / ".claude/projects"),
            "GHOSTKEEP_ANTIGRAVITY_DIRS": f"antigravity-ide={self.ide};antigravity-cli={self.cli}",
            "GHOSTKEEP_CODEX_DIR": str(self.codex),
        }

    # --- repo ---------------------------------------------------------------------
    def write(self, rel: str, text: str, mode: str = "w", newline: str | None = "\n"):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open(mode, encoding="utf-8", newline=newline) as fh:
            fh.write(text)

    def commit(self, msg: str = "c", date: str = "2026-11-01T00:00:00"):
        git(self.repo, "add", "-A", ":!.ghostkeep")
        if not date.endswith("Z") and "+" not in date[10:]:
            date += "+00:00"  # session logs are UTC; a bare time would be read in the machine's timezone
        env = {**os.environ, "GIT_COMMITTER_DATE": date, "GIT_AUTHOR_DATE": date}
        subprocess.run(["git", "commit", "-qm", msg], cwd=self.repo, check=True, env=env, capture_output=True)

    def head(self) -> str:
        return git(self.repo, "rev-parse", "HEAD").strip()

    # --- session logs -------------------------------------------------------------
    @staticmethod
    def _jsonl(path: Path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    def claude_session(self, sid: str, rows):
        self._jsonl(self.claude / f"{sid}.jsonl", rows)

    def ag_session(self, which: str, sid: str, rows):
        base = self.ide if which == "ide" else self.cli
        self._jsonl(base / sid / ".system_generated/logs/transcript.jsonl", rows)

    def codex_session(self, name: str, rows):
        self._jsonl(self.codex / "2026/11/11" / f"{name}.jsonl", rows)

    def abs(self, rel: str) -> str:
        return str(self.repo / rel)


# --- row builders, one per real log shape ---------------------------------------------

def c_user(text, ts="2026-11-10T15:50:00Z"):
    return {"type": "user", "timestamp": ts, "cwd": "x", "origin": {"kind": "human"},
            "message": {"role": "user", "content": text}}


def c_edit(path, old, new, ts="2026-11-10T15:52:00Z"):
    return {"type": "assistant", "timestamp": ts, "message": {"model": "claude-opus-5", "role": "assistant",
            "content": [{"type": "tool_use", "name": "Edit",
                         "input": {"file_path": path, "old_string": old, "new_string": new}}]}}


def c_write(path, content, ts="2026-11-10T15:52:00Z"):
    return {"type": "assistant", "timestamp": ts, "message": {"model": "claude-opus-5", "role": "assistant",
            "content": [{"type": "tool_use", "name": "Write", "input": {"file_path": path, "content": content}}]}}


def c_say(text, ts="2026-11-10T15:55:00Z"):
    return {"type": "assistant", "timestamp": ts, "message": {"model": "claude-opus-5", "role": "assistant",
            "content": [{"type": "text", "text": text}]}}


def c_interrupt(ts="2026-11-10T15:56:00Z"):
    return {"type": "user", "timestamp": ts, "interruptedMessageId": "m1",
            "message": {"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user]"}]}}


def ag(step_type, ts="2026-11-10T15:30:00Z", status="DONE", **kw):
    return {"step_index": 0, "source": "MODEL", "type": step_type, "status": status, "created_at": ts, **kw}


def ag_user(text, repo, ts="2026-11-10T15:30:00Z"):
    return ag("USER_INPUT", ts=ts, source="USER_EXPLICIT", content=f"<USER_REQUEST>\n{text}\n</USER_REQUEST>\nworkspace {repo}")


def ag_edit(path, target, replacement, ts="2026-11-10T15:31:00Z"):
    return ag("PLANNER_RESPONSE", ts=ts, tool_calls=[{"name": "edit_file", "args": {
        "Path": path, "Target": target, "Replacement": replacement}}])


def ag_write(path, content, ts="2026-11-10T15:31:00Z"):
    return ag("PLANNER_RESPONSE", ts=ts, tool_calls=[{"name": "write_file", "args": {
        "Path": path, "Content": content, "Overwrite": "false"}}])


def ag_say(text, ts="2026-11-10T15:32:00Z"):
    return ag("PLANNER_RESPONSE", ts=ts, content=text)


def cx_meta(repo, commit, ts="2026-11-11T10:00:00Z"):
    return {"timestamp": ts, "type": "session_meta", "payload": {
        "type": "session_meta", "cwd": str(repo), "git": {"commit_hash": commit, "branch": "main"}}}


def cx_user(text, ts="2026-11-11T10:01:00Z"):
    return {"timestamp": ts, "type": "response_item", "payload": {
        "type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}}


def cx_exec(cmd, ts="2026-11-11T10:02:00Z"):
    return {"timestamp": ts, "type": "response_item", "payload": {
        "type": "function_call", "name": "exec_command", "arguments": json.dumps({"cmd": cmd})}}


def cx_say(text, ts="2026-11-11T10:03:00Z"):
    return {"timestamp": ts, "type": "response_item", "payload": {
        "type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}}


def cx_event(kind, ts="2026-11-11T10:04:00Z"):
    return {"timestamp": ts, "type": "event_msg", "payload": {"type": kind}}


@contextmanager
def world():
    base = Path(tempfile.mkdtemp(prefix="gk-eval-"))
    w = World(base)
    saved = {k: os.environ.get(k) for k in w.env}
    os.environ.update(w.env)
    cwd = os.getcwd()
    os.chdir(w.repo)
    try:
        yield w
    finally:
        os.chdir(cwd)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(base, ignore_errors=True)
