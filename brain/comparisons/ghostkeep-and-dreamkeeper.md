# Ghostkeep and DreamKeeper: Sibling Ecosystem

How Ghostkeep and [DreamKeeper](https://github.com/Akshu24Tech/dreamkeeper) work together as a complete agent memory stack.

---

## Separation of Concerns

```
┌─────────────────────────────────────────────────────────────┐
│                    THE COMPLETE MEMORY STACK                │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                     GHOSTKEEP                       │   │
│   │                 (The Real-Time Ledger)              │   │
│   │  • Primary source of truth                          │   │
│   │  • Fast, deterministic reads & writes via MCP       │   │
│   │  • Real-time conflict detection                     │   │
│   │  • Immutable provenance event log                   │   │
│   └──────────────────────────┬──────────────────────────┘   │
│                              │                              │
│                    (Scheduled Dream Pass)                   │
│                              ▼                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                    DREAMKEEPER                      │   │
│   │            (The Background Consolidation)           │   │
│   │  • Scans stored facts for subtle semantic clusters   │   │
│   │  • LangGraph workflow: Scan -> Plan -> Synthesize   │   │
│   │  • Generates high-order synthesis & merges          │   │
│   │  • Submits resolutions back to Ghostkeep            │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Synergy Highlights

1. **Ghostkeep as the Memory Bus**:
   - Live agents (Claude, Cursor, Windsurf) read and write to Ghostkeep in milliseconds during active coding and reasoning sessions.
   - Ghostkeep prevents data loss and tracks every edit.
2. **DreamKeeper as the Dream Cycle**:
   - Runs periodically (e.g. overnight or when idle).
   - Scans Ghostkeep's `facts.json` and pending `conflicts.json`.
   - Uses an LLM pass to synthesize sprawling facts into concise rules.
   - Calls `resolve_conflict` with `merge:<consolidated text>` or updates status, preserving full historical provenance.
3. **Auditability Throughout**:
   - When DreamKeeper modifies or supersedes memories, it identifies itself as `source_agent: "dreamkeeper"` and leaves an unerasable trail in `provenance.jsonl`.

---

## Related Notes
- [[conflict-detection-and-resolution]] — Resolution primitives utilized by DreamKeeper.
- [[lifecycle-of-a-fact]] — How consolidation updates fact state.
- [[storage-engine]] — The file storage format inspected by DreamKeeper.
