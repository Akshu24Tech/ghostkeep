# Conflict Detection and Resolution

> **Core rule:** Conflicting facts are never silently overwritten.

When multiple autonomous agents (e.g., an architect agent, a developer agent, and a user in chat) interact with the same project, contradiction is inevitable.

In existing memory systems, one of two bad things happens:
1. **Silent Overwrite (Last-Write-Wins)**: The newest write stomps over the old fact, wiping out institutional context.
2. **Duplicate Accumulation**: Both contradictory facts are saved alongside each other, causing the agent to hallucinate or vacillate between incompatible directives.

Ghostkeep introduces an explicit **Conflict Lifecycle**.

---

## Detection Phase

When `add_memory` is invoked:
1. The store checks existing active facts from **different** `source_agent`s.
2. If text overlap exceeds the `SIMILARITY_THRESHOLD` (default: `0.72`) but is not identical (`< 0.97`), Ghostkeep flags a **conflict**.
3. Both facts are tagged with `status: "conflicted"`.
4. A new record is inserted into `conflicts.json`.
5. An event `conflict_detected` is appended to `provenance.jsonl`.

```
Fact A: "Primary database backend is PostgreSQL 16 on AWS Aurora" (Agent: Architect)
Fact B: "Primary database backend is MySQL 8 on AWS" (Agent: Developer)
                           │
                           ▼ Similarity ~ 0.86
                    ┌─────────────┐
                    │  CONFLICT!  │
                    └──────┬──────┘
                           ▼
          Staged in conflicts.json until resolved
```

---

## Resolution Strategies

Conflicts must be explicitly resolved through `resolve_conflict(conflict_id, resolution, resolved_by)`.

Ghostkeep supports three deterministic resolution primitives:

| Strategy | Description | Resulting State |
|---|---|---|
| `keep_a` | Fact A is retained as the winner. | Fact A becomes `active`; Fact B becomes `superseded` (`superseded_by: Fact_A`). |
| `keep_b` | Fact B is retained as the winner. | Fact B becomes `active`; Fact A becomes `superseded` (`superseded_by: Fact_B`). |
| `merge:<new text>` | Both facts are synthesized into a new canonical statement. | A new `Fact` is created with combined provenance (`derived_from: Fact_A`); both A and B become `superseded`. |

### Immutable Audit Trail
Resolving a conflict never erases the contradicted facts. Instead:
- Facts are marked `status = "superseded"` with a pointer to `superseded_by`.
- Two `resolved` events are logged into `provenance.jsonl` recording who authorized the resolution, the timestamp, and the rationale.

---

## Related Notes
- [[provenance-tracking]] — The historical record of resolutions.
- [[lifecycle-of-a-fact]] — How facts transition between active, conflicted, and superseded states.
- [[ghostkeep-and-dreamkeeper]] — Automated background resolution passes via DreamKeeper.
