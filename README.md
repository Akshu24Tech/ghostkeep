# Ghostkeep

Verified handoffs between free AI coding tools.

When you switch from Claude Code to Antigravity CLI (limit hit, missing feature, second opinion),
the files carry over but the story doesn't. The next agent can't tell what was asked, who changed
what, or whether the last agent's claimed work actually happened. Ghostkeep keeps one append-only
ledger per project and checks every claim against git, with no LLM, no API key and no server.

> Status: v0.1, Week 1 of the build. Ledger + checker work. Session-log readers (automatic capture)
> and `ghostkeep handoff` come next.

## Use

```bash
uv tool install .            # or: pip install .   (Python 3.10+, no dependencies)
cd your-project
ghostkeep init
ghostkeep log --tool antigravity-ide \
  --asked 'Add one line "it is completed" at the end of docs/RESULTS.md.' \
  --claimed "Added the line." --file docs/RESULTS.md:+1-0
ghostkeep check              # exit 1 if any mismatch or orphan change
ghostkeep show
```

```
[BAD] mismatch    e_a7ce363193a7 antigravity-ide
      count_mismatch    docs/RESULTS.md  (expected +1 -0, actual +3 -0)
[???] orphan      no claim
      no_claim          stray.py  (untracked)
```

## Statuses

`verified` · `uncommitted` · `mismatch` · `superseded` · `orphan`. See [docs/LEDGER.md](docs/LEDGER.md).

## Why

Measured on a real project (10 Nov 2026): after a tool switch, plain agents found *what* changed but
got *who*, *status* or *the task itself* wrong in 4 of 5 answers, and Antigravity CLI confidently
resumed the wrong task after a Claude session was cut off mid-way.

## Tests

```bash
uv run --group dev pytest    # or: python -m pytest
```
