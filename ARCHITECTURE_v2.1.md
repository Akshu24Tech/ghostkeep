# Ghostkeep Architecture v2.1

Status: design, supersedes the v2 blueprint where they differ. Date: October 2026.
Author: Ghost (Akshu Grewal)

One line: memory is a register of claims. Whoever writes a claim never decides whether it is true.

---

## 1. What changed from v2, and why

| # | v2 | v2.1 | Reason |
|---|----|------|--------|
| 1 | Agents append claims themselves (AGENTS.md rule) | Capture is automatic: transcript watcher + git scanner feed a claim extractor. Agent-written rows are optional | Habit-based capture gets skipped. Original goal was "I should not have to say remember this" |
| 2 | Markdown files are the store | Append-only log is the truth. claims_register.md and memory_evolution.md are generated | Two writers on one file overwrite each other |
| 3 | Every claim goes to the auditor | Three claim kinds. Only verifiable claims are audited | A decision such as "we chose SQLite" has no test to run |
| 4 | Checked is never flagged at any age | Checked goes stale when its evidence changes, not when time passes | A claim true at one commit can be false ten commits later |
| 5 | Auditor agent verifies | Auditor is code. An LLM may propose a check but never sets a status | Otherwise the hallucination just moves |

Kept from v2: writer and checker are decoupled, nothing is deleted, old is not wrong, one source of truth for all agents.

---

## 2. Components

```
Claude Code / Gemini CLI / Antigravity / scripts
        │ (hooks where they exist, transcript files where they do not)
        ▼
 Capture:  Track A worker rules (optional)
           Track B git scanner (passive)
           Track C transcript watcher (passive)
        ▼
 Append-only event log        (source of truth, never edited)
        ▼
 Claim extractor              (proposes claims, status = unverified)
        ▼
 Claims store                 (rows, with status and evidence)
        ▼
 Auditor                      (deterministic checks, sets status)
        ▼
 Generated views              claims_register.md, memory_evolution.md,
                              MEMORY.md, Obsidian notes
        ▼
 Read path: MEMORY.md or MCP, injected at session start
```

Rebuild rule: every view can be regenerated from the log. If a view is damaged, regenerate it.

---

## 3. Claim model

### Kinds
- **verifiable**: about code or behavior. Example: "server.py listens on port 8765". The auditor can check it.
- **decision**: a choice made by a human. Example: "log is the source of truth, Obsidian is a view". Status is declared, not audited.
- **preference**: how the human wants things done. Same handling as decision.

### Statuses
| Status | Meaning | Set by |
|---|---|---|
| unverified | proposed, not yet checked | extractor |
| checked | a check passed, evidence stored | auditor only |
| invalid | a check failed, reason stored | auditor only |
| stale | was checked, evidence files have since changed | auditor only |
| superseded | replaced by a newer claim, link kept | auditor or human |
| declared | decision or preference stated by a human | human, or extractor from the human's own message |

### Fields
```
id, kind, text, project,
author_agent, source_event_ids[],
recorded_at, valid_at,
status, status_changed_at,
evidence: { check_type, command_or_pattern, result, commit, file_hashes{} },
supersedes, superseded_by
```

---

## 4. Rules

1. **No deletion.** Records are marked, never removed. Removal needs a human approval step.
2. **Only the auditor (code) sets checked, invalid or stale.** Agents and the extractor can only create unverified or declared rows.
3. **Staleness comes from change, not age.** At check time, store a hash of every file the claim depends on. If any hash differs later, the claim becomes stale and is re-queued for checking.
4. **Unverified claims are flagged after 30 days** as epistemic debt. Declared claims are never flagged for age.
5. **Conflicts:** checked beats unverified. Two checked claims: the one backed by newer evidence supersedes, link kept. Two declared claims: the newer one supersedes, link kept. A human can always override.
6. **Deterministic checks only.** Allowed check types for v1: file_exists, grep_in_file, config_value, run_test (exit code), git_log_contains, port_listening. An LLM may translate a claim into one of these checks. It may not decide the result.

---

## 5. Read path

MEMORY.md has three labeled sections:
- Checked facts (with evidence commit)
- Declared decisions and preferences
- Unverified (clearly marked, short, most recent first)

Stale and invalid claims are left out of the default view but stay in the register.

---

## 6. Capture sources

| Source | Method | Status |
|---|---|---|
| Cursor, Claude Code | Hooks (phase0/hook.py) | Written. Cursor hook not yet confirmed to fire |
| Antigravity IDE | Tail transcript.jsonl under .gemini\antigravity-ide\brain\<id>\.system_generated\logs\ | Found, watcher not built |
| Antigravity CLI | history.jsonl (prompts only), SQLite DBs are binary | Prompts only for now |
| Gemini CLI | Unknown, check docs | Not started |
| Git | Scanner compares diff since the last audited commit | Not started |

Known risk: the Antigravity folder is internal and its format can change in an update. Redact secrets and truncate long tool output before logging.

---

## 7. Roadmap

| Phase | Build | Done when |
|---|---|---|
| 1 | Antigravity transcript watcher into the existing log | Real events from a real chat appear in events.jsonl |
| 2 | Claim extractor, rule-based first (file edits, commands run, explicit decisions) | Log lines turn into unverified or declared rows |
| 3 | Claims store plus ONE claim end to end | "server listens on 8765" goes unverified, checked, then stale after a change to server.py |
| 4 | Auditor with the six check types | Checks run on a schedule and on pre-commit |
| 5 | Generated views: claims_register.md, MEMORY.md, Obsidian notes | Views can be deleted and rebuilt from the log |
| 6 | Read path into agents (MEMORY.md, then MCP) | A fact from one agent shows up in another |
| 7 | More agents, review queue for removals | Same memory works in 3 or more tools |

Do not start phase N+1 before phase N has real data behind it.

---

## 8. Honest limits

- Only claims about code and behavior can be verified. Decisions and preferences are recorded, not proven.
- A weak check passes a bad claim. The register is only as trustworthy as the checks in auditor_protocol.md.
- Capture from agents without hooks depends on files that may change format.
- The extractor will miss things and invent some. That is why every extracted claim starts as unverified.

## 9. Open questions

- Storage for claims: SQLite table or JSONL plus index?
- Extractor: how far can rules go before it needs an LLM?
- Who approves removals, and how often?
- Project name and repo layout for phase 1 onward.
