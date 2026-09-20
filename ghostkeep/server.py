"""
Ghostkeep MCP Server.

Exposes the Ghostkeep Memory Engine and System 1 Sieve over Model Context Protocol (MCP).
Compatible with Claude Desktop, Claude Code, Cursor, Windsurf, and Antigravity.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

try:
    from mcp.server.fastmcp import FastMCP as MCPServer
except ImportError:
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError:
        MCPServer = None

from .store import MemoryStore
from .sieve import MemorySieve
from .scribe import MemoryScribe

STORE_DIR = os.environ.get("GHOSTKEEP_DIR", os.path.expanduser("~/.ghostkeep"))
store = MemoryStore(STORE_DIR)
sieve = MemorySieve()
scribe = MemoryScribe()

mcp = MCPServer("ghostkeep") if MCPServer else None


def _get_mcp_instance():
    return mcp


if mcp:
    @mcp.tool()
    def process_turn(
        raw_text: str,
        source_agent: str = "agent",
        source_session_id: str = "default",
    ) -> dict:
        """
        The 80ms Ambient Sieve: Evaluates a raw terminal command, tool output, or chat turn.
        If it is ephemeral noise, discards it (zero bloat).
        If it contains a durable decision/constraint, distills it and saves it with provenance.
        """
        eval_result = sieve.evaluate(raw_text)
        if not eval_result.is_durable:
            return {
                "status": "discarded",
                "reason": eval_result.reason,
                "confidence": eval_result.confidence,
                "engine": eval_result.engine,
            }

        distilled = scribe.distill(raw_text, eval_result)
        fact = store.add_memory(
            content=distilled["content"],
            source_agent=source_agent,
            source_session_id=source_session_id,
            confidence=distilled["confidence"],
            domain=distilled["domain"],
            tags=distilled["tags"],
        )
        return {
            "status": "stored",
            "fact": fact,
            "sieve": asdict(eval_result),
        }

    @mcp.tool()
    def add_memory(
        content: str,
        source_agent: str,
        source_session_id: str,
        confidence: float = 0.8,
        domain: str = "general",
        tags: list[str] = None,
        derived_from: str = None,
    ) -> dict:
        """Store a fact with full provenance and contradiction checking."""
        return store.add_memory(
            content=content,
            source_agent=source_agent,
            source_session_id=source_session_id,
            confidence=confidence,
            domain=domain,
            tags=tags,
            derived_from=derived_from,
        )

    @mcp.tool()
    def search_memory(
        query: str,
        domain: str = None,
        min_confidence: float = 0.0,
        source_agent: str = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search stored facts ranked by relevance and confidence."""
        return store.search_memory(
            query=query,
            domain=domain,
            min_confidence=min_confidence,
            source_agent=source_agent,
            limit=limit,
        )

    @mcp.tool()
    def get_provenance(fact_id: str) -> dict:
        """Return the complete provenance timeline and derivation ancestry for a fact."""
        return store.get_provenance(fact_id)

    @mcp.tool()
    def list_conflicts(include_resolved: bool = False) -> list[dict]:
        """List detected contradictions across agents awaiting resolution."""
        return store.list_conflicts(include_resolved)

    @mcp.tool()
    def resolve_conflict(conflict_id: str, resolution: str, resolved_by: str) -> dict:
        """
        Resolve a contradiction:
          resolution: 'keep_a' | 'keep_b' | 'merge:<new text>'
        """
        return store.resolve_conflict(conflict_id, resolution, resolved_by)


def run_server():
    if mcp:
        mcp.run()
    else:
        print("MCP SDK not installed. Run: pip install mcp>=1.0.0")


if __name__ == "__main__":
    run_server()
