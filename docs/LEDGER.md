# Ghostkeep ledger format (v1)

The ledger is one file, `.ghostkeep/ledger.jsonl`, inside the project. One JSON object per line.
It is **append-only**: nothing is edited or deleted. A newer line can supersede an older one,
but the older one stays ("old is not wrong").

There are two kinds of line.

## 1. Claim: what an agent says it did

```json
{"v": 1, "kind": "claim", "id": "e_3f9a1c2b7d10", "ts": "2026-11-10T21:00:12+05:30",
 "tool": "antigravity-ide", "model": "gemini-3.8-flash", "session": "a4ddd84e-...",
 "source": "~/.gemini/antigravity/brain/a4ddd84e-.../transcript.jsonl",
 "asked": "Add one line \"it is completed\" at the end of docs/RESULTS.md.",
 "claimed": "Added the line at the end of docs/RESULTS.md.",
 "files": [{"path": "docs/RESULTS.md", "added": 1, "removed": 0}],
 "open": [],
 "base": "270ce56..."}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `tool` | yes | Which tool did the work: `claude-code`, `antigravity-cli`, `antigravity-ide`, `codex`, `gemini-cli`, `browser`, `manual` |
| `asked` | yes | The user's request, **verbatim**. Never the agent's paraphrase (grounding rule). |
| `claimed` | yes | What the agent says it did, in its own words |
| `files` | yes | Files the agent says it changed. `added`/`removed` are line counts, or `null` if it didn't say |
| `open` | no | What is still left to do, as the agent or user stated it |
| `model`, `session`, `source` | no | Where the claim came from, so it can be traced back |
| `base` | auto | Git HEAD when the claim was logged. Filled in by `ghostkeep log` |

## 2. Check: what the checker found

Written only by `ghostkeep check`. No LLM is involved.

```json
{"v": 1, "kind": "check", "id": "c_8b2d...", "ts": "...", "head": "270ce56...",
 "entry": "e_3f9a1c2b7d10", "status": "mismatch",
 "findings": [{"path": "docs/RESULTS.md", "code": "count_mismatch",
               "expected": "+1 -0", "actual": "+3 -0"}]}
```

Orphan changes (a file changed with no claim covering it) are written as a check with `"entry": null`
and `"status": "orphan"`.

## Statuses

| Status | Means | Rule |
| --- | --- | --- |
| `unverified` | Logged, not checked yet | Every claim starts here |
| `verified` | Every claimed file changed exactly as claimed, and it's committed | Diff matches, file clean in `git status` |
| `uncommitted` | Matches the claim, but not committed yet | Diff matches, file still modified or untracked |
| `mismatch` | The files don't match what the agent said | Claimed file unchanged, or line counts differ |
| `superseded` | A newer claim covers the same file | Only the newest claim per file is checked strictly |
| `orphan` | A file changed and no claim mentions it | Working tree change with no claim on the current HEAD |

## What the checker compares

For a claim with `base` B and file F:

- actual = `git diff --numstat B -- F` (committed + staged + unstaged changes since B),
  or the file's line count if F is new and untracked.
- No change found → `claimed_not_found`.
- `added`/`removed` given and different → `count_mismatch`.
- Otherwise the file matches. It's `uncommitted` if `git status` still lists it.

Known limits (v1): only the newest claim per file is checked strictly; renames are seen as
delete + add; binary files are compared as "changed / not changed" only.
