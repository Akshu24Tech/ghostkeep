"""
Ghostkeep Memory Store — Provenance-aware file-backed persistence engine.

Design principles:
1. Plain files are the source of truth (facts.json, conflicts.json, provenance.jsonl).
2. Every fact carries source_agent, source_session_id, calibrated confidence,
   and derivation chain (answers 'why is this fact what it is').
3. Conflicting facts are never silently overwritten; they are queued in conflicts.json
   and logged to the append-only provenance ledger.
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
    source_agent: str          # e.g. "terminal-agy", "claude-code", "ide-agent"
    source_session_id: str     # traceable back to the conversation/run that wrote it
    confidence: float          # 0.0–1.0 — calibrated confidence
    domain: str = "general"    # e.g. "auth", "database", "ui", "devops", "preferences"
    tags: list[str] = field(default_factory=list)
    derived_from: Optional[str] = None   # antecedent fact id
    created_at: str = field(default_factory=_now)
    superseded_by: Optional[str] = None  # set when resolved into another fact
    status: str = "active"     # active | superseded | conflicted

    def to_dict(self):
        return asdict(self)


@dataclass
class ProvenanceEvent:
    id: str
    fact_id: str
    event_type: str            # created | conflict_detected | resolved | superseded
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
    resolution: Optional[str] = None     # keep_a | keep_b | merge:<text>
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None

    def to_dict(self):
        return asdict(self)


SIMILARITY_THRESHOLD = 0.72


class MemoryStore:
    """
    File-backed store. Layout under root_dir:
        facts.json        -- list of Fact dicts
        conflicts.json     -- list of Conflict dicts
        provenance.jsonl   -- append-only log of ProvenanceEvents
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

    # ---------- IO Primitives ----------

    @staticmethod
    def _write_json(path: Path, data):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _read_json(path: Path):
        if not path.exists():
            return []
        content = path.read_text(encoding="utf-8")
        return json.loads(content or "[]")

    def _log_event(self, fact_id: str, event_type: str, detail: str, actor: str) -> ProvenanceEvent:
        event = ProvenanceEvent(
            id=_new_id("evt"),
            fact_id=fact_id,
            event_type=event_type,
            detail=detail,
            actor=actor,
        )
        with self.provenance_path.open("a", encoding="utf-8") as f:
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

    # ---------- Public API ----------

    def add_memory(
        self,
        content: str,
        source_agent: str,
        source_session_id: str,
        confidence: float = 0.8,
        domain: str = "general",
        tags: Optional[list[str]] = None,
        derived_from: Optional[str] = None,
    ) -> dict:
        fact = Fact(
            id=_new_id("fact"),
            content=content,
            source_agent=source_agent,
            source_session_id=source_session_id,
            confidence=max(0.0, min(1.0, confidence)),
            domain=domain,
            tags=tags or [],
            derived_from=derived_from,
        )
        facts = self._all_facts()
        facts.append(fact.to_dict())
        self._save_facts(facts)
        self._log_event(fact.id, "created", f"written by {source_agent}", source_agent)

        conflict = self._detect_conflict(fact, facts)
        if conflict:
            self._log_event(
                fact.id,
                "conflict_detected",
                f"overlaps with {conflict['fact_id_a'] if conflict['fact_id_b'] == fact.id else conflict['fact_id_b']}",
                "system",
            )
        return fact.to_dict()

    def _detect_conflict(self, new_fact: Fact, facts: list[dict]) -> Optional[dict]:
        """
        Detects if an active fact from a different agent opposes or conflicts
        with new_fact. Uses sequence similarity as baseline.
        """
        for other in facts:
            if other["id"] == new_fact.id or other["status"] != "active":
                continue
            if other["source_agent"] == new_fact.source_agent:
                continue
            ratio = difflib.SequenceMatcher(
                None, other["content"].lower(), new_fact.content.lower()
            ).ratio()
            if SIMILARITY_THRESHOLD <= ratio < 0.99:
                conflicts = self._all_conflicts()
                c = Conflict(id=_new_id("conf"), fact_id_a=other["id"], fact_id_b=new_fact.id)
                conflicts.append(c.to_dict())
                self._save_conflicts(conflicts)

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
        domain: Optional[str] = None,
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
            if domain and f.get("domain") != domain:
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
        if self.provenance_path.exists():
            with self.provenance_path.open("r", encoding="utf-8") as fh:
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
                domain=a.get("domain", "general"),
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
        return {
            "conflict": conflict,
            "facts_after": [f for f in facts if f["id"] in (conflict["fact_id_a"], conflict["fact_id_b"])],
        }
