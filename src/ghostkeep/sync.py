"""Turn on-disk session logs into ledger claims and decisions. Append-only, idempotent."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import decisions, gitio, ledger, sources
from .ledger import Claim, FileClaim, new_id, now


@dataclass
class SyncReport:
    sessions_seen: int = 0
    claims_added: int = 0
    decisions_added: int = 0
    skipped_unchanged: int = 0
    skipped_no_edits: int = 0


def session_to_claim(root: Path, s: sources.Session) -> Claim | None:
    files = [FileClaim(p, a, r) for p, a, r in s.files()]
    if not files and not (s.interrupted and s.prompts):
        return None  # a finished Q&A session; an interrupted one is unfinished work, so keep it
    first = s.prompts[0][1] if s.prompts else "(no prompt found in the session log)"
    last = s.prompts[-1][1] if s.prompts else None
    open_items = []
    if s.interrupted:
        why = f" ({s.status_note})" if s.status_note else ""
        open_items.append(f"Session was interrupted before finishing{why}. "
                          f"Last request: {sources.clip(last or first, 300)}")
    return Claim(
        tool=s.tool, asked=sources.clip(first), claimed=sources.clip(s.final or "(no final summary)"),
        files=files, open=open_items, model=s.model, session=s.session, source=s.source,
        base=s.base or gitio.commit_before(root, s.started), ts=sources.to_local(s.ended) or now(),
        prompts=[sources.clip(p, 300) for _, p in s.prompts[:8]], interrupted=s.interrupted,
        source_rev=s.rev, via="sync",
    )


def run(root: Path, days: float = 14, write: bool = True) -> tuple[SyncReport, list[dict]]:
    records = ledger.read(root)
    seen_revs = {(r.get("session"), r.get("source_rev")) for r in records if r.get("kind") == "claim"}
    seen_dec = {(r.get("session"), r.get("text")) for r in records if r.get("kind") in ("decision", "preference")}
    rep, new = SyncReport(), []
    for s in sources.all_sessions(root, days):
        rep.sessions_seen += 1
        for ts, prompt in s.prompts:
            for kind, sentence in decisions.find(prompt):
                text = sources.clip(sentence, 300)
                if (s.session, text) in seen_dec:
                    continue
                seen_dec.add((s.session, text))
                new.append({"v": ledger.SCHEMA_VERSION, "kind": kind, "id": new_id("d"),
                            "ts": sources.to_local(ts) or now(), "tool": s.tool, "session": s.session, "text": text})
                rep.decisions_added += 1
        if (s.session, s.rev) in seen_revs:
            rep.skipped_unchanged += 1
            continue
        claim = session_to_claim(root, s)
        if claim is None:
            rep.skipped_no_edits += 1
            continue
        new.append(claim.to_json())
        rep.claims_added += 1
    new.sort(key=lambda r: r.get("ts") or "")
    if write:
        for r in new:
            ledger.append(root, r)
    return rep, new
