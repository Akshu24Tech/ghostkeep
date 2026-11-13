"""The append-only ledger: .ghostkeep/ledger.jsonl."""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

LEDGER_DIR = ".ghostkeep"
LEDGER_FILE = "ledger.jsonl"
SCHEMA_VERSION = 1
TOOLS = {
    "claude-code", "antigravity-cli", "antigravity-ide", "codex",
    "gemini-cli", "browser", "manual",
}


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def ledger_path(root: Path) -> Path:
    return root / LEDGER_DIR / LEDGER_FILE


@dataclass
class FileClaim:
    path: str
    added: int | None = None
    removed: int | None = None

    @classmethod
    def parse(cls, spec: str) -> "FileClaim":
        """'docs/a.md', 'docs/a.md:+3', 'docs/a.md:+3-1'."""
        path, sep, counts = spec.rpartition(":")
        if not sep or not counts or counts[0] not in "+-" or len(path) <= 1:
            return cls(path=spec.replace("\\", "/"))
        added = removed = None
        num, sign = "", ""
        for ch in counts + "\0":
            if ch in "+-\0":
                if sign == "+" and num:
                    added = int(num)
                elif sign == "-" and num:
                    removed = int(num)
                sign, num = ch, ""
            elif ch.isdigit():
                num += ch
            else:
                return cls(path=spec.replace("\\", "/"))
        return cls(path=path.replace("\\", "/"), added=added, removed=removed)

    def expected(self) -> str:
        if self.added is None and self.removed is None:
            return "changed"
        if self.added == 0 and self.removed is None:
            return "deleted"
        return f"+{self.added if self.added is not None else '?'} -{self.removed if self.removed is not None else '?'}"


@dataclass
class Claim:
    tool: str
    asked: str
    claimed: str
    files: list[FileClaim]
    open: list[str] = field(default_factory=list)
    model: str | None = None
    session: str | None = None
    source: str | None = None
    base: str | None = None
    id: str = field(default_factory=lambda: new_id("e"))
    ts: str = field(default_factory=now)
    prompts: list[str] = field(default_factory=list)
    interrupted: bool = False
    source_rev: str | None = None
    via: str = "manual"  # "manual" (ghostkeep log) or "sync" (read from a session log)

    def to_json(self) -> dict:
        return {
            "v": SCHEMA_VERSION, "kind": "claim", "id": self.id, "ts": self.ts,
            "tool": self.tool, "model": self.model, "session": self.session,
            "source": self.source, "source_rev": self.source_rev, "via": self.via,
            "asked": self.asked, "prompts": self.prompts, "claimed": self.claimed,
            "files": [f.__dict__ for f in self.files], "open": self.open,
            "interrupted": self.interrupted, "base": self.base,
        }

    @classmethod
    def from_json(cls, d: dict) -> "Claim":
        return cls(
            tool=d["tool"], asked=d["asked"], claimed=d["claimed"],
            files=[FileClaim(**f) for f in d.get("files", [])],
            open=d.get("open", []), model=d.get("model"), session=d.get("session"),
            source=d.get("source"), base=d.get("base"), id=d["id"], ts=d["ts"],
            prompts=d.get("prompts", []), interrupted=d.get("interrupted", False),
            source_rev=d.get("source_rev"), via=d.get("via", "manual"),
        )


def init(root: Path) -> Path:
    p = ledger_path(root)
    p.parent.mkdir(exist_ok=True)
    p.touch(exist_ok=True)
    # Keep .ghostkeep/ out of git without touching the project's own .gitignore: the ledger quotes your
    # messages, and a stranger's first `git add .` shouldn't publish it.
    ign = p.parent / ".gitignore"
    if not ign.exists():
        ign.write_text("# created by ghostkeep: keep this folder out of git\n*\n", encoding="utf-8")
    return p


def append(root: Path, record: dict) -> None:
    p = ledger_path(root)
    if not p.exists():
        raise FileNotFoundError(f"No ledger at {p}. Run `ghostkeep init` first.")
    with p.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read(root: Path) -> list[dict]:
    """All records, oldest first. Bad lines are reported, never silently dropped."""
    p = ledger_path(root)
    if not p.exists():
        return []
    records = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            records.append({"kind": "corrupt", "line": n, "error": str(exc)})
    return records


def claims(records: list[dict]) -> list[Claim]:
    return [Claim.from_json(r) for r in records if r.get("kind") == "claim"]


def latest_status(records: list[dict]) -> dict[str, dict]:
    """Claim id -> its most recent check record."""
    out: dict[str, dict] = {}
    for r in records:
        if r.get("kind") == "check" and r.get("entry"):
            out[r["entry"]] = r
    return out
