"""
Ghostkeep MCP Server.

Run it, point any MCP-compatible client at it (Claude Desktop, Claude Code,
Cursor, Windsurf, or Gemini CLI once it speaks MCP), and every one of them
reads and writes the SAME provenance-tracked memory store — instead of each
tool keeping its own private memory the way native "Claude memory" /
"Gemini memory" do.

Usage:
    python -m ghostkeep.server            # stdio transport (local tools)

Then in the client's MCP config, point it at this command. See README.md
for exact config snippets for Claude Desktop / Cursor / Windsurf.
"""

import os
try:
    from mcp.server.fastmcp import FastMCP as MCPServer
except ImportError:
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError:
        MCPServer = None

try:
    from ghostkeep.store import MemoryStore
except ImportError:
    from store import MemoryStore

STORE_DIR = os.environ.get("GHOSTKEEP_DIR", os.path.expanduser("~/.ghostkeep"))
store = MemoryStore(STORE_DIR)

mcp = MCPServer("ghostkeep")


@mcp.tool()
def add_memory(
    content: str,
    source_agent: str,
    source_session_id: str,
    confidence: float = 0.8,
    tags: list[str] = None,
    derived_from: str = None,
) -> dict:
    """
    Store a fact with full provenance. ALWAYS pass source_agent (which tool
    is calling this — e.g. 'claude-chat', 'gemini-cli', 'cursor') and
    source_session_id (any string identifying this conversation/run) so the
    fact can be traced back later. confidence is 0-1: how sure you are this
    fact is true/stable, not how important it is.
    """
    return store.add_memory(content, source_agent, source_session_id, confidence, tags, derived_from)


@mcp.tool()
def search_memory(
    query: str,
    min_confidence: float = 0.0,
    source_agent: str = None,
    limit: int = 10,
) -> list[dict]:
    """Search stored facts. Returns facts ranked by relevance and confidence."""
    return store.search_memory(query, min_confidence, source_agent, limit=limit)


@mcp.tool()
def get_provenance(fact_id: str) -> dict:
    """
    Answer 'why is this fact what it is': returns who wrote it, when, from
    which session, every event touching it, and its full derivation chain
    if it was inferred from other facts.
    """
    return store.get_provenance(fact_id)


@mcp.tool()
def list_conflicts(include_resolved: bool = False) -> list[dict]:
    """
    List facts that contradict each other across sources. Nothing gets
    silently merged — conflicts sit here until resolve_conflict is called.
    """
    return store.list_conflicts(include_resolved)


@mcp.tool()
def resolve_conflict(conflict_id: str, resolution: str, resolved_by: str) -> dict:
    """
    Resolve a conflict. resolution must be exactly one of:
      'keep_a'          - the first fact wins, the second is superseded
      'keep_b'          - the second fact wins, the first is superseded
      'merge:<text>'    - both are superseded by a new merged fact with <text>
    resolved_by identifies who/what made the call, for the audit trail.
    """
    return store.resolve_conflict(conflict_id, resolution, resolved_by)


if __name__ == "__main__":
    mcp.run()
