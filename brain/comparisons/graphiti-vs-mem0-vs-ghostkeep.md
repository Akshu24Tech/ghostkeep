# Ghostkeep vs Graphiti vs Mem0: Write Paths, Latency & Benchmark Realities

> **Context:** Architectural comparison evaluating how Ghostkeep's 3-Tier Sieve contrasts with Graphiti's knowledge graph pipeline (`add_episode`), Mem0's entity-linking rewrite, and the empirical truth behind LLM memory benchmarks.

---

## 1. High-Level Comparison Matrix

| Architectural Feature | **Ghostkeep** | **Graphiti (Zep)** | **Mem0 (v3)** |
| :--- | :--- | :--- | :--- |
| **Primary Philosophy** | Sub-100ms real-time execution bus (Terminal $\leftrightarrow$ IDE) | Bi-temporal knowledge graph with episodic extraction | Token-efficient hybrid memory (<7k tokens) + background Dream |
| **Write Path Latency** | **70 – 100 ms** (instant) | **2,000 – 5,000 ms** (multi-call LLM pipeline) | **800 – 1,200 ms** (single-pass extraction) |
| **Write Path Stages** | Sieve (Jev/Regex) $\to$ Scribe $\to$ Vault | Extract $\to$ Entity Res $\to$ Edge Dedup $\to$ Contradiction | Single-pass ADD $\to$ SQLite/Vector/Entity stores |
| **Graph Mechanism** | Vectorless, human-readable JSON facts | Neo4j property graph with dynamic edge updates | **Dropped graph traversal**; uses flat spaCy entity linking |
| **Contradiction Strategy** | Explicit quarantine in `conflicts.json` | Bi-temporal expiration (`expired_at`) on old edges | Background Dream pass (`supersede_facts`) |
| **Protocol / Interface** | **Native MCP stdio** + CLI | REST API / Python SDK | REST API / Python SDK / MCP |
| **Storage Substrate** | Git-diffable JSON / JSONL | Neo4j + Vector DB | SQLite + Qdrant/pgvector + Entity Store |

---

## 2. Deconstructing the Write Paths

### Graphiti: The Synchronous 4-Stage Tax
Inside Graphiti's `add_episode`:
1. **Extraction:** LLM extracts entities and relational facts.
2. **Entity Resolution:** MinHash + LSH fuzzy check $\to$ LLM fallback if ambiguous.
3. **Edge Deduplication:** Checks if relational fact exists.
4. **Contradiction Resolution:** Stamped with `expired_at` (bi-temporal closing).

**The Reality:** Every single write can trigger **2 to 4 separate LLM calls**. While excellent for deep biographical retention, this write amplification freezes interactive developer sessions (CLI terminal execution).

### Mem0: Why They Dropped Graph Traversal
Mem0's internal benchmarks (arXiv:2504.19413) proved that a full property graph:
* Ran **3x slower** than non-graph alternatives.
* Cost **2x more in tokens**.
* Lost on simple single-fact recall **and** complex multi-step reasoning.
* Only marginally won on time-based queries.

Mem0 consequently abandoned Neo4j graph traversal for **spaCy entity linking**—a flat, lightweight lookup table.

### Ghostkeep: The 3-Tier Asymmetric Sieve
Ghostkeep handles high-velocity developer commands by splitting memory into two speeds:
* **Tier 1 (Sieve):** Discards 90% conversational noise and terminal garbage in **<80ms** via non-autoregressive Jev or deterministic regex.
* **Tier 2 (Scribe):** Normalizes surviving signals into 1-sentence canonical claims.
* **Tier 3 (Vault):** Commits to human-readable `facts.json` or quarantines conflicting assertions into `conflicts.json`.

---

## 3. The Benchmark Skepticism Guide

Leaderboard claims (e.g. 92.5% on LOCOMO) dominate commercial memory marketing. Here is why Ghostkeep rejects raw leaderboard numbers as validation:

1. **LLM-as-Judge Bias:** Vendors grade their own benchmarks using proprietary prompts and handpicked models.
2. **Model Sensitivity:** Independent studies (Continua AI) demonstrated that merely switching the judge model from GPT-4o-mini to GPT-4.1-mini shifted scores by **~10 points** across all architectures without a single code change.
3. **Short-Context Fallacy:** The standard LOCOMO benchmark tests conversations spanning only 16k–26k tokens. Modern LLMs can hold this entire history in their native working context window, completely bypassing the memory store.
4. **Public Feuds:** Zep (Graphiti) published *"Lies, Damn Lies & Statistics"* directly attacking Mem0's benchmark configurations.

**Ghostkeep's Verification Stance:** True memory quality is validated by **architectural invariants**:
* Zero silent overwrites.
* Sub-100ms write latency.
* Git-diffable transparent state.
* Deterministic conflict quarantine.

---

## 4. The Unified Blueprint: Ghostkeep + Decision Provenance Agent

Instead of choosing between fast writes (Ghostkeep) and deep causal reasoning (Graphiti/DPA), Ghostkeep pairs with `decision_provenance_agent`:

1. **Ghostkeep handles the hot loop:** Captures terminal keystrokes, environment state, and tool executions in <100ms.
2. **Conflict Escalation:** When Ghostkeep flags a collision in `conflicts.json`, it triggers `decision_provenance_agent` asynchronously.
3. **Semantic Diff & Causal Lineage:** DPA uses Gemini Flash to determine the `ChangeTrigger` (`new evidence`, `correction`, `constraint change`), updating the fact lineage without blocking the developer's CLI.
