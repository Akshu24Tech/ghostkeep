# Storage Engine Architecture

> **Simplicity over complexity:** File-backed storage with atomic JSON writes and an append-only JSONL event ledger.

The entire Ghostkeep storage engine is contained in [`ghostkeep/store.py`](file:///e:/Ghost%20OS/projects/ghostkeep/store.py). It has **zero third-party dependencies**, using only Python standard library modules (`json`, `uuid`, `difflib`, `dataclasses`, `pathlib`, `datetime`).

---

## File Layout

Ghostkeep stores all state under `GHOSTKEEP_DIR` (defaulting to `~/.ghostkeep`):

```
$GHOSTKEEP_DIR/
├── facts.json
├── conflicts.json
└── provenance.jsonl
```

### 1. `facts.json`
Array of `Fact` dictionaries.
```json
[
  {
    "id": "fact_7a8b9c0d1e2f",
    "content": "User prefers Python for data engineering",
    "source_agent": "claude-code",
    "source_session_id": "session-1",
    "confidence": 0.95,
    "tags": ["python", "preferences"],
    "derived_from": null,
    "created_at": "2026-09-18T11:45:00.000Z",
    "superseded_by": null,
    "status": "active"
  }
]
```

### 2. `conflicts.json`
Array of detected contradictory pairs awaiting review.
```json
[
  {
    "id": "conf_3f4e5d6c7b8a",
    "fact_id_a": "fact_7a8b9c0d1e2f",
    "fact_id_b": "fact_99a8b7c6d5e4",
    "detected_at": "2026-09-18T12:00:00.000Z",
    "resolved": false,
    "resolution": null,
    "resolved_by": null,
    "resolved_at": null
  }
]
```

### 3. `provenance.jsonl`
Append-only log of every mutation and lifecycle event. Never modified, only appended.
```jsonl
{"id": "evt_111", "fact_id": "fact_7a8b9c0d1e2f", "event_type": "created", "detail": "written by claude-code", "actor": "claude-code", "created_at": "2026-09-18T11:45:00.000Z"}
{"id": "evt_222", "fact_id": "fact_7a8b9c0d1e2f", "event_type": "conflict_detected", "detail": "overlaps with fact_99a8b7c6d5e4", "actor": "system", "created_at": "2026-09-18T12:00:00.000Z"}
{"id": "evt_333", "fact_id": "fact_7a8b9c0d1e2f", "event_type": "resolved", "detail": "keep_a by human-reviewer", "actor": "human-reviewer", "created_at": "2026-09-18T12:15:00.000Z"}
```

---

## Performance Characteristics

- **Read throughput**: Sub-millisecond reads from memory; small file sizes load in under 1ms.
- **Search complexity**: $O(N)$ string sequence matching across active facts, lightning-fast for typical knowledge stores (<10,000 facts).
- **Concurrency**: In multi-agent environments, file locking or SQLite backing can be layered transparently as an upgrade without changing the public MCP interface.

---

## Related Notes
- [[lifecycle-of-a-fact]] — How facts move through the storage engine.
- [[vectorless-memory]] — Rationale for this zero-dependency architecture.
- [[provenance-tracking]] — The provenance event schema.
