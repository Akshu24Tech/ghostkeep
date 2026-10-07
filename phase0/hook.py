"""Phase 0 hook for coding agents. Reads the hook JSON from stdin and posts it
to the capture server. Always exits 0 and never blocks the agent.

Usage in a hook command:
  python /ABS/PATH/phase0/hook.py --agent claude-code
  python /ABS/PATH/phase0/hook.py --agent cursor
  python /ABS/PATH/phase0/hook.py --agent gemini-cli
  python /ABS/PATH/phase0/hook.py --agent antigravity
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = os.environ.get("MEMORY_URL", "http://127.0.0.1:8765/observe")
FALLBACK = Path.home() / ".shared-memory" / "fallback.jsonl"


def get_agent():
    args = sys.argv[1:]
    if "--agent" in args:
        i = args.index("--agent")
        if i + 1 < len(args):
            return args[i + 1]
    return "claude-code"


def main(agent):
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    roots = data.get("workspace_roots") or []
    cwd = data.get("cwd") or (roots[0] if roots else os.getcwd())
    event = {
        "agent": agent,
        "project": os.path.basename(str(cwd).rstrip("/\\")),
        "cwd": cwd,
        "session": data.get("session_id") or data.get("conversation_id"),
        "event": data.get("hook_event_name"),
        "tool": data.get("tool_name"),
        "payload_keys": sorted(data.keys()),
        "raw": json.dumps(data, ensure_ascii=False)[:4000],
    }
    body = json.dumps(event, ensure_ascii=False).encode("utf-8")
    try:
        req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        try:
            FALLBACK.parent.mkdir(parents=True, exist_ok=True)
            event["recorded_at"] = datetime.now(timezone.utc).isoformat()
            with FALLBACK.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception:
            pass


if __name__ == "__main__":
    agent = get_agent()
    try:
        main(agent)
    finally:
        # Cursor expects a JSON reply on stdout; the others should stay silent.
        if agent == "cursor":
            print('{"continue": true}')
        sys.exit(0)