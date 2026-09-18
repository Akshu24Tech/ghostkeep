# Ghostkeep

**Provenance-aware shared memory store and MCP server for AI agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Ready](https://img.shields.io/badge/MCP-Protocol-purple.svg)](https://modelcontextprotocol.io)

---

## What is Ghostkeep?

Generic agent memory tools (Mem0, Supermemory, Echo, or vendor-locked native memory in Claude/Gemini) store text blobs in isolated vector databases. When an agent retrieves a memory, it has no idea:
- **Where** did this fact come from?
- **Which** tool, session, or agent wrote it?
- **How** confident was the author?
- **What** previous facts was it derived from?
- **Why** is there a conflicting statement, and how was it resolved?

**Ghostkeep solves this by making provenance a first-class citizen.**

Every fact in Ghostkeep carries its authoring agent, session ID, confidence score, and derivation chain. Conflicting facts from different agents are never silently overwritten — they enter a conflict queue with a full audit trail until explicitly resolved.

Best of all: **Plain files are the source of truth.** No heavyweight vector database or external cluster is required to trust a fact. JSON files are human-readable, git-diffable, and lightweight.

---

## Core Architecture

```
~/.ghostkeep/ (or $GHOSTKEEP_DIR)
├── facts.json        # Canonical active, conflicted, and superseded facts
├── conflicts.json    # Pending & resolved cross-agent contradiction queue
└── provenance.jsonl  # Append-only immutable event ledger (audit trail)
```

```
                     ┌───────────────────────────┐
                     │   Claude Desktop / Code   │
                     ├───────────────────────────┤
                     │     Cursor / Windsurf     │
                     ├───────────────────────────┤
                     │   Custom Agents / Scripts │
                     └─────────────┬─────────────┘
                                   │ (MCP / Python)
                                   ▼
                     ┌───────────────────────────┐
                     │         GHOSTKEEP         │
                     │  MemoryStore & MCP Server │
                     └─────────────┬─────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
      ┌───────────────┐    ┌───────────────┐    ┌────────────────┐
      │  facts.json   │    │conflicts.json │    │provenance.jsonl│
      │ (Source Truth)│    │(Contradictions│    │(Audit Ledger)  │
      └───────────────┘    └───────────────┘    └────────────────┘
```

---

## Key Features

1. **Full Provenance & Audit Trail**: Answers *"Why is this fact what it is?"* with complete lineage, authoring agent identity, session tracing, and immutable event logs.
2. **Conflict Queue (Zero Silent Overwrites)**: When two agents write contradictory facts, both facts are flagged and added to `conflicts.json`. Nothing is destroyed or silently trampled.
3. **No Heavy Vector DB Required**: Works out of the box with zero external infrastructure.
4. **Universal MCP Server**: One shared memory store across Claude Desktop, Claude Code, Cursor, Windsurf, and Gemini.

---

## Quick Start

### Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/Akshu24Tech/ghostkeep.git
cd ghostkeep
pip install -e .
```

Or install dependencies directly:
```bash
pip install -r requirements.txt
```

---

## MCP Server Configuration

Ghostkeep provides an MCP server (`server.py`) using standard I/O transport.

### 1. Claude Desktop

Add this to your `claude_desktop_config.json`:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ghostkeep": {
      "command": "python",
      "args": ["-m", "ghostkeep.server"],
      "env": {
        "GHOSTKEEP_DIR": "~/.ghostkeep"
      }
    }
  }
}
```

### 2. Cursor

In `.cursor/mcp.json` (or Cursor Settings > MCP):

```json
{
  "mcpServers": {
    "ghostkeep": {
      "command": "python",
      "args": ["path/to/ghostkeep/server.py"],
      "env": {
        "GHOSTKEEP_DIR": "~/.ghostkeep"
      }
    }
  }
}
```

### 3. Windsurf

In `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "ghostkeep": {
      "command": "python",
      "args": ["path/to/ghostkeep/server.py"]
    }
  }
}
```

---

## MCP Tools Reference

Ghostkeep exposes 5 tools over MCP:

| Tool | Parameters | Description |
|---|---|---|
| `add_memory` | `content`, `source_agent`, `source_session_id`, `confidence=0.8`, `tags=[]`, `derived_from=None` | Stores a fact with full origin provenance. Automatically checks for potential contradictions. |
| `search_memory` | `query`, `min_confidence=0.0`, `source_agent=None`, `limit=10` | Searches facts ranked by relevance and confidence. |
| `get_provenance` | `fact_id` | Returns complete origin info, timeline of all events, and derivation ancestry. |
| `list_conflicts` | `include_resolved=False` | Lists detected contradictory facts across agents waiting for resolution. |
| `resolve_conflict` | `conflict_id`, `resolution`, `resolved_by` | Resolves conflict via `keep_a`, `keep_b`, or `merge:<new text>`. Logs resolution event to audit ledger. |

---

## Python API Usage

You can also use Ghostkeep directly in Python without MCP:

```python
from ghostkeep import MemoryStore

store = MemoryStore("./my_memory")

# 1. Add memories from different agents
f1 = store.add_memory(
    content="User prefers Python for data engineering projects",
    source_agent="claude-code",
    source_session_id="session-2026-09-18",
    confidence=0.95,
    tags=["preferences", "python"]
)

# 2. Search memories
results = store.search_memory("Python preferences", min_confidence=0.5)
for fact in results:
    print(f"[{fact['source_agent']}] {fact['content']} (confidence: {fact['confidence']})")

# 3. Inspect provenance and audit chain
prov = store.get_provenance(f1["id"])
print("History of events:", prov["events"])

# 4. Check and resolve conflicts
conflicts = store.list_conflicts()
for conflict in conflicts:
    print(f"Conflict detected between {conflict['fact_id_a']} and {conflict['fact_id_b']}")
    store.resolve_conflict(conflict["id"], resolution="keep_a", resolved_by="human-reviewer")
```

---

## Running Tests

Ghostkeep includes test coverage for store operations, conflict detection, and provenance tracking:

```bash
python -m unittest tests/test_store.py
# or if pytest is installed:
pytest
```

---

## Ecosystem

Ghostkeep works seamlessly with [DreamKeeper](https://github.com/Akshu24Tech/dreamkeeper) — an open-source memory consolidation agent ("dreaming pass") that merges duplicates, supersedes stale facts, and synthesizes higher-order patterns.

---

## License

[MIT](LICENSE) © 2026 Akshu24Tech
