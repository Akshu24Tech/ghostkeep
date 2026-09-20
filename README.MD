# Ghostkeep

**Provenance-aware shared memory store and System 1 micro-decision sieve for AI agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Ready](https://img.shields.io/badge/MCP-Protocol-purple.svg)](https://modelcontextprotocol.io)

---

## The Problem

Developers work across multiple agent execution surfaces simultaneously:
- **Terminal CLI** (`agy`, `claude`) running long tasks, builds, and tests.
- **IDE Agent** (Antigravity IDE, Cursor, Windsurf) pair-programming and refactoring code.

**They suffer from complete amnesia.** The terminal agent fixes a bug or upgrades a dependency, but the IDE agent has zero awareness of it. Calling frontier LLMs (Claude Sonnet, GPT-4o) on every single terminal command and lint output takes 3 seconds and wastes thousands of tokens on noisy compiler logs.

---

## The Solution: The 3-Tier Memory Sieve

Ghostkeep acts as the **shared central nervous system** across surfaces using a 3-tier architecture:

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
 └───────────────────────────────────────────────────────────────┘
```

1. **Tier 1 (The Sieve)**: Fast micro-decision filter (using **Jev System 1** when `TYPESAFE_API_KEY` is set, or local heuristic engine). Discards 90% of ephemeral terminal output in ~80ms.
2. **Tier 2 (The Scribe)**: Strips filler and distills the core 1-sentence canonical claim and metadata.
3. **Tier 3 (The Store)**: Plain-file source of truth with full lineage (`source_agent`, `source_session_id`, `derived_from`) and conflict detection.

---

## Quick Start

### Installation

```bash
git clone https://github.com/Akshu24Tech/ghostkeep.git
cd ghostkeep
pip install -e .
```

To enable Jev System 1 acceleration:
```bash
pip install typesafe-sdk
export TYPESAFE_API_KEY="your-typesafe-key"
```

---

## CLI Usage

### Ingest a turn through the Sieve
```bash
# 1. Ephemeral noise -> Discarded in 0 bytes:
ghostkeep ingest "npm test: 14 passing, 0 failing"

# 2. Durable decision -> Stored with provenance:
ghostkeep ingest "We decided to enforce Vanilla CSS across all components instead of Tailwind" \
  --source "terminal-agy" \
  --session "session-92"
```

### Search memories
```bash
ghostkeep search "CSS"
```

### List and resolve conflicts
```bash
ghostkeep conflicts
```

---

## MCP Server Configuration

Point your MCP clients to Ghostkeep so Terminal, IDE, and Desktop share the same memory:

### Claude Desktop (`claude_desktop_config.json`)
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

### Cursor (`.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "ghostkeep": {
      "command": "python",
      "args": ["-m", "ghostkeep.cli", "serve"]
    }
  }
}
```

---

## MCP Tools Reference

| Tool | Parameters | Description |
|---|---|---|
| `process_turn` | `raw_text`, `source_agent`, `source_session_id` | **The Ambient Sieve**: Runs the 80ms filter. Discards noise or distills & saves durable memory. |
| `add_memory` | `content`, `source_agent`, `source_session_id`, `confidence`, `domain`, `tags` | Direct fact insertion with contradiction checks. |
| `search_memory` | `query`, `domain`, `min_confidence`, `source_agent`, `limit` | Ranked lexical and confidence memory search. |
| `get_provenance` | `fact_id` | Lineage ancestry, derivation chain, and event audit trail. |
| `list_conflicts` | `include_resolved` | List unresolved contradictory facts across agents. |
| `resolve_conflict` | `conflict_id`, `resolution`, `resolved_by` | Resolve conflict (`keep_a`, `keep_b`, `merge:<text>`). |

---

## Running Tests

```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

## In-Repo Brain (Obsidian Vault)

For conceptual models, research notes on System One AI, W3C PROV specifications, and comparison matrices, open:
[`projects/ghostkeep/brain`](brain/) in Obsidian.

---

## License

[MIT](LICENSE) © 2026 Akshu24Tech
