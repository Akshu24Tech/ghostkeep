# Vectorless Memory

> **Key premise:** Plain files are the source of truth. No vector database or embedding model is required to trust a fact.

Most modern agent frameworks immediately reach for vector databases (Chroma, Pinecone, Qdrant, Milvus) for memory. While vector similarity is useful for semantic retrieval over millions of unstructured documents, it introduces significant downsides when used as the primary ledger for agent state.

---

## Why Vector-First Memory Fails for Agent Facts

1. **Opaque Ground Truth**
   - High-dimensional vector embeddings are black boxes. You cannot inspect an embedding array in Git, run `git diff`, or explain why `cosine_similarity(q, f) = 0.81` triggered a critical decision.
2. **Embedding Drift & Version Lock**
   - When an embedding model is updated (e.g. `text-embedding-3-small` vs `ada-002` or local Ollama models), all previously computed vector coordinates become invalid or require a full, costly re-indexing pass.
3. **Loss of Determinism & Auditing**
   - In safety-critical or enterprise agent setups, you need deterministic lookups: *"Did the user explicitly instruct us to never use AWS Cognito?"* Fuzzy vector matching often buries direct negative constraints.
4. **Operational Overhead**
   - Vector databases require running daemon services, managing index partitions, network roundtrips, and handling client dependencies.

---

## The Ghostkeep Approach

```
┌─────────────────────────────────────────────────────────────┐
│                    GHOSTKEEP PHILOSOPHY                     │
│                                                             │
│   Human-Readable JSON  ───► Git-Diffable & Traceable        │
│   Fast In-Memory Match ───► Sub-millisecond local recall    │
│   Direct Fact Registry ───► Deterministic ID lookups        │
│   Optional Embeddings  ───► Pluggable auxiliary index only  │
└─────────────────────────────────────────────────────────────┘
```

- **Storage as Plain Files**: `facts.json`, `conflicts.json`, and `provenance.jsonl` can be inspected in VS Code, committed to git, or verified in shell scripts using `jq`.
- **Lexical & Substring Matching**: Built-in sequence matching (`difflib.SequenceMatcher`) provides robust local recall without external network calls or GPU dependencies.
- **Zero Cost & Zero Cold Start**: Zero API tokens required for fact insertion, indexing, or verification.

---

## Related Notes
- [[provenance-tracking]] — Tracing origin without opaque vectors.
- [[storage-engine]] — Details on the file-based persistence format.
- [[ghostkeep-vs-traditional-memory]] — Benchmarking against vector memory frameworks.
