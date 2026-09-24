# LongMemEval Memory Optimizations: Roadmap & Blueprint for Ghostkeep

> **Context:** Architectural translation of the ICLR 2025 LongMemEval benchmark optimizations (Value Decomposition, Key Expansion $K=V+\text{fact}$, Temporal Scoping, and JSON + Chain-of-Note Reading) into Ghostkeep's real-time, cross-surface memory engine.

---

## 1. Executive Motivation: Why LongMemEval Matters to Ghostkeep

LongMemEval proves empirically that:
1. **Context stuffing fails:** Models drop 30% to 60% accuracy on long chat histories due to attention dilution ("lost in the middle").
2. **Compressive memory loses critical context:** ChatGPT overwrites facts, while Coze misses indirect signals.
3. **The Reader is a major bottleneck:** 40% to 50% of memory failures happen at the reading/synthesis stage even when the retrieval contains the exact answer.

Ghostkeep's mission is to be the **sub-100ms shared memory bus bridging Terminal CLI (`agy`) and IDE Agents (Cursor, Claude Desktop)**. By applying LongMemEval's four control points, Ghostkeep achieves state-of-the-art recall and reasoning without abandoning its file-backed, git-diffable simplicity.

---

## 2. Ghostkeep Mapping: The 4 Control Points

```
LongMemEval Knob         Ghostkeep Implementation Component
───────────────────────────────────────────────────────────────────────────
CP1: Value Granularity   ──→ Decompose CLI/IDE streams into Execution Rounds
CP2: Key Expansion       ──→ Prepend Scribe facts to raw terminal context (K = V + fact)
CP3: Query Expansion     ──→ Temporal window filter on ISO-8601 timestamps
CP4: Reading Strategy    ──→ Structured JSON MCP responses + Chain-of-Note (CoN)
```

---

## 3. Concrete Optimization Specs for Ghostkeep

### Optimization 1: Store Execution Rounds ($U_i + A_i$)
* **Current State:** Ghostkeep stores extracted atomic `Fact` items in `facts.json`.
* **LongMemEval Finding:** Compressing dialogues purely into atomic facts loses surrounding context, degrading general question answering. Rounds (User prompt + Assistant response) preserve context while keeping items sharp.
* **Ghostkeep Upgrade:**
  - Store execution rounds: `(command/prompt, output/summary)`.
  - Link atomic facts directly to their parent execution round via `source_round_id`.
  - Fast-path queries fetch the compact canonical fact; deep investigative queries (e.g. debugging a build crash) pull the full execution round.

### Optimization 2: Key Expansion via Index-Merging ($K = V + \text{fact}$)
* **LongMemEval Finding:** Concatenating extracted facts to the front of the raw round before indexing yields **+9.4% Recall@k** and **+5.4% QA accuracy**. Rank-merging separate indices failed; single-key index-merging won.
* **Ghostkeep Implementation in `sieve.py` / `scribe.py`:**
  When Ghostkeep ingests terminal outputs or agent tool logs:
  ```python
  # Construct search key via document expansion
  canonical_claim = scribe.distill_claim(raw_output)
  search_key = f"[Fact: {canonical_claim}] {raw_output}"
  ```
  This enables search to hit either the clean, normalized statement or the raw command output/error trace without maintaining multiple fragmented databases.

### Optimization 3: Time-Aware Metadata Query Scoping
* **LongMemEval Finding:** Inferring date ranges for time-sensitive queries improves recall by **+11.3%**.
* **Ghostkeep Implementation:**
  - Ghostkeep already records exact UTC timestamps on every fact (`timestamp`).
  - When an agent calls `ghostkeep_recall_facts(query="What database port did we configure yesterday?", time_range={"since": "2026-09-23T00:00:00Z"})`, Ghostkeep applies a deterministic temporal filter **before** text or keyword matching.
  - Eliminates false positive collisions from past project sessions weeks ago.

### Optimization 4: Structured JSON Context + Chain-of-Note (CoN)
* **LongMemEval Finding:** Formatting recalled memory as JSON and enforcing an extract-before-reasoning note-taking phase prevents the reader LLM from hallucinating or misreading complex context.
* **Ghostkeep MCP Server Design (`server.py`):**
  - All MCP recall tools (`ghostkeep_recall_facts`, `ghostkeep_get_conflicts`, `ghostkeep_query_provenance`) must output strict, typed JSON arrays rather than prose markdown.
  - In Ghostkeep's MCP server instructions / prompt injection:
    > *"When reasoning over recalled Ghostkeep facts, first extract the relevant evidence statements into brief notes, then reason over those notes to formulate your action."*

### Optimization 5: Abstention & Anti-Hallucination Gate
* **LongMemEval Finding:** Memory systems must learn to say *"I don't know / You never mentioned that"* when presented with false premises.
* **Ghostkeep Implementation:**
  - If a query checks for an unverified environment condition (e.g., *"What is our Redis production password?"*) and no fact exists in `facts.json`, Ghostkeep explicitly returns `status: "unknown"` with an abstention flag, preventing downstream agents from hallucinating dummy credentials.

---

## 4. Implementation Phasing in Ghostkeep

| Phase | Milestone | Files Modified |
| :--- | :--- | :--- |
| **Phase 1** | **Structured JSON & CoN Prompts** | `ghostkeep/server.py` (MCP tool return formats) |
| **Phase 2** | **Document Key Expansion ($K=V+\text{fact}$)** | `ghostkeep/scribe.py`, `ghostkeep/store.py` |
| **Phase 3** | **Time-Aware Range Filtering** | `ghostkeep/store.py` (`recall_facts` time filters) |
| **Phase 4** | **Execution Round Storage** | `ghostkeep/models.py`, `facts.json` / `rounds.jsonl` |
