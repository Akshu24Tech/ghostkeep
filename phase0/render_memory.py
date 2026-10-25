"""Ghostkeep Memory Renderer (Phase 0 v1).

Reads phase0/claims.jsonl and writes MEMORY.md at the repo root with:
- Declared decisions and preferences
- Checked facts with evidence date
- Needs recheck (stale)
- 10 most recent Unverified (labeled unverified)
Strict maximum 60 lines.
"""

import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CLAIMS_FILE = ROOT_DIR / "phase0" / "claims.jsonl"
MEMORY_MD = ROOT_DIR / "MEMORY.md"


def load_claims() -> list[dict]:
    if not CLAIMS_FILE.exists():
        return []
    claims = []
    with CLAIMS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    claims.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return claims


def render_memory() -> str:
    claims = load_claims()

    declared = [c for c in claims if c.get("status") == "declared"]
    checked = [c for c in claims if c.get("status") == "checked"]
    stale = [c for c in claims if c.get("status") == "stale"]
    unverified = [c for c in claims if c.get("status") == "unverified"]

    lines = [
        "# Project Memory",
        "",
        "## Declared Decisions & Preferences",
    ]

    if declared:
        for c in declared:
            cid = c.get("id", "")
            kind = c.get("kind", "decision")
            text = c.get("text", "")
            lines.append(f"- [{cid}] ({kind}) {text}")
    else:
        lines.append("- *(none)*")

    lines.append("")
    lines.append("## Checked Facts")
    if checked:
        for c in checked:
            cid = c.get("id", "")
            text = c.get("text", "")
            ev = c.get("evidence") or {}
            ev_date = ev.get("verified_at") or c.get("valid_at") or c.get("recorded_at", "")[:10]
            if isinstance(ev_date, str) and "T" in ev_date:
                ev_date = ev_date.split("T")[0]
            lines.append(f"- [{cid}] {text} (checked: {ev_date})")
    else:
        lines.append("- *(none)*")

    lines.append("")
    lines.append("## Needs Recheck (Stale)")
    if stale:
        for c in stale:
            cid = c.get("id", "")
            text = c.get("text", "")
            lines.append(f"- [{cid}] {text}")
    else:
        lines.append("- *(none)*")

    lines.append("")
    lines.append("## Recent Unverified (max 10)")
    recent_unverified = unverified[-10:] if len(unverified) > 10 else unverified
    if recent_unverified:
        for c in reversed(recent_unverified):
            cid = c.get("id", "")
            text = c.get("text", "")
            lines.append(f"- [{cid}] [unverified] {text}")
    else:
        lines.append("- *(none)*")

    # Enforce strictly max 60 lines
    if len(lines) > 60:
        lines = lines[:60]

    content = "\n".join(lines) + "\n"
    MEMORY_MD.write_text(content, encoding="utf-8")
    print(f"Rendered MEMORY.md at {MEMORY_MD} ({len(lines)} lines)")
    return content


if __name__ == "__main__":
    render_memory()
