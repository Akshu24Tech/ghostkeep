"""
Ghostkeep CLI — Command line interface for memory operations and ambient ingestion.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows terminals
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .store import MemoryStore
from .sieve import MemorySieve
from .scribe import MemoryScribe

STORE_DIR = os.environ.get("GHOSTKEEP_DIR", os.path.expanduser("~/.ghostkeep"))


def main():
    parser = argparse.ArgumentParser(
        prog="ghostkeep",
        description="Ghostkeep: Provenance-aware shared memory store and System 1 Sieve.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Run a turn or command through the 80ms Sieve")
    p_ingest.add_argument("text", help="Raw command, chat turn, or observation")
    p_ingest.add_argument("--source", default="cli", help="Source agent (e.g. terminal-agy, ide)")
    p_ingest.add_argument("--session", default="interactive", help="Session or task identifier")

    # search
    p_search = subparsers.add_parser("search", help="Search stored memories")
    p_search.add_argument("query", help="Search string")
    p_search.add_argument("--domain", help="Filter by domain")
    p_search.add_argument("--min-conf", type=float, default=0.0, help="Minimum confidence threshold")

    # conflicts
    p_conflicts = subparsers.add_parser("conflicts", help="List detected contradictions")
    p_conflicts.add_argument("--all", action="store_true", help="Include resolved conflicts")

    # provenance
    p_prov = subparsers.add_parser("provenance", help="Inspect lineage and event ledger for a fact")
    p_prov.add_argument("fact_id", help="Fact ID (e.g. fact_...)")

    # serve
    subparsers.add_parser("serve", help="Start the Ghostkeep MCP server (stdio transport)")

    args = parser.parse_args()

    store = MemoryStore(STORE_DIR)
    sieve = MemorySieve()
    scribe = MemoryScribe()

    if args.command == "ingest":
        eval_res = sieve.evaluate(args.text)
        print(f"\n[SIEVE] Evaluation [{eval_res.engine}]:")
        print(f"   Durable   : {eval_res.is_durable}")
        print(f"   Confidence: {eval_res.confidence:.2f}")
        print(f"   Domain    : {eval_res.domain}")
        print(f"   Reason    : {eval_res.reason}\n")

        if not eval_res.is_durable:
            print("[DISCARDED] Classified as ephemeral noise (0 bytes added to memory).")
            return

        distilled = scribe.distill(args.text, eval_res)
        fact = store.add_memory(
            content=distilled["content"],
            source_agent=args.source,
            source_session_id=args.session,
            confidence=distilled["confidence"],
            domain=distilled["domain"],
            tags=distilled["tags"],
        )
        print(f"[STORED] Stored with full provenance in facts.json:")
        print(f"   ID        : {fact['id']}")
        print(f"   Claim     : {fact['content']}")
        print(f"   Status    : {fact['status']}")
        print(f"   Tags      : {', '.join(fact['tags'])}")

    elif args.command == "search":
        results = store.search_memory(
            query=args.query,
            domain=args.domain,
            min_confidence=args.min_conf,
        )
        print(f"\nFound {len(results)} memory match(es):")
        for f in results:
            status_tag = "[CONFLICTED]" if f["status"] == "conflicted" else "[ACTIVE]"
            print(f"\n* {status_tag} [{f['id']}] (conf: {f['confidence']:.2f}, domain: {f.get('domain', 'general')})")
            print(f"   {f['content']}")
            print(f"   Source: {f['source_agent']} (session: {f['source_session_id']})")

    elif args.command == "conflicts":
        conflicts = store.list_conflicts(include_resolved=args.all)
        print(f"\nFound {len(conflicts)} conflict(s):")
        for c in conflicts:
            state = "RESOLVED" if c["resolved"] else "PENDING"
            print(f"\n! [{c['id']}] Status: {state}")
            print(f"   Fact A: {c.get('fact_a', {}).get('content', c['fact_id_a'])}")
            print(f"   Fact B: {c.get('fact_b', {}).get('content', c['fact_id_b'])}")
            if c["resolved"]:
                print(f"   Resolution: {c['resolution']} by {c['resolved_by']}")

    elif args.command == "provenance":
        prov = store.get_provenance(args.fact_id)
        if "error" in prov:
            print(f"Error: {prov['error']}")
            return
        fact = prov["fact"]
        print(f"\n[PROVENANCE] Lineage for {fact['id']}:")
        print(f"   Content   : {fact['content']}")
        print(f"   Author    : {fact['source_agent']}")
        print(f"   Session   : {fact['source_session_id']}")
        print(f"   Confidence: {fact['confidence']:.2f}")
        print("\n   Audit Ledger Events:")
        for ev in prov["events"]:
            print(f"     * [{ev['created_at'][:19]}] {ev['event_type'].upper()}: {ev['detail']} (actor: {ev['actor']})")

    elif args.command == "serve":
        from .server import run_server
        print(f"Starting Ghostkeep MCP server over stdio (store: {STORE_DIR})...")
        run_server()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
