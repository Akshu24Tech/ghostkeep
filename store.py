"""
Ghostkeep — provenance-aware memory store.

Design principles (the whole point of this project):
1. Plain files are the source of truth. No vector DB, no embeddings required
   to trust a fact. JSON is human-readable and git-diffable on purpose.
2. Every fact carries WHERE it came from (source_agent, source_session_id),
   HOW confident the writer was, and WHAT it was derived from (if anything).
   That answers "why is this fact what it is" — the thing generic memory
   tools (Mem0, Supermemory, Echo, etc.) don't give you.
3. Conflicting facts are never silently overwritten. They sit in a conflict
   queue until something explicitly resolves them, and the resolution itself
   is logged as a provenance event — so the audit trail never has a gap.

This file has zero framework dependencies on purpose — you can import and
use MemoryStore directly from a script, a notebook, or wrap it in anything
(MCP server, FastAPI, CLI). server.py wraps it as an MCP server.
"""

from __future__ import annotations

import json
import uuid
import difflib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class Fact:
    id: str
    content: str
    source_agent: str          # e.g. "claude-chat", "gemini-cli", "finagent"
    source_session_id: str     # traceable back to the conversation/run that wrote it
    confidence: float          # 0.0–1.0 — how sure the writing agent was
    tags: list[str] = field(default_factory=list)
    derived_from: Optional[str] = None   # fact id this was inferred from, if any
    created_at: str = field(default_factory=_now)
    superseded_by: Optional[str] = None  # set when resolved into another fact
    status: str = "active"     # active | superseded | conflicted

    def to_dict(self):
        return asdict(self)


@dataclass
class ProvenanceEvent:
    id: str
    fact_id: str
    event_type: str            # created | conflict_detected | resolved
    detail: str
    actor: str                 # who/what performed this event
    created_at: str = field(default_factory=_now)

    def to_dict(self):
        return asdict(self)


@dataclass
class Conflict:
    id: str
    fact_id_a: str
    fact_id_b: str
    detected_at: str = field(default_factory=_now)
    resolved: bool = False
    resolution: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None

    def to_dict(self):
        return asdict(self)


SIMILARITY_THRESHOLD = 0.72  # naive text-overlap trigger for "these facts might clash"


class MemoryStore:
    """
    File-backed store. Layout under root_dir:
        facts.json        -- list of Fact
        conflicts.json     -- list of Conflict
        provenance.jsonl   -- append-only log of ProvenanceEvent (audit trail)
    """

    def __init__(self, root_dir: str | Path):
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.facts_path = self.root / "facts.json"
        self.conflicts_path = self.root / "conflicts.json"
        self.provenance_path = self.root / "provenance.jsonl"
        if not self.facts_path.exists():
            self._write_json(self.facts_path, [])
        if not self.conflicts_path.exists():
            self._write_json(self.conflicts_path, [])
        if not self.provenance_path.exists():
            self.provenance_path.write_text("")

    # ---------- low-level IO ----------

    @staticmethod
    def _write_json(path: Path, data):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    @staticmethod
    def _read_json(path: Path):
        return json.loads(path.read_text() or "[]")

    def _log_event(self, fact_id: str, event_type: str, detail: str, actor: str):
        event = ProvenanceEvent(
            id=_new_id("evt"), fact_id=fact_id, event_type=event_type,
            detail=detail, actor=actor,
        )
        with self.provenance_path.open("a") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return event

    def _all_facts(self) -> list[dict]:
        return self._read_json(self.facts_path)

    def _save_facts(self, facts: list[dict]):
        self._write_json(self.facts_path, facts)

    def _all_conflicts(self) -> list[dict]:
        return self._read_json(self.conflicts_path)

    def _save_conflicts(self, conflicts: list[dict]):
        self._write_json(self.conflicts_path, conflicts)

    # ---------- public API (mirrors the MCP tool surface) ----------

    def add_memory(
        self,
        content: str,
        source_agent: str,
        source_session_id: str,
        confidence: float = 0.8,
        tags: Optional[list[str]] = None,
        derived_from: Optional[str] = None,
    ) -> dict:
        fact = Fact(
            id=_new_id("fact"),
            content=content,
            source_agent=source_agent,
            source_session_id=source_session_id,
            confidence=max(0.0, min(1.0, confidence)),
            tags=tags or [],
            derived_from=derived_from,
        )
        facts = self._all_facts()
        facts.append(fact.to_dict())
        self._save_facts(facts)
        self._log_event(fact.id, "created", f"written by {source_agent}", source_agent)

        conflict = self._detect_conflict(fact, facts)
        if conflict:
            self._log_event(fact.id, "conflict_detected",
                             f"overlaps with {conflict['fact_id_a'] if conflict['fact_id_b']==fact.id else conflict['fact_id_b']}",
                             "system")
        return fact.to_dict()

    def _detect_conflict(self, new_fact: Fact, facts: list[dict]) -> Optional[dict]:
        """
        Naive same-topic-different-content detector: flags two ACTIVE facts
        from different source_agents whose text overlaps a lot but isn't
        identical. Good enough as a v1 signal — swap in an embedding
        similarity check later without touching the rest of the system.
        """
        for other in facts:
            if other["id"] == new_fact.id or other["status"] != "active":
                continue
            if other["source_agent"] == new_fact.source_agent:
                continue
            ratio = difflib.SequenceMatcher(
                None, other["content"].lower(), new_fact.content.lower()
            ).ratio()
            if SIMILARITY_THRESHOLD <= ratio < 0.97:
                conflicts = self._all_conflicts()
                c = Conflict(id=_new_id("conf"), fact_id_a=other["id"], fact_id_b=new_fact.id)
                conflicts.append(c.to_dict())
                self._save_conflicts(conflicts)
                # mark both facts conflicted so search can surface that
                facts_list = self._all_facts()
                for f in facts_list:
                    if f["id"] in (other["id"], new_fact.id):
                        f["status"] = "conflicted"
                self._save_facts(facts_list)
                return c.to_dict()
        return None

    def search_memory(
        self,
        query: str,
        min_confidence: float = 0.0,
        source_agent: Optional[str] = None,
        include_superseded: bool = False,
        limit: int = 10,
    ) -> list[dict]:
        query_l = query.lower()
        results = []
        for f in self._all_facts():
            if f["confidence"] < min_confidence:
                continue
            if source_agent and f["source_agent"] != source_agent:
                continue
            if not include_superseded and f["status"] == "superseded":
                continue
            score = difflib.SequenceMatcher(None, query_l, f["content"].lower()).ratio()
            if query_l in f["content"].lower():
                score = max(score, 0.9)
            if score > 0.15:
                results.append((score, f))
        results.sort(key=lambda pair: (pair[0], pair[1]["confidence"]), reverse=True)
        return [f for _, f in results[:limit]]

    def get_provenance(self, fact_id: str) -> dict:
        fact = next((f for f in self._all_facts() if f["id"] == fact_id), None)
        if not fact:
            return {"error": f"no fact with id {fact_id}"}
        events = []
        with self.provenance_path.open() as fh:
            for line in fh:
                if not line.strip():
                    continue
                e = json.loads(line)
                if e["fact_id"] == fact_id:
                    events.append(e)
        chain = []
        cursor = fact
        while cursor:
            chain.append(cursor)
            if cursor.get("derived_from"):
                cursor = next((f for f in self._all_facts() if f["id"] == cursor["derived_from"]), None)
            else:
                cursor = None
        return {"fact": fact, "events": events, "derivation_chain": chain}

    def list_conflicts(self, include_resolved: bool = False) -> list[dict]:
        conflicts = self._all_conflicts()
        if not include_resolved:
            conflicts = [c for c in conflicts if not c["resolved"]]
        facts_by_id = {f["id"]: f for f in self._all_facts()}
        enriched = []
        for c in conflicts:
            enriched.append({
                **c,
                "fact_a": facts_by_id.get(c["fact_id_a"]),
                "fact_b": facts_by_id.get(c["fact_id_b"]),
            })
        return enriched

    def resolve_conflict(
        self,
        conflict_id: str,
        resolution: str,          # "keep_a" | "keep_b" | "merge:<new text>"
        resolved_by: str,
    ) -> dict:
        conflicts = self._all_conflicts()
        conflict = next((c for c in conflicts if c["id"] == conflict_id), None)
        if not conflict:
            return {"error": f"no conflict with id {conflict_id}"}

        facts = self._all_facts()
        by_id = {f["id"]: f for f in facts}
        a, b = by_id.get(conflict["fact_id_a"]), by_id.get(conflict["fact_id_b"])

        if resolution == "keep_a" and a and b:
            b["status"] = "superseded"
            b["superseded_by"] = a["id"]
            a["status"] = "active"
        elif resolution == "keep_b" and a and b:
            a["status"] = "superseded"
            a["superseded_by"] = b["id"]
            b["status"] = "active"
        elif resolution.startswith("merge:") and a and b:
            merged_text = resolution.split("merge:", 1)[1].strip()
            merged = Fact(
                id=_new_id("fact"),
                content=merged_text,
                source_agent=f"merge({a['source_agent']}+{b['source_agent']})",
                source_session_id=resolved_by,
                confidence=max(a["confidence"], b["confidence"]),
                derived_from=a["id"],
            )
            facts.append(merged.to_dict())
            a["status"] = "superseded"
            a["superseded_by"] = merged.id
            b["status"] = "superseded"
            b["superseded_by"] = merged.id
        else:
            return {"error": "resolution must be 'keep_a', 'keep_b', or 'merge:<text>'"}

        self._save_facts(facts)
        conflict["resolved"] = True
        conflict["resolution"] = resolution
        conflict["resolved_by"] = resolved_by
        conflict["resolved_at"] = _now()
        self._save_conflicts(conflicts)
        self._log_event(conflict["fact_id_a"], "resolved", f"{resolution} by {resolved_by}", resolved_by)
        self._log_event(conflict["fact_id_b"], "resolved", f"{resolution} by {resolved_by}", resolved_by)
        return {"conflict": conflict, "facts_after": [f for f in facts if f["id"] in
                (conflict["fact_id_a"], conflict["fact_id_b"], by_id.get("id", ""))]}
