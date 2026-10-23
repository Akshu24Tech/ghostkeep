# Ghostkeep & Google Cloud Knowledge Catalog: Enterprise vs. Local Context Engines

> **Context:** On October 22, 2026, Google Cloud announced the transformation of Knowledge Catalog into an "Always-On Context Engine" featuring self-learning enrichment agents, trace mining, and IAM-governed Context Sets served over MCP.
> **Significance:** Google's enterprise architecture directly validates the core thesis and mechanics of Ghostkeep.

---

## 1. Convergence on the Same Core Problem

Whether at Google Cloud enterprise scale (BigQuery, SAP, Spanner) or local developer scale (Cursor, Gemini CLI, Claude Code), AI agents hit the exact same failure mode:

> **"Without trusted context, AI agents are forced to guess definitions and hunt through raw schemas — leading to slow responses, high token costs, and inaccurate answers."**

Traditional solutions fail:
- **Dumping raw schemas / full transcripts into prompts:** Causes prompt degradation, token exhaustion, and 45-second latency.
- **Naive Vector Search:** Embeddings confuse similar-sounding column names, fail on exact business formulas, and cannot handle temporal updates (e.g., changes to accounting or coding rules).
- **Manual Documentation:** Developers and data stewards never have time to document every table, rule, or constraint by hand.

---

## 2. Architectural Comparison

| Architectural Function | Google Cloud Knowledge Catalog (Enterprise) | Ghostkeep Memory Engine (Local / Developer) |
|---|---|---|
| **Data Scope** | Multi-cloud data lakes (BigQuery, Spanner, SAP, dbt, Looker) | Local codebases, monorepos, git worktrees, toolchain sessions |
| **Trace Mining** | Self-Learning Agent crawls Gemini Enterprise and BigQuery interaction traces | Sieve parses `antigravity-cli` and IDE conversation logs (`transcript.jsonl`) |
| **Ground Truth Store** | BigQuery Context Graph | Plain-text, vectorless `facts.json` |
| **Conflict Handling** | Confidence score gating + Steward Review Change Requests | Conflict staging queue (`conflicts.json`); zero silent overwrites |
| **Audit & Lineage** | Cloud IAM + versioned Change Requests with diffs | Append-only W3C-PROV ledger (`provenance.jsonl`) with recursive ancestor chains |
| **Standard Format** | Open Knowledge Format (OKF) bundles | Git-diffable JSON / markdown files |
| **Delivery Protocol** | Cloud Model Context Protocol (MCP) & Search APIs | Local MCP Server (`server.py`) with stdio / SSE transport |
| **Benchmark Gains** | Up to 4x accuracy, 33% lower latency, 75% fewer tokens, 67% fewer tool calls | Zero prompt token bloat during normal execution; sub-10ms deterministic recall |

---

## 3. Why This Matters for Ghostkeep's Design

1. **Validation of Vectorless Fact Grounding:**
   Google did not solve enterprise agent grounding by throwing everything into a massive vector database. They built a **semantic graph with golden formulas, explicit join logic, and scoped Context Sets**. This strongly affirms Ghostkeep's vectorless design choice for codebases and developer intent.
2. **Trace Mining as the Capture Mechanism:**
   Ghostkeep's Sieve approach (passively listening to agent terminal and IDE logs) matches Google's "Self-Learning Enrichment Agent" mining agent interaction traces. Instead of asking developers to manually type `add_memory`, the engine extracts facts from real execution friction.
3. **Context Sets & Task Scoping:**
   Just as Google partitions the graph into "Sales" and "Finance" context sets to prevent collisions, Ghostkeep scopes facts by project, repository root, and category to prevent multi-agent drift across worktrees.

---

## Related Notes
- [[mcp-memory-protocol]] — How Ghostkeep exposes its memory bus over MCP.
- [[vectorless-memory]] — Why file-backed stores outperform vector DBs for ground truth.
- [[conflict-detection-and-resolution]] — Staging multi-agent contradictions without silent overwrites.
- [[closed-loop-sdlc-with-ghostkeep]] — Running parallel worktrees and retrospectives with Ghostkeep.
