"""Antigravity Transcript Watcher (Track C Passive Capture).

Tails the active conversation's transcript.jsonl under:
~/.gemini/antigravity-ide/brain/<conversation-id>/.system_generated/logs/transcript.jsonl
and appends structured events into phase0/events.jsonl.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BRAIN_DIR = Path.home() / ".gemini" / "antigravity-ide" / "brain"
DEFAULT_EVENTS_FILE = Path(__file__).parent / "events.jsonl"
DEFAULT_STATE_FILE = Path(__file__).parent / ".watcher_state.json"
SERVER_URL = os.environ.get("MEMORY_URL", "http://127.0.0.1:8765/observe")


def find_latest_transcript(brain_dir: Path) -> tuple[Path, str] | None:
    """Find the conversation folder with the most recently updated transcript.jsonl."""
    if not brain_dir.exists():
        return None

    candidates = []
    for conv_dir in brain_dir.iterdir():
        if not conv_dir.is_dir() or conv_dir.name.startswith("temp"):
            continue
        transcript = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
        if transcript.is_file():
            candidates.append((transcript.stat().st_mtime, transcript, conv_dir.name))

    if not candidates:
        return None

    candidates.sort(key=lambda c: c[0], reverse=True)
    _, latest_transcript, conv_id = candidates[0]
    return latest_transcript, conv_id


def sanitize_text(text: str, max_len: int = 1000) -> str:
    """Remove potential secrets or tokens and truncate overly long chunks."""
    if not text:
        return ""
    # Redact common token patterns (GitHub tokens, bearer headers, api keys)
    redacted = re.sub(r"(ghp_[A-Za-z0-9_]{30,}|gho_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{20,})", "[REDACTED_TOKEN]", text)
    redacted = re.sub(r"(AIza[0-9A-Za-z-_]{35})", "[REDACTED_API_KEY]", redacted)
    redacted = redacted.strip()
    if len(redacted) > max_len:
        return redacted[:max_len] + "... [truncated]"
    return redacted


def load_state(state_file: Path) -> dict:
    if state_file.exists():
        try:
            with state_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state_file: Path, state: dict) -> None:
    try:
        with state_file.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def is_server_online(url: str = SERVER_URL) -> bool:
    """Quickly probe if local capture daemon is online."""
    try:
        health_url = url.rsplit("/", 1)[0] + "/health"
        req = urllib.request.Request(health_url)
        with urllib.request.urlopen(req, timeout=0.1) as resp:
            return resp.status == 200
    except Exception:
        return False


def record_event(event: dict, events_file: Path, post_to_server: bool = False) -> None:
    """Write event to events.jsonl and optionally post to running local server."""
    event["recorded_at"] = datetime.now(timezone.utc).isoformat()
    line = json.dumps(event, ensure_ascii=False) + "\n"

    # Always ensure local append-only log is written
    with events_file.open("a", encoding="utf-8") as f:
        f.write(line)

    # If capture daemon is confirmed online, notify it as well
    if post_to_server:
        try:
            req = urllib.request.Request(
                SERVER_URL,
                data=line.encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=0.2)
        except Exception:
            pass


def process_new_lines(transcript_path: Path, conv_id: str, events_file: Path, state: dict) -> int:
    """Read newly appended lines from transcript and append to events.jsonl."""
    file_key = str(transcript_path.resolve())
    last_line_index = state.get(file_key, 0)

    if not transcript_path.exists():
        return 0

    server_up = is_server_online()
    count = 0

    with transcript_path.open("r", encoding="utf-8", errors="replace") as f:
        for idx, line in enumerate(f):
            if idx < last_line_index:
                continue

            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            step_type = data.get("type", "UNKNOWN")
            source = data.get("source", "UNKNOWN")
            step_idx = data.get("step_index", idx)
            content = data.get("content") or ""

            # Extract tool name and command summary if present
            tool_name = None
            tool_calls = data.get("tool_calls") or []
            if tool_calls and isinstance(tool_calls, list):
                tool_name = tool_calls[0].get("name")

            summary = sanitize_text(content, max_len=600)

            event = {
                "agent": "antigravity",
                "session": conv_id,
                "event": step_type,
                "step_index": step_idx,
                "source": source,
                "tool": tool_name,
                "summary": summary,
            }

            record_event(event, events_file, post_to_server=server_up)
            count += 1
            last_line_index = idx + 1

    state[file_key] = last_line_index
    return count


def main():
    parser = argparse.ArgumentParser(description="Antigravity Transcript Watcher (Track C)")
    parser.add_argument("--once", action="store_true", help="Process currently available lines once and exit")
    parser.add_argument("--tail", action="store_true", help="Run continuously in background tail mode")
    parser.add_argument("--from-start", action="store_true", help="Reprocess entire current transcript from line 0")
    args = parser.parse_args()

    found = find_latest_transcript(DEFAULT_BRAIN_DIR)
    if not found:
        print(f"Error: No Antigravity transcript found in {DEFAULT_BRAIN_DIR}")
        sys.exit(1)

    transcript_path, conv_id = found
    state = load_state(DEFAULT_STATE_FILE)

    if args.from_start:
        state[str(transcript_path.resolve())] = 0

    print(f"Watching Antigravity conversation: {conv_id}")
    print(f"Source transcript: {transcript_path}")
    print(f"Destination: {DEFAULT_EVENTS_FILE}")

    if args.once or not args.tail:
        count = process_new_lines(transcript_path, conv_id, DEFAULT_EVENTS_FILE, state)
        save_state(DEFAULT_STATE_FILE, state)
        print(f"Processed {count} new event(s).")
        return

    # Continuous loop mode
    print("Running in continuous tail mode... Press Ctrl+C to stop.")
    try:
        while True:
            # Check for newer conversation folder if active chat switched
            current_found = find_latest_transcript(DEFAULT_BRAIN_DIR)
            if current_found:
                current_transcript, current_conv_id = current_found
                if current_conv_id != conv_id:
                    print(f"Switched to newer conversation: {current_conv_id}")
                    conv_id = current_conv_id
                    transcript_path = current_transcript

            count = process_new_lines(transcript_path, conv_id, DEFAULT_EVENTS_FILE, state)
            if count > 0:
                save_state(DEFAULT_STATE_FILE, state)
                print(f"Captured {count} event(s) at {datetime.now().strftime('%H:%M:%S')}")
            time.sleep(2)
    except KeyboardInterrupt:
        save_state(DEFAULT_STATE_FILE, state)
        print("\nWatcher stopped.")


if __name__ == "__main__":
    main()
