# Provenance Tracking in Agent Memory

> **Key question:** *"Why is this fact what it is?"*

In standard AI memory systems, once a memory is stored, all historical lineage is severed. A fact like `"User prefers Tailwind CSS"` floats in vector space with no record of:
- Which agent or model generated it
- Which conversation or prompt session triggered it
- How confident the agent was at the moment of recording
- Whether it was a direct user quote or an inferred synthesis from another fact

**Provenance** is the cryptographic and logical audit trail of origin, derivation, and custody.

---

## The Provenance Data Model

Ghostkeep implements a lightweight lineage model inspired by W3C PROV:

```
                  ┌───────────────────────┐
                  │      source_agent     │ (e.g. claude-code)
                  └──────────┬────────────┘
                             │ writes
                             ▼
 ┌───────────────┐     ┌───────────┐     ┌───────────────────────┐
 │ derived_from  ├────►│   FACT    │◄────┤   source_session_id   │
 │ (Parent Fact) │     └─────┬─────┘     │ (Traceable execution) │
 └───────────────┘           │           └───────────────────────┘
                             │ emits
                             ▼
                  ┌───────────────────────┐
                  │    ProvenanceEvent    │ (created, conflicted, resolved)
                  └───────────────────────┘
```

### 1. `Fact` Entities
Every fact carries:
- `source_agent`: The exact client or agent persona (`"claude-chat"`, `"cursor"`, `"gemini-cli"`, `"devops-bot"`).
- `source_session_id`: Unique correlation ID linking back to the raw conversation logs or prompt trace.
- `confidence`: Calibrated score between `0.0` (hypothetical / weak inference) and `1.0` (explicit user directive).
- `derived_from`: Pointer to the antecedent fact ID, enabling recursive ancestor walks (`derivation_chain`).

### 2. `ProvenanceEvent` Ledger
Every lifecycle touchpoint generates an immutable event appended to `provenance.jsonl`:
- `created`: Fact creation stamped with actor and timestamp.
- `conflict_detected`: Automatic warning when an overlapping fact from another agent is detected.
- `resolved`: Complete audit record of how a conflict was settled, by whom, and what the resulting state is.

---

## The `get_provenance(fact_id)` Call

When an agent or human reviewer asks about a fact, Ghostkeep returns:
1. The fact payload.
2. The complete chronological sequence of `ProvenanceEvent`s that have touched it.
3. The recursive `derivation_chain`, tracing parent facts until the root observation is reached.

---

## Related Notes
- [[vectorless-memory]] — Why human-readable JSON files are essential for provenance.
- [[conflict-detection-and-resolution]] — Handling divergence between multiple agent observations.
- [[storage-engine]] — How events are appended to `provenance.jsonl`.
