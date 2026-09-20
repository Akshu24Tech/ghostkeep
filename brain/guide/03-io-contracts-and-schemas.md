# 03: I/O Contracts, Schemas, & Examples

This document specifies the exact JSON schemas, storage formats, and real-world input/output executions across Ghostkeep.

---

## 1. Storage Schemas

All files reside in `~/.ghostkeep/` (or `$GHOSTKEEP_DIR`):

### `facts.json` (Array of Facts)
```json
[
  {
    "id": "fact_7d0dbba04372",
    "content": "We decided to enforce Vanilla CSS across all frontend components",
    "source_agent": "terminal-agy",
    "source_session_id": "sess-101",
    "confidence": 0.92,
    "domain": "ui",
    "tags": ["ui", "css"],
    "derived_from": null,
    "created_at": "2026-09-20T13:32:38.123456+00:00",
    "superseded_by": null,
    "status": "active"
  }
]
```

### `conflicts.json` (Array of Conflicts)
```json
[
  {
    "id": "conf_a1b2c3d4e5f6",
    "fact_id_a": "fact_7d0dbba04372",
    "fact_id_b": "fact_88e9a1b2c3d4",
    "detected_at": "2026-09-20T14:00:00.000000+00:00",
    "resolved": false,
    "resolution": null,
    "resolved_by": null,
    "resolved_at": null
  }
]
```

### `provenance.jsonl` (Append-Only Event Ledger)
Each line is an immutable JSON object:
```jsonl
{"id": "evt_001", "fact_id": "fact_7d0dbba04372", "event_type": "created", "detail": "written by terminal-agy", "actor": "terminal-agy", "created_at": "2026-09-20T13:32:38+00:00"}
{"id": "evt_002", "fact_id": "fact_7d0dbba04372", "event_type": "conflict_detected", "detail": "overlaps with fact_88e9a1b2c3d4", "actor": "system", "created_at": "2026-09-20T14:00:00+00:00"}
{"id": "evt_003", "fact_id": "fact_7d0dbba04372", "event_type": "resolved", "detail": "keep_a by human-reviewer", "actor": "human-reviewer", "created_at": "2026-09-20T14:15:00+00:00"}
```

---

## 2. The Sieve I/O Contract (`sieve.py`)

### Input Signature
```python
sieve.evaluate(raw_text: str) -> SieveResult
```

### Output: `SieveResult`
```python
@dataclass
class SieveResult:
    is_durable: bool       # True if it should be saved
    confidence: float      # Calibrated 0.0 to 1.0
    domain: str            # "database" | "auth" | "ui" | "devops" | "preferences" | "general"
    reason: str            # Human-readable rationale
    engine: str            # "typesafe_jev" | "local_heuristic"
```

---

## 3. Real-World Execution Examples

### Case A: Ephemeral Terminal Noise (Discarded in ~80ms)

**Input Command / Text:**
```text
npm test: 12 passing, 0 failing (1.4s)
```

**Sieve Result:**
- `is_durable`: `False`
- `confidence`: `0.10`
- `reason`: `"Matched ephemeral noise pattern: ^npm (test|run|install|start)"`

**Terminal Output:**
```
[SIEVE] Evaluation [local_heuristic]:
   Durable   : False
   Confidence: 0.10
   Domain    : general
   Reason    : Matched ephemeral noise pattern: ^npm (test|run|install|start)

[DISCARDED] Classified as ephemeral noise (0 bytes added to memory).
```

---

### Case B: Durable Decision Ingested (Stored with Full Provenance)

**Input Command / Text:**
```text
We decided to enforce Vanilla CSS across all frontend components instead of Tailwind
```

**Sieve Result:**
- `is_durable`: `True`
- `confidence`: `0.92`
- `domain`: `"ui"`
- `reason`: `"Matched constraint trigger"`

**Scribe Distillation Output:**
- `content`: `"We decided to enforce Vanilla CSS across all frontend components instead of Tailwind"`
- `tags`: `["ui", "css"]`

**Terminal Output:**
```
[SIEVE] Evaluation [local_heuristic]:
   Durable   : True
   Confidence: 0.92
   Domain    : ui
   Reason    : Matched constraint trigger

[STORED] Stored with full provenance in facts.json:
   ID        : fact_7d0dbba04372
   Claim     : We decided to enforce Vanilla CSS across all frontend components instead of Tailwind
   Status    : active
   Tags      : ui, css
```

---

### Case C: Searching Memory

**CLI Command:**
```bash
python -m ghostkeep.cli search "CSS"
```

**Output:**
```
Found 1 memory match(es):

* [ACTIVE] [fact_7d0dbba04372] (conf: 0.92, domain: ui)
   We decided to enforce Vanilla CSS across all frontend components instead of Tailwind
   Source: terminal-agy (session: sess-101)
```

---

### Case D: Forensic Provenance Lookup

**CLI Command:**
```bash
python -m ghostkeep.cli provenance fact_7d0dbba04372
```

**Output:**
```
[PROVENANCE] Lineage for fact_7d0dbba04372:
   Content   : We decided to enforce Vanilla CSS across all frontend components instead of Tailwind
   Author    : terminal-agy
   Session   : sess-101
   Confidence: 0.92

   Audit Ledger Events:
     * [2026-09-20T13:32:38] CREATED: written by terminal-agy (actor: terminal-agy)
```

---

## 4. MCP Tool Payloads (JSON-RPC)

### `process_turn`
**Request Payload:**
```json
{
  "method": "tools/call",
  "params": {
    "name": "process_turn",
    "arguments": {
      "raw_text": "Constraint: Never use inline styles, only modular CSS files.",
      "source_agent": "claude-code",
      "source_session_id": "claude-session-991"
    }
  }
}
```

**Response Payload:**
```json
{
  "status": "stored",
  "fact": {
    "id": "fact_4a3b2c1d",
    "content": "Constraint: Never use inline styles, only modular CSS files.",
    "source_agent": "claude-code",
    "source_session_id": "claude-session-991",
    "confidence": 0.92,
    "domain": "ui",
    "tags": ["ui", "css"],
    "status": "active"
  },
  "sieve": {
    "is_durable": true,
    "confidence": 0.92,
    "domain": "ui",
    "reason": "Matched constraint trigger",
    "engine": "local_heuristic"
  }
}
```

---

## 🔗 Next Chapters
- [[01-system-overview-and-purpose]] — Architecture and motivation.
- [[02-component-deep-dive]] — Detailed code breakdown.
- [[04-developer-workflow-and-setup]] — Setup, testing, and IDE configurations.
