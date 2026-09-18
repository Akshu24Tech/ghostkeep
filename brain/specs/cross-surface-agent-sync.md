# Problem Spec: Cross-Surface Agent Amnesia (Terminal vs. IDE)

> **"I am using the same account and Gemini Antigravity, but the chat in the terminal (`agy`) and the chat in the IDE agent don't know what is happening in each other."**

---

## 1. The Core Problem: Two Minds, One Workspace

When developing with modern AI agent toolchains (specifically **Gemini Antigravity**), developers work across two distinct execution surfaces simultaneously:

```
                  ┌─────────────────────────────────────┐
                  │          DEVELOPER (USER)           │
                  └──────────┬───────────────┬──────────┘
                             │               │
                             ▼               ▼
                   ┌─────────────────┐ ┌─────────────────┐
                   │  Terminal CLI   │ │    IDE Agent    │
                   │ (`agy` session) │ │ (Pair Assistant)│
                   └────────┬────────┘ └────────┬────────┘
                            │                   │
                            ▼                   ▼
                   ┌─────────────────┐ ┌─────────────────┐
                   │ Siloed CLI Log  │ │ Siloed IDE Log  │
                   │ (antigravity-   │ │ (antigravity-   │
                   │      cli)       │ │      ide)       │
                   └─────────────────┘ └─────────────────┘
                            ▲                   ▲
                            │                   │
                            └─── NO BRIDGE ─────┘
                             (Cognitive Amnesia)
```

### The Real-World Friction
1. **Redundant Explanations**: You ask the terminal CLI agent to run a 45-minute migration or benchmark. When you switch to the IDE agent to write the frontend, you have to manually copy-paste terminal outputs and explain what CLI did.
2. **Conflicting Edits**: Terminal CLI refactors a module while the IDE agent generates code assuming the old module layout. Both make valid local decisions that clash globally.
3. **Lost Intent & Decisions**: Terminal agent chooses a specific library version due to an error it encountered during a build. IDE agent later tries to upgrade or revert it because it doesn't know *why* the terminal agent made that choice.
4. **Context Fracturing**: Even though both tools run on the same machine, under the same Google account, in the exact same workspace repo, they are completely deaf and blind to each other.

---

## 2. Technical Root Cause

Both surfaces maintain isolated state directories:
- **CLI Agent State**: `~/.gemini/antigravity-cli/brain/<conversation-id>/`
- **IDE Agent State**: `~/.gemini/antigravity-ide/brain/<conversation-id>/`

There is no shared communication bus, no shared event ledger, and no unified provenance memory. Each conversation ID is an island.

---

## 3. The Ghostkeep Solution

Ghostkeep acts as the **Unified Central Nervous System** between the Terminal CLI and the IDE Agent.

```
 ┌─────────────────────────────────────────────────────────────┐
 │                     SAME REPOSITORY                         │
 │                                                             │
 │  ┌───────────────────────┐       ┌───────────────────────┐  │
 │  │      Terminal CLI     │       │       IDE Agent       │  │
 │  │      (`agy` run)      │       │     (Antigravity)     │  │
 │  └───────────┬───────────┘       └───────────┬───────────┘  │
 │              │ (writes fact/event)           │              │
 │              ▼                               ▼              │
 │  ┌───────────────────────────────────────────────────────┐  │
 │  │                   GHOSTKEEP BUS                       │  │
 │  │             Shared Memory & Provenance                │  │
 │  ├───────────────────────────────────────────────────────┤  │
 │  │ • facts.json         : Active decisions & knowledge   │  │
 │  │ • provenance.jsonl   : Real-time action audit trail   │  │
 │  │ • conflicts.json     : Disagreements flagged live     │  │
 │  └───────────────────────────────────────────────────────┘  │
 │              ▲                               ▲              │
 │              │ (reads cross-surface context) │              │
 │              └───────────────────────────────┘              │
 └─────────────────────────────────────────────────────────────┘
```

### How It Works:
1. **Provenance-Tagged Events**:
   - When terminal CLI finishes a step (e.g., installs a package, tests an API, fixes a compile error), it records a memory to Ghostkeep:
     ```json
     {
       "content": "Upgraded pydantic to 2.10 due to FastAPI 0.115 compatibility in terminal",
       "source_agent": "antigravity-cli",
       "source_session_id": "cli-sess-92",
       "confidence": 1.0,
       "tags": ["dependency", "fastapi", "terminal-action"]
     }
     ```
2. **Context Querying on Wakeup**:
   - When you switch to the IDE Agent and send a prompt, the IDE agent queries Ghostkeep:
     `search_memory(source_agent="antigravity-cli")` or `get_recent_cross_surface_activity()`.
   - The IDE agent instantly knows: *"Ah, terminal CLI just finished the backend migration and upgraded Pydantic. I don't need to ask the user."*
3. **Cross-Surface Conflict Detection**:
   - If IDE agent proposes changing an architectural pattern that terminal CLI just committed for a specific reason, Ghostkeep surfaces a conflict before the IDE writes code:
     `"Conflict detected: Terminal CLI chose SQLite for local testing 10 minutes ago, but IDE agent is proposing PostgreSQL."`

---

## 4. First Milestone: Concrete Implementation Plan

To solve this specific problem step-by-step, we build:

### Step 1: The Cross-Surface Schema
Define a standardized event format for session handoffs:
- `event_type`: `tool_execution`, `architectural_decision`, `test_result`, `blocker_encountered`.
- `surface`: `terminal` vs. `ide`.
- `workspace_root`: Anchor events to the project directory path.

### Step 2: The MCP Bridge
Both Terminal (`agy`) and IDE agent connect to the Ghostkeep MCP server:
- Terminal agent calls `ghostkeep.add_memory(...)` at the end of key tasks or milestones.
- IDE agent calls `ghostkeep.search_memory(...)` or reads the shared ledger before planning.

### Step 3: Passive Sync / Transcript Watcher (Zero Manual Effort)
To make it completely automatic without relying on manual agent prompts:
- A lightweight watcher script reads the JSONL transcript log of `antigravity-cli` in the background.
- Whenever `antigravity-cli` concludes a task or writes code, the watcher extracts the summary and pushes it into Ghostkeep.
- The IDE agent immediately has access to the terminal's brain in real time!

---

## 5. Why This Shapes Ghostkeep into a Killer Product

1. **Solves an immediate, acute pain point**: Every developer using modern agent CLIs + IDEs experiences this exact amnesia every day.
2. **Proves the Provenance model**: Ghostkeep isn't just storing static notes; it is tracking *who did what, where, and why* across surfaces.
3. **Foundation for multi-agent workflows**: Once Terminal and IDE can communicate, extending this to background cron agents, GitHub Action bots, and phone agents is trivial.

---

## Related Notes
- [[Index]] — Back to Map of Content.
- [[provenance-tracking]] — The underlying lineage model.
- [[conflict-detection-and-resolution]] — Preventing terminal vs IDE code collisions.
- [[mcp-memory-protocol]] — How MCP facilitates cross-surface access.
