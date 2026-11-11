"""Thin, read-only wrappers around git. Ghostkeep never writes to git."""
from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def repo_root(start: Path) -> Path:
    return Path(_git(start, "rev-parse", "--show-toplevel").strip())


def head(root: Path) -> str | None:
    try:
        return _git(root, "rev-parse", "HEAD").strip()
    except GitError:
        return None  # repo with no commits yet


def commit_before(root: Path, iso_ts: str | None) -> str | None:
    """The commit HEAD pointed to at `iso_ts` (first-parent history), else current HEAD."""
    if iso_ts:
        try:
            out = _git(root, "rev-list", "-1", "--first-parent", f"--before={iso_ts}", "HEAD").strip()
            if out:
                return out
        except GitError:
            pass
    return head(root)


def branch(root: Path) -> str | None:
    try:
        return _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    except GitError:
        return None


def changed_paths(root: Path) -> dict[str, str]:
    """Paths that differ from HEAD (staged, unstaged or untracked) -> porcelain code."""
    out = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    result: dict[str, str] = {}
    for line in out.splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:]
        if " -> " in path:  # rename: count the new name
            path = path.split(" -> ", 1)[1]
        result[path.strip('"')] = code
    return result


def numstat(root: Path, base: str | None, path: str) -> tuple[int | None, int | None] | None:
    """Lines (added, removed) for `path` between `base` and the working tree.

    Returns None when the file has no change. (None, None) means binary.
    """
    if base is not None:
        out = _git(root, "diff", "--numstat", base, "--", path).strip()
        if out:
            a, r, _ = out.split("\t", 2)
            return (None, None) if a == "-" else (int(a), int(r))
    # Not in the diff: maybe a new untracked file.
    codes = changed_paths(root)
    if codes.get(path) == "??" or (base is None and path in codes):
        return _count_lines(root / path), 0
    return None


def show(root: Path, rev: str | None, path: str) -> str | None:
    """File content at `rev`, or None if it didn't exist there."""
    if rev is None:
        return None
    try:
        return _git(root, "show", f"{rev}:{path}")
    except GitError:
        return None


def last_commit_touching(root: Path, path: str) -> str | None:
    try:
        return _git(root, "log", "-1", "--format=%H", "--", path).strip() or None
    except GitError:
        return None


def is_ancestor(root: Path, older: str, newer: str) -> bool:
    """True when `older` is `newer` or one of its ancestors."""
    proc = subprocess.run(["git", "merge-base", "--is-ancestor", older, newer], cwd=root,
                          capture_output=True, text=True)
    return proc.returncode == 0


def _count_lines(file: Path) -> int | None:
    try:
        data = file.read_bytes()
    except OSError:
        return 0
    if b"\0" in data[:8000]:
        return None  # binary
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)
