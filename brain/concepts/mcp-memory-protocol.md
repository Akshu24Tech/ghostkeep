# MCP Memory Protocol

> **Vision:** A universal cross-agent memory bus enabled by the Model Context Protocol (MCP).

Historically, every AI tool maintained its own walled garden:
- Claude Desktop stored memories in local Anthropic app data.
- Cursor maintained indexed chat histories in `.cursor`.
- Claude Code had its own session context.
- Gemini CLI had its own history store.

An agent assisting you in Cursor had no knowledge of architectural constraints formulated in Claude Desktop an hour earlier.

---

## MCP as the Shared Substrate

The **Model Context Protocol (MCP)** provides an open, bidirectional standard for language models to interface with local and remote resources, prompts, and tools.

Ghostkeep leverages MCP to serve as a **single shared memory daemon**:

```
 ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
 │ Claude Desktop │   │  Claude Code   │   │ Cursor / IDE   │
 └───────┬────────┘   └───────┬────────┘   └───────┬────────┘
         │ (stdio)            │ (stdio)            │ (stdio)
         └──────────────┐     │     ┌──────────────┘
                        ▼     ▼     ▼
                ┌───────────────────────────────┐
                │      Ghostkeep MCP Server     │
                │        (`server.py`)          │
                └──────────────┬────────────────┘
                               │
                               ▼
                ┌───────────────────────────────┐
                │       Shared MemoryStore      │
                │         (~/.ghostkeep)        │
                └───────────────────────────────┘
```

---

## Exposed Tool Signatures

Ghostkeep exposes a clean, minimal 5-tool MCP surface:

1. `add_memory(content, source_agent, source_session_id, confidence, tags, derived_from)`
   - Used when any agent learns a durable constraint, architectural pattern, or user preference.
2. `search_memory(query, min_confidence, source_agent, limit)`
   - Queried at session bootstrap or when planning actions.
3. `get_provenance(fact_id)`
   - Used when an agent needs to verify why a rule was instituted.
4. `list_conflicts(include_resolved)`
   - Surfaces unaddressed contradictions to agents or users.
5. `resolve_conflict(conflict_id, resolution, resolved_by)`
   - Allows an authorized orchestrator or human in the loop to resolve contradictory directives.

---

## Related Notes
- [[storage-engine]] — The underlying file backend accessed by the MCP server.
- [[provenance-tracking]] — Capturing `source_agent` across MCP sessions.
- [[ghostkeep-vs-traditional-memory]] — Shared protocol vs proprietary vendor silos.
