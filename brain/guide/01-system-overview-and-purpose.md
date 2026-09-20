# 01: System Overview & Purpose

> **Project:** Ghostkeep  
> **Repository:** [Akshu24Tech/ghostkeep](https://github.com/Akshu24Tech/ghostkeep)  
> **Core Concept:** Provenance-Aware Shared Memory Store & System 1 Micro-Decision Sieve

---

## 1. The Core Problem: Cross-Surface Agent Amnesia

When building modern AI-assisted software, developers rarely work in a single chat box. They run across two primary execution surfaces simultaneously:
1. **Terminal CLI Agents** (`agy`, `claude`): Running long builds, running test suites, executing database migrations, and testing APIs.
2. **IDE Pair-Programmer Agents** (Antigravity IDE, Cursor, Windsurf): Writing code, editing files, refactoring components, and planning architecture.

### The Breakdown
Even though both agents run on the **same machine**, in the **exact same git repository**, and often under the **same Google/Anthropic account**:
- **They operate in total cognitive isolation.**
- Terminal CLI logs its session to `~/.gemini/antigravity-cli/brain/`.
- IDE agent logs its session to `~/.gemini/antigravity-ide/brain/`.

```
                    DEVELOPER (USER)
              ┌────────────┴────────────┐
              ▼                         ▼
      Terminal CLI (`agy`)        IDE Agent Chat
              │                         │
              ▼                         ▼
      Siloed CLI Logs           Siloed IDE Logs
              ▲                         ▲
              │                         │
              └─── COGNITIVE AMNESIA ───┘
```

### Why Existing Solutions Fail:
- **Dumping raw chat logs into memory** explodes context windows with megabytes of noisy compiler output, lint errors, and test progress bars.
- **Calling frontier LLMs (Claude Sonnet, GPT-4o)** on every command to summarize the turn takes 2–4 seconds and burns significant token costs.
- **Generic vector databases (Chroma, Pinecone)** lose origin context: they store vectors, but cannot answer *"Why did we make this decision, which agent decided it, and what previous fact did it contradict?"*

---

## 2. The Ghostkeep Solution: The 3-Tier Memory Sieve

Ghostkeep serves as the **shared central nervous system** across all execution surfaces. It uses a 3-tier architecture designed for sub-100ms speed, zero context bloat, and complete provenance tracking:

```
                  RAW CHAT TURN / TERMINAL COMMAND
                                 │
                                 ▼
 ┌───────────────────────────────────────────────────────────────┐
 │ TIER 1: THE SIEVE (sieve.py) - ~80ms System 1 Micro-Decision  │
 │ • Evaluates raw text in <100ms via Jev (or local engine)      │
 │ • Noul  : "Contains durable decision or constraint?"          │
 │ • Choice: Route to domain (database, auth, ui, devops, etc.)  │
 └───────────────────────────────┬───────────────────────────────┘
                                 │
                 Is `contains_decision` >= 0.75?
                                 │
                 ┌───────────────┴───────────────┐
                 ▼ (No: 90% noise)               ▼ (Yes: 10% signal)
          ┌─────────────┐         ┌──────────────────────────────┐
          │   DISCARD   │         │ TIER 2: THE SCRIBE (scribe)  │
          │ (Zero bloat)│         │ • Distills 1-sentence Fact   │
          └─────────────┘         │ • Cleans chatter & preambles │
                                  └──────────────┬───────────────┘
                                                 │
                                                 ▼
 ┌───────────────────────────────────────────────────────────────┐
 │ TIER 3: PROVENANCE STORE (store.py)                           │
 │ • Real-time contradiction check (no silent overwrites)        │
 │ • facts.json (Active & superseded facts)                      │
 │ • conflicts.json (Queue of contradictory statements)          │
 │ • provenance.jsonl (Immutable audit ledger)                   │
 └───────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
                     UNIVERSAL MCP SERVER / CLI
                   (Both agents query on startup)
```

---

## 3. Four Guiding Design Principles

1. **Plain Files are the Source of Truth**:
   No external vector database service required. `facts.json`, `conflicts.json`, and `provenance.jsonl` are human-readable, git-diffable, and inspectable with standard tools (`jq`, VS Code).
2. **System 1 Filtering (Fast & Cheap)**:
   Never use a 70B parameter frontier model to check a binary boolean condition. Jev evaluates decisions in **80ms** at **$0.042/1M tokens**.
3. **Zero Silent Overwrites**:
   When Agent B asserts something that contradicts Agent A, Ghostkeep does not overwrite. It flags both facts as `conflicted` and stages them in `conflicts.json` until explicitly resolved.
4. **Full Lineage & Provenance**:
   Every single fact knows its `source_agent`, `source_session_id`, `derived_from` ancestor, and has an append-only timeline in `provenance.jsonl`.

---

## 🔗 Next Chapters
- [[02-component-deep-dive]] — Detailed breakdown of every Python file in the codebase.
- [[03-io-contracts-and-schemas]] — Data models, JSON structures, and input/output contracts.
- [[04-developer-workflow-and-setup]] — Setup, MCP configuration, and CLI runbook.
