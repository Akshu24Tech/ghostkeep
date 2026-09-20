# Ghostkeep: The Complete Engineering Manual

> **A comprehensive reference on Ghostkeep's purpose, architecture, modules, I/O schemas, and workflows.**

---

## Table of Contents
1. [Overview & Problem Space](#1-overview--problem-space)
2. [3-Tier Architecture](#2-3-tier-architecture)
3. [Codebase Modules Deep Dive](#3-codebase-modules-deep-dive)
4. [I/O Contracts & Schemas](#4-io-contracts--schemas)
5. [Real-World Execution Walkthroughs](#5-real-world-execution-walkthroughs)
6. [Setup & Client Integrations](#6-setup--client-integrations)

---

## 1. Overview & Problem Space

### The Core Friction: Cross-Surface Agent Amnesia
Modern agentic software engineering occurs across multiple execution surfaces:
- **Terminal CLI** (`agy`, `claude`): Running background migrations, long builds, benchmark tests.
- **IDE Pair-Programmer** (Antigravity IDE, Cursor, Windsurf): Writing code, editing schemas, refactoring.

Even when running on the same machine and in the same repository, these agents operate in **cognitive isolation**. Terminal actions are not visible to the IDE agent, and architectural constraints set in the IDE are frequently clobbered by terminal agents.

### The Ghostkeep Solution
Ghostkeep is a **lightweight, file-backed shared memory store and System 1 micro-decision sieve** that acts as the real-time central nervous system across all agent surfaces.

---

## 2. 3-Tier Architecture

```
                  RAW CHAT TURN / TERMINAL COMMAND
                                 │
                                 ▼
 ┌───────────────────────────────────────────────────────────────┐
 │ TIER 1: THE SIEVE (sieve.py) - ~80ms System 1 Micro-Decision  │
 │ • Evaluates raw text in <100ms via Jev (or local engine)      │
 │ • Noul  : "Contains durable decision or constraint?"          │
 │ • Choice: Route to domain (database, auth, ui, devops, etc.)  │
 └───────────────────────────────┬───────────────────────────────┘
                                 │
                 Is `contains_decision` >= 0.75?
                                 │
                 ┌───────────────┴───────────────┐
                 ▼ (No: 90% noise)               ▼ (Yes: 10% signal)
          ┌─────────────┐         ┌──────────────────────────────┐
          │   DISCARD   │         │ TIER 2: THE SCRIBE (scribe)  │
          │ (Zero bloat)│         │ • Distills 1-sentence Fact   │
          └─────────────┘         │ • Cleans chatter & preambles │
                                  └──────────────┬───────────────┘
                                                 │
                                                 ▼
 ┌───────────────────────────────────────────────────────────────┐
 │ TIER 3: PROVENANCE STORE (store.py)                           │
 │ • Real-time contradiction check (no silent overwrites)        │
 │ • facts.json (Active & superseded facts)                      │
 │ • conflicts.json (Queue of contradictory statements)          │
 │ • provenance.jsonl (Immutable audit ledger)                   │
 └───────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
                     UNIVERSAL MCP SERVER / CLI
                   (Both agents query on startup)
```

1. **Tier 1 (The Sieve)**: Fast non-autoregressive filter (using **Jev System 1** when `TYPESAFE_API_KEY` is present, or local heuristic engine). Drops 90% of ephemeral terminal output in ~80ms.
2. **Tier 2 (The Scribe)**: Cleans preambles and distills the core 1-sentence canonical claim.
3. **Tier 3 (The Store)**: Plain-file ground truth with complete lineage (`source_agent`, `source_session_id`, `derived_from`) and conflict detection.

---

## 3. Codebase Modules Deep Dive

### `ghostkeep/store.py`
The file-backed persistence engine:
- **`Fact`**: Dataclass holding canonical claims, calibrated confidence, domain, status (`active`, `conflicted`, `superseded`), and derivation ancestry.
- **`ProvenanceEvent`**: Immutable event object appended to `provenance.jsonl` on creation, conflict detection, resolution, and supersession.
- **`Conflict`**: Staged contradiction record linking Fact A and Fact B.
- **`MemoryStore`**:
  - `add_memory()`: Adds fact, appends to provenance, triggers `_detect_conflict()`.
  - `search_memory()`: Ranks facts by sequence similarity and confidence; supports domain filtering.
  - `get_provenance()`: Retrieves full event history and recursive derivation tree.
  - `list_conflicts()`: Returns pending or resolved contradictions.
  - `resolve_conflict()`: Applies `keep_a`, `keep_b`, or `merge:<new text>` with audit logs.

### `ghostkeep/sieve.py`
The System 1 micro-decision engine:
- **`MemorySieve`**: Evaluates whether raw text contains permanent institutional memory.
- Uses **TypeSafe Jev** (`typesafe-sdk`) with `Noul` (probability), `Choice` (domain routing), and `Score` (permanence) when configured.
- Contains high-precision regex heuristic fallbacks for offline and zero-config local execution.
- Discards noise patterns (`npm test`, `git status`, test passing counters, progress bars).

### `ghostkeep/scribe.py`
The distillation layer:
- **`MemoryScribe`**: Strips conversational fluff (`"basically..."`, `"we agreed..."`), isolates the core operative sentence, and generates domain tags.

### `ghostkeep/server.py`
The Model Context Protocol (MCP) server:
- Exposes 6 tools over standard I/O (stdio):
  - `process_turn`: The one-stop ambient sieve and storage pipeline.
  - `add_memory`: Direct fact insertion.
  - `search_memory`: Memory retrieval.
  - `get_provenance`: Lineage lookup.
  - `list_conflicts`: Contradiction queue.
  - `resolve_conflict`: Conflict settlement.

### `ghostkeep/cli.py`
Windows-safe command line interface with UTF-8 console safety:
- `ghostkeep ingest "<text>"`
- `ghostkeep search "<query>"`
- `ghostkeep conflicts`
- `ghostkeep provenance <fact_id>`
- `ghostkeep serve`

---

## 4. I/O Contracts & Schemas

### Facts Schema (`facts.json`)
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

### Provenance Schema (`provenance.jsonl`)
```jsonl
{"id": "evt_001", "fact_id": "fact_7d0dbba04372", "event_type": "created", "detail": "written by terminal-agy", "actor": "terminal-agy", "created_at": "2026-09-20T13:32:38+00:00"}
```

---

## 5. Real-World Execution Walkthroughs

### Example 1: Discarding Ephemeral Noise
```bash
$ python -m ghostkeep.cli ingest "npm test: 12 passing, 0 failing"

[SIEVE] Evaluation [local_heuristic]:
   Durable   : False
   Confidence: 0.10
   Domain    : general
   Reason    : Matched ephemeral noise pattern: ^npm (test|run|install|start)

[DISCARDED] Classified as ephemeral noise (0 bytes added to memory).
```

### Example 2: Ingesting an Architectural Decision
```bash
$ python -m ghostkeep.cli ingest "We decided to enforce Vanilla CSS across all frontend components" --source "terminal-agy"

[SIEVE] Evaluation [local_heuristic]:
   Durable   : True
   Confidence: 0.92
   Domain    : ui
   Reason    : Matched constraint trigger

[STORED] Stored with full provenance in facts.json:
   ID        : fact_7d0dbba04372
   Claim     : We decided to enforce Vanilla CSS across all frontend components
   Status    : active
   Tags      : ui, css
```

### Example 3: Searching Memory
```bash
$ python -m ghostkeep.cli search "CSS"

Found 1 memory match(es):
* [ACTIVE] [fact_7d0dbba04372] (conf: 0.92, domain: ui)
   We decided to enforce Vanilla CSS across all frontend components
   Source: terminal-agy (session: interactive)
```

---

## 6. Setup & Client Integrations

### Install
```bash
git clone https://github.com/Akshu24Tech/ghostkeep.git
cd ghostkeep
pip install -e .
```

### Configure MCP Client (e.g. Claude Desktop / Cursor)
```json
{
  "mcpServers": {
    "ghostkeep": {
      "command": "python",
      "args": ["-m", "ghostkeep.cli", "serve"],
      "env": {
        "GHOSTKEEP_DIR": "~/.ghostkeep"
      }
    }
  }
}
```

### Run Tests
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 7. License

[MIT](LICENSE) © 2026 Akshu24Tech
