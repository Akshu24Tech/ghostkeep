# Shared Agent Memory (working title)

One project memory that every AI agent can read and write: IDE agents, terminal CLIs, Gemini CLI, Antigravity, and more.

Author: Ghost (Akshu Grewal) | Started: 2026-10-06 | Status: Planning done, Phase 0 files ready in phase0/

---

## 1. The idea (simple version)

When I work on one project, I talk to many different agents: one in the IDE, one in the terminal, another CLI, the Antigravity agent panel. Each keeps its own memory in its own place. None of them knows what the others did.

I want **one shared memory per project**, filled **automatically**, so any agent I open already knows what was done, what was decided, and what is still pending.

---

## 2. The problem

| Problem | What happens today |
|---|---|
| Memory is split | Each tool stores context in its own folder or format |
| I repeat myself | I re-explain the project every time I switch agents |
| Agents disagree | Agent A remembers an old decision, Agent B remembers the new one |
| Memory only grows | Old, useless notes pile up and pollute context |
| Manual saving fails | If I have to say "remember this", I forget to do it |

---

## 3. The solution (in plain words)

Three parts:

1. **The diary (log).** Every agent adds a line: what happened, which agent, what time. Old lines are never edited. This is the real memory.
2. **The cleaner (Decision Provenance Agent).** On a schedule, it reads the diary, picks out decisions and facts, links them together, and marks old ones as replaced.
3. **The view (Obsidian vault).** The cleaner writes notes with `[[links]]` and timestamps. I can see the graph and edit notes. Agents read from here too.

If the vault breaks, it is rebuilt from the diary.

```
Claude Code ─┐
Gemini CLI  ─┤ hooks / MCP        ┌──────────────┐
Antigravity ─┼──────────────────► │ Capture API  │
Cursor/IDE  ─┘   (what happened)  └──────┬───────┘
                                          ▼
                                 ┌──────────────────┐
                                 │ Append-only log  │  (JSONL / SQLite)
                                 └──────┬───────────┘
                                        ▼  scheduled
                                 ┌──────────────────┐
                                 │ Provenance agent │  Extract → Match → Diff → Store
                                 └──────┬───────────┘
                                        ▼
                                 ┌──────────────────┐
                                 │ Obsidian vault   │  notes + links + timestamps
                                 │ + MEMORY.md      │
                                 └──────┬───────────┘
                                        ▼  read at session start (hook or MCP)
                                    All agents
```

---

### Detailed architecture (v2.1)

```
 Claude Code      Cursor / IDE      Antigravity IDE     Gemini CLI
  (hooks)          (hooks)        (transcript watcher)   (hooks/log)
     │                │                   │                  │
     └────────────────┼───────────────────┼──────────────────┘
                      ▼                   ▼
           ┌─────────────────────────────────────────┐
           │ Capture Daemon / Logbook (Append-Only)  │
           │ events.jsonl - Source of Truth (Ledger) │
           └────────────────────┬────────────────────┘
                                │
                    Extract Claims & Decisions
                                ▼
           ┌─────────────────────────────────────────┐
           │ Claims Engine (3 Claim Kinds)           │
           │ • Verifiable: Tested by Auditor         │
           │ • Decision: Declared by Human (no audit)│
           │ • Preference: Styling & constraints     │
           └────────────────────┬────────────────────┘
                                │
          ┌─────────────────────┴─────────────────────┐
          ▼                                           ▼
┌─────────────────────────────────┐       ┌───────────────────────────────┐
│ Deterministic Auditor (Code)    │       │ Rendered Markdown View        │
│ Tests file hashes, ports, pytest│       │ brain/claims_register.md      │
│ Checked → Stale (on hash change)│       │ brain/MEMORY.md               │
└─────────────────────────────────┘       └───────────────────────────────┘
```

**Core Guarantees in v2.1:**
1. **Append-Only Log is Truth:** Never let multiple agents collide rewriting Markdown. The JSONL log is the database; `claims_register.md` is a generated artifact.
2. **Track C Transcript Watcher:** Background daemon tails Antigravity's live `transcript.jsonl` to capture facts with zero manual prompt habits.
3. **Deterministic Auditor:** The auditor is plain Python code (AST, greps, exit codes), not an LLM grading its own homework.
4. **Change-Based Invalidation:** Evidence stores file hashes. When files change, claims transition from `Checked` → `Stale`.

---

## 4. Key design decisions

- **Log first, notes second.** Append-only log avoids two agents overwriting one file.
- **Facts, not whole chats.** Store extracted facts and decisions, not raw transcripts, in the vault.
- **Two timestamps per fact:** `recorded_at` (when the system learned it) and `valid_at` (when it became true).
- **Never delete automatically.** Replaced facts get `superseded_by` and `superseded_at`. Low-use items lose priority instead of vanishing. A human reviews before anything is truly removed.
- **Local-first.** Everything runs on my machine, plain files, nothing locked to a vendor.
- **Tag the source.** Every record notes which agent and which event created it.

### Log line (example)
```json
{"ts":"2026-10-06T14:02:11+05:30","agent":"claude-code","project":"shared-memory","session":"abc123","event":"PostToolUse","content":"..."}
```

### Vault note (example)
```
---
type: decision
project: shared-memory
recorded_at: 2026-10-06T14:02
valid_at: 2026-10-06
agent: claude-code
supersedes: "[[old-decision]]"
---
Use SQLite as the log, Obsidian as the view.
```

---

## 5. Forgetting rules (the "human-like" part)

1. New claim vs old record is labeled **REVISION**, **DUPLICATE** or **ORTHOGONAL** (from the Provenance agent).
2. REVISION: old record marked superseded, linked to the new one.
3. DUPLICATE: merged, counter increased.
4. Not retrieved for N days: priority lowered, still searchable.
5. Review queue: items proposed for removal wait for my approval.

Do not add decay until there are enough facts that change over time. Decay on stable facts just loses information.

---

## 6. Roadmap

| Phase | What you build | Done when |
|---|---|---|
| 0 (2 hrs) | One Claude Code hook posts to the capture endpoint (see `phase0/`) | I can see real event data arrive |
| 1 | Log, Gemini CLI hook, inject last events at session start, noise filter | A fact from one agent shows up in the other |
| 2 | Log to markdown notes in a test vault | Graph view is useful, not noise |
| 3 | Provenance agent runs on a schedule, marks replaced decisions | Old decisions show as replaced |
| 4 | MCP search, Antigravity and Cursor | Same memory works in 4+ tools |
| 5 | Review queue, decay, small dashboard | I can approve or reject removals |

Out of scope for now: capturing arbitrary apps on screen, cloud sync, multi-user teams.

---

## 7. Risks

- **Wrong deletion** hurts more than clutter, so mark superseded and review first.
- **Bad content spreading** between agents (memory or tool poisoning), so tag sources and treat captured text as data, not instructions.
- **Noisy capture** (hundreds of tool events per session), so filter and summarize before the vault.
- **Rebuilding what exists.** agentmemory, Claude-Mem, Letta, Mem0 and Graphiti already cover parts of this. Test agentmemory for a week to confirm where it falls short.

---

## 8. What already exists (research summary)

- **Shared files:** AGENTS.md and CLAUDE.md, plus sync tools like Pluribus.
- **Shared MCP memory servers:** threadctx-mcp, Turbo Quant Memory, Krimto (markdown in git).
- **Hook-based auto capture:** agentmemory (many hooks, 4 memory tiers, hybrid search), Claude-Mem (SQLite, Claude Code hooks).
- **Memory frameworks:** Letta (background sleep-time consolidation), Graphiti/Zep (time-stamped facts, supersede not delete), Mem0 (extract and consolidate).
- **Gap this project targets:** verifiable decision lineage (why was this decided, what replaced it, what evidence) across agents.

---

# Basic Project Report

**Title:** Shared Agent Memory
**Date:** 2026-10-06
**Status:** Planning complete, Phase 0 spike files ready

**Objective:** Give all AI agents used on one project a single, automatically updated, verifiable memory.

**Scope (v1):** Claude Code and Gemini CLI capture, append-only log, Obsidian view, provenance-based supersede logic, local only.

**Success criteria**
1. A decision made in one agent is available in another within the same day, with no manual saving.
2. Replaced decisions are marked, not shown as current.
3. The vault can be fully rebuilt from the log.
4. Setup takes under 15 minutes on a new project.

**Tech (planned):** Python, FastAPI, SQLite/JSONL, LangGraph (Provenance pipeline), Gemini for extraction, Obsidian vault, MCP.

**Decisions made so far**
- Log is the source of truth; Obsidian is a generated view.
- Two timestamps per fact.
- No automatic hard deletion.
- Start with two agents and capture only.

**Open questions**
- Project name.
- Which hooks does Gemini CLI and Antigravity expose in practice?
- Vector search needed in v1, or are keyword and links enough?
- How often should the cleaner run (per session end, or nightly)?

**Next action:** Phase 0 spike, a single Claude Code hook posting to FastAPI.

