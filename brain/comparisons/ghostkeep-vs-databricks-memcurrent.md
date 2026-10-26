# Ghostkeep vs Databricks MemCurrent: Code-Grounded Memory vs Enterprise Dreaming

> **Context:** Architectural comparison evaluating how Ghostkeep's deterministic claims register contrasts with Databricks Research's **MemCurrent** persistent memory architecture (powers Agent Bricks Memory and Genie).

---

## 1. High-Level Comparison Matrix

| Architectural Feature | **Ghostkeep** | **Databricks MemCurrent** |
| :--- | :--- | :--- |
| **Primary Philosophy** | Deterministic, file-backed claim register for multi-tool developer workflows | 3-tier managed memory architecture for enterprise Lakehouse agents |
| **Target Workload** | Software engineering agents (Cursor, Claude Code, Terminal) | Enterprise business data, SQL agents, customer workflow bots |
| **Event Bus (Episodic)** | `phase0/events.jsonl` (Append-only raw interaction log) | Managed Sessions (Append-only turn ledger with `actor_id` & `session_id`) |
| **Consolidation Pipeline** | `phase0/extractor.py` + `phase0/auditor.py` | Offline "Dreaming" Pipeline (Background LLM scheduled jobs) |
| **Verification Substrate** | **Deterministic Python code** (SHA-256 hashes, git objects, AST, live sockets) | **LLM Reasoning** (LLM reads, compares, deduplicates, and resolves conflicts) |
| **Active Memory View** | `MEMORY.md` (<30 lines, markdown) + `claims_register.md` | Managed Memory index in **Lakebase** (Managed PostgreSQL) |
| **Conflict & Staleness Strategy** | **Applicability Gate**: Preconditions must match; clashing rules quarantined | Newer conversations overwrite older contradicted facts |
| **Interface / Protocol** | **Native Model Context Protocol (MCP 2.x)** on `stdio` + CLI runner | Automatic SDK Plugins + Agent Tools (`recall`, `remember`, `forget`) |
| **Infrastructure & Cost** | **Zero cloud dependencies, 100% local, $0** | Databricks Lakehouse Cloud Platform ($$$ enterprise subscription) |

---

## 2. Three Concrete Improvements to Lift from MemCurrent into Ghostkeep

1. **Standardized Memory Tools in MCP Server:**
   - MemCurrent exposes intuitive primitives: `remember(claim)`, `recall(query)`, `forget(claim_id)`.
   - Ghostkeep can add `remember_claim` and `forget_claim` directly into `mcp_server.py` so agents can propose or retire claims programmatically over stdio.
2. **Session and Branch Scoping:**
   - MemCurrent scopes records by `actor_id` and `session_id`.
   - Ghostkeep can add `session_id` and `git_branch` to `claims.jsonl` so active memory can seamlessly toggle when switching Git branches.
3. **Explicit Sieve Distillation Policy:**
   - MemCurrent guides distillation with rules like *"keep customer preferences, ignore one-off debugging notes"*.
   - Ghostkeep can formalize its extractor heuristics into a user-configurable `sieve_policy.json`.
