# 02: Codebase Component Deep Dive

This guide breaks down every module, class, and method inside the [`ghostkeep/`](file:///e:/Ghost%20OS/projects/ghostkeep/ghostkeep) codebase.

---

## 📂 Codebase File Map

```
ghostkeep/
├── __init__.py      # Package entrypoint & public exports
├── store.py         # File-backed persistence, provenance tracking & conflict logic
├── sieve.py         # System 1 micro-decision filter (Jev RLCD & heuristic fallback)
├── scribe.py        # Distillation engine converting raw text to canonical facts
├── server.py        # Universal MCP server (Model Context Protocol stdio transport)
└── cli.py           # Command-line interface with Windows UTF-8 safety
tests/
├── test_store.py    # Unit tests for store operations, conflicts, and provenance
└── test_sieve.py    # Unit tests for noise filtering and decision distillation
```

---

## 1. `ghostkeep/store.py` (The Persistence Engine)

### Core Data Structures
- **`Fact`**: Represents a single atomic unit of ground truth knowledge.
  - `id`: Unique identifier (e.g. `fact_7d0dbba04372`).
  - `content`: The canonical statement (e.g. *"We decided to enforce Vanilla CSS"*).
  - `source_agent`: Identity of the writing agent (`"terminal-agy"`, `"ide-agent"`).
  - `source_session_id`: Correlation ID linking back to the raw conversation/task run.
  - `confidence`: Calibrated certainty score (`0.0` to `1.0`).
  - `domain`: Functional bucket (`"database"`, `"auth"`, `"ui"`, `"devops"`, `"preferences"`).
  - `derived_from`: Pointer to antecedent fact ID if inferred or merged.
  - `status`: `"active"` | `"conflicted"` | `"superseded"`.
  - `superseded_by`: ID of the newer fact that replaced it.

- **`ProvenanceEvent`**: An immutable audit ledger entry.
  - `id`: Event ID (e.g. `evt_9a8b7c6d5e4f`).
  - `fact_id`: Target fact.
  - `event_type`: `"created"` | `"conflict_detected"` | `"resolved"` | `"superseded"`.
  - `detail`: Description of what occurred.
  - `actor`: Who performed the event (agent name, user, or `"system"`).

- **`Conflict`**: A pending or resolved contradiction between two facts.
  - `id`: Conflict ID (e.g. `conf_3f4e5d6c7b8a`).
  - `fact_id_a`, `fact_id_b`: The two clashing facts.
  - `resolved`: Boolean flag.
  - `resolution`: Strategy applied (`"keep_a"`, `"keep_b"`, `"merge:<text>"`).

### Key Methods in `MemoryStore`
| Method | Inputs | Outputs | Behavior |
|---|---|---|---|
| `add_memory()` | `content`, `source_agent`, `source_session_id`, `confidence`, `domain`, `tags`, `derived_from` | `dict` (Fact) | Saves fact, appends `created` event to `provenance.jsonl`, checks for contradictions. |
| `_detect_conflict()` | `new_fact: Fact`, `facts: list[dict]` | `dict` or `None` | Compares text against active facts from *other* agents. If similarity is between `0.72` and `0.99`, marks both `conflicted` and records in `conflicts.json`. |
| `search_memory()` | `query`, `domain`, `min_confidence`, `source_agent`, `include_superseded`, `limit` | `list[dict]` | Ranks active facts by string similarity and confidence. Filters by domain or agent. |
| `get_provenance()` | `fact_id` | `dict` | Returns fact, all chronological events touching it, and recursive `derivation_chain`. |
| `list_conflicts()` | `include_resolved: bool` | `list[dict]` | Returns all conflicts enriched with full text of Fact A and Fact B. |
| `resolve_conflict()` | `conflict_id`, `resolution`, `resolved_by` | `dict` | Applies `keep_a`, `keep_b`, or `merge:<text>`, updates statuses to `superseded`/`active`, and logs resolution to audit ledger. |

---

## 2. `ghostkeep/sieve.py` (System 1 Micro-Decision Filter)

### Purpose
To answer in under 100ms: *"Does this command or conversation turn declare a permanent decision, or is it disposable noise?"*

### Architecture
- **`MemorySieve`**:
  - Checks if `TYPESAFE_API_KEY` is available in environment.
  - If present, initializes `typesafe_sdk.TypeSafeClient` and invokes Jev via `system_one()` with `Noul`, `Choice`, and `Score`.
  - If not present or network unavailable, falls back to the **Deterministic Heuristic Engine**.

### Decision & Noise Rules:
- **`NOISE_PATTERNS`**: Matches commands like `npm test`, `git status`, test summary counters (`12 passed`), progress bars, and casual greetings. Any match immediately returns `is_durable = False` (confidence `0.10`).
- **`DECISION_PATTERNS`**: Regex matching strong decision triggers:
  - *"we decided to"*, *"switched from"*, *"migrate to"*
  - *"always use"*, *"never use"*, *"constraint:"*
  - *"root cause:"*, *"fixed bug caused by"*
  - High confidence (`0.85` – `0.92`).
- **`DOMAIN_KEYWORDS`**: Automatically maps content to `"database"`, `"auth"`, `"ui"`, `"devops"`, or `"preferences"`.

---

## 3. `ghostkeep/scribe.py` (Distillation Engine)

### Purpose
Jev and the Sieve determine *what* to keep, but cannot write prose. `MemoryScribe` cleans and formats the passing text into a canonical statement.

### Key Logic:
1. **Preamble Stripping**: Strips conversational fluff like `"So basically..."`, `"I was thinking and we agreed that..."`, `"FYI..."`.
2. **Primary Claim Isolation**: Extracts the main operative sentence.
3. **Keyword Tagging**: Automatically attaches technical tags (e.g. `["ui", "css"]` or `["database", "postgres"]`).

---

## 4. `ghostkeep/server.py` (Universal MCP Server)

Exposes the engine over standard I/O (stdio) transport using Model Context Protocol (MCP).

### Exposed MCP Tools:
1. **`process_turn(raw_text, source_agent, source_session_id)`**:
   - The primary ambient tool. Takes raw text, passes through `MemorySieve`.
   - If noise: returns `{"status": "discarded", "reason": ...}`.
   - If durable: distills via `MemoryScribe`, saves to `MemoryStore`, and returns `{"status": "stored", "fact": ...}`.
2. **`add_memory(...)`**: Explicit fact storage.
3. **`search_memory(...)`**: Semantic/lexical query tool.
4. **`get_provenance(...)`**: Lineage and forensic audit trail inspection.
5. **`list_conflicts(...)`**: Review pending contradictions.
6. **`resolve_conflict(...)`**: Settle contradictions.

---

## 5. `ghostkeep/cli.py` (Command Line Interface)

A fast, terminal-native CLI designed with Windows UTF-8 console compatibility (`sys.stdout.reconfigure(encoding="utf-8")`):
- `ghostkeep ingest "<text>"`: Evaluates a turn and outputs Sieve rationale.
- `ghostkeep search "<query>"`: Fast formatted memory lookup.
- `ghostkeep conflicts`: Shows pending disputes between agents.
- `ghostkeep provenance <fact_id>`: Prints chronological event timeline.
- `ghostkeep serve`: Starts the MCP server on stdio.

---

## 🔗 Next Chapters
- [[01-system-overview-and-purpose]] — High-level architecture and problem space.
- [[03-io-contracts-and-schemas]] — Complete JSON schemas and I/O examples.
- [[04-developer-workflow-and-setup]] — Step-by-step setup and client configurations.
