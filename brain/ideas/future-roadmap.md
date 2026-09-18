# Future Ideas & Architectural Roadmap

Potential future directions, research questions, and experimental extensions for Ghostkeep.

---

## 1. 🔍 Advanced Conflict Resolution & Semantic Diffing

Currently, `_detect_conflict` uses character-level sequence matching (`difflib.SequenceMatcher`).
- **AST / Code Diffing**: When facts describe code snippets, API endpoints, or database schemas, invoke an AST-aware or structural diff instead of raw string matching.
- **Negation & Contradiction Detection**: Integrate a tiny local NLI (Natural Language Inference) model (or an optional LLM prompt) that distinguishes "complementary detail" from "direct contradiction" (e.g. *"Use Python 3.11"* vs *"Use Python 3.12"*).

---

## 2. ⏳ Temporal Confidence Decay & Reinforcement

Facts that are neither verified nor queried over long periods should naturally lose priority:
- **Decay Function**: Implement exponential or linear confidence decay for dynamic facts (e.g. temporary debug configurations), while marking canonical architectural decisions with an `immutable` or `pinned` flag.
- **Access Reinforcement**: Every time an agent queries and uses a fact without contesting it, increase its confidence score slightly (Hebbian reinforcement in agent memory).

---

## 3. 🗳️ Multi-Agent Consensus & Voting

When more than two agents disagree:
- Support voting protocols where multiple agents can cast attestations on a fact.
- Weight votes by agent domain expertise (e.g., security agent has higher voting power on auth decisions than a documentation agent).

---

## 4. 🗄️ Optional SQLite / Embedded Storage Backend

For massive deployments (>50,000 facts):
- Provide an optional drop-in SQLite storage backend with Write-Ahead Logging (WAL) and Full-Text Search (FTS5).
- Keep plain JSON export as a first-class feature so portability and git diffs are never lost.

---

## 5. 🌐 Webhook / PubSub Notifications

- Fire events over local WebSockets or HTTP webhooks whenever a conflict is detected.
- Allows real-time desktop notifications in IDEs or developer dashboards.

---

## Related Notes
- [[provenance-tracking]] — Foundation for confidence updates.
- [[conflict-detection-and-resolution]] — Enhancing the contradiction engine.
- [[ghostkeep-and-dreamkeeper]] — Coordinating background updates.
