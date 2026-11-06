# Ghostkeep and Baton: Store vs. Enforcer

How [Baton](https://github.com/StanimirTenev/baton) relates to Ghostkeep. Deep-researched 2026-11-06 at Baton v3.30.0. Short version: **they solve different halves of the same problem and compose cleanly.** Baton is not a competitor to Ghostkeep — it is the *discipline layer* Ghostkeep's write path currently assumes but does not enforce.

---

## The split

```
┌──────────────────────────────────────────────────────────────┐
│  WHAT IS TRUE  (the store)          │  THAT IT GETS WRITTEN    │
│                                     │  & STAYS TRUE (the loop) │
│  ┌────────────────────────────┐    │  ┌────────────────────┐  │
│  │        GHOSTKEEP           │    │  │       BATON        │  │
│  │ • provenance-aware facts   │    │  │ • 6 Claude Code    │  │
│  │ • conflicts.json ledger    │◀───┼──│   hooks (harness-  │  │
│  │ • MCP read/write, cross-   │    │  │   run, not agent-  │  │
│  │   surface (CLI + IDE)      │    │  │   judged)          │  │
│  │ • W3C PROV lineage         │    │  │ • demands the      │  │
│  └────────────────────────────┘    │  │   record exists    │  │
│                                     │  │ • flags rot/staleness │
│  A store an agent can skip writing  │  └────────────────────┘  │
│  to is a store that silently rots.  │  Baton makes skipping    │
│                                     │  structurally hard.      │
└──────────────────────────────────────────────────────────────┘
```

| | Ghostkeep | Baton |
|---|---|---|
| **Primitive** | a *fact* (JSON) with provenance | a *task folder* + `LOGBOOK.md` (markdown) |
| **Surface** | cross-surface (Claude Desktop, Cursor, Windsurf, CLI) via MCP | Claude Code only (terminal/IDE/desktop), via hooks |
| **Mechanism** | a server agents *choose* to call | hooks the *harness* runs — the agent cannot opt out |
| **State vs history** | `facts.json` (now) + `provenance.jsonl` (log) | memory file (true now) + `LOGBOOK.md` (what was done) — same split |
| **Conflict** | `conflicts.json` queue (`keep_a`/`keep_b`/`merge`) | `### Claims to verify` section + `refuted:` lines a human reads |
| **Network** | local JSON SoT | hooks = zero network; opt-in `review`/`sift` → OpenRouter only |

Ghostkeep answers *"what do we know, and who said it?"* Baton answers *"did anyone actually write it down, and is what's written still true?"* Neither answers the other.

---

## Ideas worth stealing (mapped to our existing design)

1. **Enforcement as a harness concern, not an agent virtue.** Baton's thesis: "write it down" fails in exactly the loaded session where it matters, because nobody's thinking about note-taking then. So the *harness* enforces it. **For Ghostkeep:** ship an optional **Claude Code hook pack** (`Stop`/`SessionStart`) that (a) injects the relevant Ghostkeep facts at session start and (b) hands the turn back if the session made decisions that never reached a `scribe` write. This is the missing teeth on our MCP write path — right now an agent that forgets to call Ghostkeep leaves no trace, same failure Baton exists to kill.

2. **"Never a silent pass."** Baton's hardest rule: a check that quietly passes on what it couldn't read is *worse* than no check, because it's then trusted. **For Ghostkeep:** anywhere the Sieve, conflict detector, or a retrieval filter can't fully read its input (truncated file, unreadable source, confidential hold), it must **report partial/blocked**, never return a clean-looking empty. Validates the applicability-gate instinct already in `ARCHITECTURE_v2.1.md`.

3. **Confidence-as-debt + shelf life → sharpens [[future-roadmap]] §2 (Temporal Confidence Decay).** Baton doesn't just decay; it treats an *unverified* claim (`I`=inferred / `A`=agent-claimed, older than 30 days) as a **debt that must be paid — verified or dropped** — and surfaces `true_as_of` / `review_after` shelf-life expiry at session start. Steal the *debt* framing: a fact's `confidence` should pair with a `verified_until`, and expiry should actively nag, not passively decay into noise.

4. **"The record rests on code, and the code moves" (`kod: path@commit`).** Baton ties a logbook to a repo ref and reports when the repo has moved N commits past it — the record reads fine while the code it describes drifted underneath. **For Ghostkeep:** a fact about code should carry the commit it was true at; retrieval flags "this fact is 9 commits stale." Complements our `derived_from` lineage with a *freshness* axis.

5. **Verifiable over generative (same creed as Nemo).** "A claim that tests pass → list the command and its output," optionally **re-run the pinned test** and set the true result beside the claim. Ghostkeep already prefers deterministic reads; adopt the pattern of storing the *evidence command*, not just the asserted outcome, for any testable fact.

6. **Confidentiality guard before egress.** Baton's `review_confidential` holds any passage (matched on path *and* content, every alphabet) back before a single byte goes to a model — and a held row stops *itself*, not the whole run. Directly reusable for Ghostkeep's permission-bounded retrieval: access-check the *quote*, in every language it might be written in, before it leaves the box.

7. **Logbook ≠ memory (don't let them merge).** Baton is adamant: the record only grows (chronology), the state file only ever replaces (what's true now); merge them and you get a file too long to load and too disordered to trust. Confirms our `facts.json` (replace) vs `provenance.jsonl` (append) separation is correct — and warns against ever letting a fact accrete its own history inline.

---

## Where Baton is weaker than us

- **Single-surface** (Claude Code only). Ghostkeep's cross-surface MCP bus is exactly what Baton lacks — a terminal `agy` agent and an IDE agent still can't see each other through Baton.
- **No structured conflict resolution** — it surfaces claims to a human, we have a resolvable `conflicts.json` queue.
- **Unproven** — 0 stars, solo author, self-reported metrics on one corpus. We should mine the *ideas*, not adopt the tool as a dependency.

## Verdict for Ghostkeep

Treat Baton as the **enforcement + rot-detection reference design** for Ghostkeep's write path. The single highest-leverage port: an optional Claude Code hook pack that makes writing to Ghostkeep structural instead of voluntary, and that refuses to let a session end with unrecorded decisions — closing the one gap an MCP-only store cannot close by itself.

## Related
- [[future-roadmap]] — §2 (Confidence Decay) and §4 (SQLite/FTS5) both pre-echo Baton/Nemo; this sharpens them.
- [[ghostkeep-and-dreamkeeper]] — DreamKeeper consolidates; Baton enforces; Ghostkeep stores.
- [[provenance-tracking]] · [[conflict-detection-and-resolution]] · [[lifecycle-of-a-fact]]
