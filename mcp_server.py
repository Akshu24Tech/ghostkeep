#!/usr/bin/env python3
"""
Ghostkeep Model Context Protocol (MCP) Server.

Exposes verified project memory and claims to any MCP-compliant client:
- Claude Desktop
- Cursor / Windsurf
- Antigravity / Gemini CLI

Tools:
- get_project_memory: Returns the full, verified MEMORY.md summary (decisions, checked facts).
- query_claims: Search/filter active claims by kind ('decision', 'verifiable') and status ('checked', 'stale', 'declared').
- audit_memory: Runs on-demand deterministic audit and returns the latest verification stats.
"""

import json
from pathlib import Path
from mcp.server.mcpserver import MCPServer

ROOT_DIR = Path(__file__).resolve().parent
PHASE0_DIR = ROOT_DIR / "phase0"
CLAIMS_FILE = PHASE0_DIR / "claims.jsonl"
MEMORY_MD = ROOT_DIR / "MEMORY.md"

mcp = MCPServer("ghostkeep-memory")


def _load_claims() -> list[dict]:
    if not CLAIMS_FILE.exists():
        return []
    claims = []
    with CLAIMS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    claims.append(json.loads(line))
                except Exception:
                    pass
    return claims


@mcp.tool()
def get_project_memory() -> str:
    """Get the current, verified project memory (MEMORY.md).
    
    Includes declared human decisions, checked facts, and any stale claims.
    """
    if MEMORY_MD.exists():
        return MEMORY_MD.read_text(encoding="utf-8")
    return "MEMORY.md has not been generated yet. Run audit first."


@mcp.tool()
def query_claims(status: str = "checked", kind: str = "") -> str:
    """Query claims from the Ghostkeep claims ledger.
    
    Args:
        status: Filter by status ('checked', 'declared', 'stale', 'invalid', 'proposed'). Defaults to 'checked'.
        kind: Optional filter by kind ('decision', 'verifiable', 'preference').
    """
    claims = _load_claims()
    filtered = []
    for c in claims:
        if status and c.get("status") != status:
            continue
        if kind and c.get("kind") != kind:
            continue
        filtered.append(c)

    if not filtered:
        return f"No claims found matching status='{status}' and kind='{kind}'."

    output = [f"Found {len(filtered)} claim(s) [status={status}, kind={kind or 'any'}]:\n"]
    for c in filtered:
        cid = c.get("id", "N/A")
        text = c.get("text", "")
        c_kind = c.get("kind", "")
        evidence = c.get("evidence", {}).get("checked_at", "N/A")
        output.append(f"- [{cid}] ({c_kind}) {text} (last checked: {evidence})")

    return "\n".join(output)


@mcp.tool()
def audit_memory() -> str:
    """Run an on-demand deterministic audit across all claims and update MEMORY.md."""
    import subprocess
    import sys
    
    res = subprocess.run([sys.executable, str(ROOT_DIR / "ghostkeep.py"), "sync"], capture_output=True, text=True, cwd=str(ROOT_DIR))
    if res.returncode == 0:
        return f"Audit & sync succeeded.\n\n{get_project_memory()}"
    return f"Audit failed:\n{res.stderr}"


if __name__ == "__main__":
    mcp.run()
