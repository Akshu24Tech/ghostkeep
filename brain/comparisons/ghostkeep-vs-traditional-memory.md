# Ghostkeep vs Traditional Memory Systems

How Ghostkeep compares to Mem0, Supermemory, LangChain Memory, and Native LLM Memory (Claude / ChatGPT / Gemini).

---

## Comparison Matrix

| Dimension | Native Vendor Memory (Claude/ChatGPT) | Vector Stores (Mem0 / Supermemory / Chroma) | Ghostkeep |
|---|---|---|---|
| **Cross-Client Access** | ❌ Locked to specific web UI or app | ⚠️ Requires bespoke API wrapper | ✅ Standard MCP Server for any client |
| **Ground Truth Transparency** | ❌ Opaque cloud store | ❌ Black-box vector embeddings | ✅ Plain JSON (`facts.json`) |
| **Provenance Tracking** | ❌ None | ❌ Lost upon ingestion | ✅ Full lineage (`source_agent`, `session_id`, `derived_from`) |
| **Conflict Handling** | ❌ Silent last-write-wins or duplicates | ❌ Cosine distance noise | ✅ Explicit conflict queue with audit events |
| **Git Integration** | ❌ None | ❌ Binary DB files | ✅ Plain text files easily committed & diffed |
| **External Dependencies** | Vendor-managed | Docker, Vector DBs, Embedding models | Zero dependencies (Python standard library) |
| **Auditability** | ❌ None | ❌ Complex query logging | ✅ Append-only `provenance.jsonl` ledger |

---

## Why Existing Solutions Fall Short

### 1. The "Vector Amnesia" Problem
Vector memory systems convert text into float32 arrays and discard the context of who said what. If Agent A (a junior developer agent) writes a faulty assumption, and Agent B (a senior staff engineer agent) writes the correct architectural pattern, a vector search will return both with near-identical cosine similarity. The downstream agent has no objective metric to distinguish the authoritative instruction from the flawed one.

### 2. The Silent Overwrite Problem
In naive Key-Value or SQL memory stores, overwriting an existing key (`user_preferences`) silently deletes previous instructions. If a user says *"For this experimental branch only, let's use SQLite instead of Postgres"*, a naive system permanently forgets that the production database is Postgres. Ghostkeep instead flags a conflict or records a session-scoped branch.

---

## Related Notes
- [[provenance-tracking]] — The provenance advantage.
- [[vectorless-memory]] — Why vectors are unnecessary for core agent facts.
- [[ghostkeep-and-dreamkeeper]] — The consolidation layer.
