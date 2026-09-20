# Jev & System One Decision Architecture

> **The Breakthrough:** Why generating words is the wrong primitive for memory gates, conflict detection, and agent state machines.

In September 2026, **TypeSafe AI** (founded by former OpenAI researcher and RLHF co-inventor **Diogo Almeida**) released **Jev**, introducing the world's first **non-autoregressive "System One" AI model**.

Ghostkeep incorporates the Jev philosophy directly into its memory and provenance design.

---

## ⚡ The Architectural Problem: Generative LLMs are Too Slow for Memory

Every autonomous agent has dozens of micro-decision points per minute:
- *"Does this observation contain a durable decision or is it ephemeral chatter?"*
- *"Does Fact B contradict Fact A?"*
- *"Is this new statement superseding the old one or adding complementary detail?"*
- *"How confident should we be in this fact?"*

When developers use frontier generative models (Claude Sonnet, GPT-4o, Gemini 2.5 Flash) for these checks, the system suffers:
1. **The Latency Tax**: A 2-to-5 second delay on every turn while the model attends to past tokens and streams JSON.
2. **Economic Waste**: Paying $3.00 to $15.00 per million tokens for simple boolean and categorical checks.
3. **Hallucinated Confidence**: Standard LLMs cannot accurately calibrate their own certainty; they suffer from polite overconfidence.

---

## 🎯 The Jev Revolution: Non-Autoregressive RLCD

Jev operates as a **System One** reflex engine:

```
                  ┌─────────────────────────────────────┐
                  │              INPUT STATE            │
                  │   (Agent transcript turn / Facts)   │
                  └──────────────────┬──────────────────┘
                                     │
                                     ▼
                  ┌─────────────────────────────────────┐
                  │             JEV ENGINE              │
                  │       (Single Forward Pass)         │
                  ├─────────────────────────────────────┤
                  │ • Evaluates all questions in //     │
                  │ • Latency: 70ms – 300ms             │
                  │ • Cost: $0.042 / 1M tokens ($0 out) │
                  └──────────────────┬──────────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          ▼                          ▼                          ▼
  ┌───────────────┐          ┌───────────────┐          ┌───────────────┐
  │     NOUL      │          │    CHOICE     │          │     SCORE     │
  │ (Boolean 0-1) │          │(Categorization│          │ (Ordinal 1-5) │
  └───────────────┘          └───────────────┘          └───────────────┘
```

### 1. Non-Autoregressive Execution
Unlike standard LLMs that generate token-by-token, Jev processes the full input context and evaluates all criteria in a **single forward pass**. Output is typed, immediate, and free from JSON formatting errors.

### 2. RLCD (Reinforcement Learning from Calibrated Decisions)
Instead of RLHF (which trains models to be conversational and agreeable), Jev is trained with **RLCD**:
- When Jev returns a `Noul` probability of `0.92`, that outcome is statistically true 92% of the time across empirical validation sets.
- In Ghostkeep, this provides a **statistically calibrated `confidence` score** on every stored fact, replacing arbitrary human or agent guesswork.

---

## 🧩 The Three Primitives in Memory Management

| Primitive | Memory Application | Example Question |
|---|---|---|
| **`Noul`** | **Deduplication & Conflict Detection** | `"Does Fact B contradict or invalidate Fact A?"` |
| **`Choice`** | **Taxonomy & Domain Routing** | `"What domain does this fact belong to? [auth, database, ui, devops, preferences]"` |
| **`Score`** | **Durable Importance & Decay Weight** | `"Rate the permanence of this constraint: ['ephemeral', 'session_only', 'durable', 'immutable']"` |

---

## 🔗 Related Notes
- [[vectorless-memory]] — Plain files combined with System One micro-decisions.
- [[provenance-tracking]] — Capturing calibrated confidence in the provenance record.
- [[jev-powered-ambient-sieve]] — How Jev powers the real-time Terminal (`agy`) to IDE memory bridge.
- [[conflict-detection-and-resolution]] — Replacing naive text diffing with calibrated semantic contradiction checks.
