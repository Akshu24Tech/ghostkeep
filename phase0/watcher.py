"""Antigravity Transcript Watcher (Track C Passive Capture - v2.1).

Tails the active conversation's transcript.jsonl under:
~/.gemini/antigravity-ide/brain/<conversation-id>/.system_generated/logs/transcript.jsonl
and posts clean, deduplicated events exclusively through the capture server.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

DEFAULT_BRAIN_DIR = Path.home() / ".gemini" / "antigravity-ide" / "brain"
DEFAULT_STATE_FILE = Path(__file__).parent / ".watcher_state.json"
SERVER_URL = os.environ.get("MEMORY_URL", "http://127.0.0.1:8765/observe")

# Types to drop (noisy system meta/artifacts)
DROP_TYPES = {
    "SYSTEM_MESSAGE",
    "CHECKPOINT",
    "KNOWLEDGE_ARTIFACTS",
    "CONVERSATION_HISTORY",
    "GENERIC",
}


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


def sanitize_text(text: str, max_len: int = 800) -> str:
    """Remove potential secrets or tokens and truncate overly long chunks."""
    if not text:
        return ""
    # Redact common token patterns (GitHub tokens, bearer headers, api keys)
    redacted = re.sub(r"(ghp_[A-Za-z0-9_]{30,}|gho_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{20,})", "[REDACTED_TOKEN]", text)
    redacted = re.sub(r"(AIza[0-9A-Za-z-_]{35})", "[REDACTED_API_KEY]", redacted)
    # Redact .env variable values if accidentally present
    redacted = re.sub(r'(?i)(api[_-]?key|secret|password|token)\s*=\s*[^\s]+', r'\1=[REDACTED]', redacted)
    redacted = redacted.strip()
    if len(redacted) > max_len:
        return redacted[:max_len] + "... [truncated]"
    return redacted


def clean_summary_for_type(step_type: str, raw_content: str, tool_name: str | None) -> str | None:
    """Filter noise and format clean summaries per event type."""
    # 1. USER_INPUT: strip <ADDITIONAL_METADATA> and request tags
    if step_type == "USER_INPUT":
        cleaned = re.sub(r"<ADDITIONAL_METADATA>[\s\S]*?</ADDITIONAL_METADATA>", "", raw_content).strip()
        cleaned = re.sub(r"^<USER_REQUEST>\s*", "", cleaned)
        cleaned = re.sub(r"\s*</USER_REQUEST>$", "", cleaned).strip()
        return sanitize_text(cleaned, max_len=600)

    # 2. VIEW_FILE: extract only the file path, never file contents
    if step_type == "VIEW_FILE":
        m = re.search(r"File Path:\s*[`\"]?(file:///[^\n`\"]+|[^\n`\"]+)[`\"]?", raw_content)
        if m:
            path = m.group(1).replace("file:///", "")
            return f"Viewed file: {path}"
        return "Viewed file"

    # 3. PLANNER_RESPONSE: drop if empty
    if step_type == "PLANNER_RESPONSE":
        if not raw_content or not raw_content.strip():
            return None
        return sanitize_text(raw_content, max_len=600)

    # 4. RUN_COMMAND / CODE_ACTION / others: keep sanitized summary
    return sanitize_text(raw_content, max_len=600)


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


def post_to_server(event: dict, server_url: str = SERVER_URL) -> bool:
    """Post event exclusively through the capture server."""
    body = json.dumps(event, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        server_url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200
    except Exception as e:
        raise ConnectionError(f"Capture server unavailable at {server_url}: {e}")


def process_new_lines(transcript_path: Path, conv_id: str, state_file: Path, state: dict) -> int:
    """Read newly appended lines from transcript and post deduplicated events via the server."""
    file_key = str(transcript_path.resolve())
    last_line_index = state.get(file_key, 0)

    # Maintain a set of recent dedupe hashes in state
    seen_hashes = set(state.get("seen_hashes", []))

    if not transcript_path.exists():
        return 0

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
            source_ts = data.get("created_at") or ""
            raw_content = data.get("content") or ""

            # Rule 4: Drop noisy meta types
            if step_type in DROP_TYPES:
                last_line_index = idx + 1
                state[file_key] = last_line_index
                save_state(state_file, state)
                continue

            # Tool name if present
            tool_name = None
            tool_calls = data.get("tool_calls") or []
            if tool_calls and isinstance(tool_calls, list):
                tool_name = tool_calls[0].get("name")

            # Clean and sanitize summary per type
            summary = clean_summary_for_type(step_type, raw_content, tool_name)
            if summary is None and step_type == "PLANNER_RESPONSE":
                # Drop empty planner line
                last_line_index = idx + 1
                state[file_key] = last_line_index
                save_state(state_file, state)
                continue

            # Rule 2: Compute robust dedupe key
            dedupe_payload = f"{conv_id}:{step_type}:{source_ts}:{raw_content[:200]}"
            dedupe_key = hashlib.sha256(dedupe_payload.encode("utf-8")).hexdigest()

            if dedupe_key in seen_hashes:
                # Duplicate detected: skip posting
                last_line_index = idx + 1
                state[file_key] = last_line_index
                save_state(state_file, state)
                continue

            # Rule 3: Structured event payload
            event = {
                "agent": "antigravity",
                "conversation_id": conv_id,
                "project": None,
                "event": step_type,
                "step_index": step_idx,
                "source_ts": source_ts,
                "source": source,
                "tool": tool_name,
                "summary": summary,
                "dedupe_hash": dedupe_key[:16],
            }

            # Rule 5: Post exclusively through the server
            post_to_server(event)

            # Mark seen & advance position
            seen_hashes.add(dedupe_key)
            count += 1
            last_line_index = idx + 1

            # Rule 1: Save state immediately after processing each record
            state[file_key] = last_line_index
            # Keep seen_hashes bounded (last 2000)
            state["seen_hashes"] = list(seen_hashes)[-2000:]
            save_state(state_file, state)

    return count


def main():
    parser = argparse.ArgumentParser(description="Antigravity Transcript Watcher (Track C v2.1)")
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
        state["seen_hashes"] = []
        save_state(DEFAULT_STATE_FILE, state)

    print(f"Watching Antigravity conversation: {conv_id}")
    print(f"Source transcript: {transcript_path}")
    print(f"Capture Gateway: {SERVER_URL}")

    if args.once or not args.tail:
        try:
            count = process_new_lines(transcript_path, conv_id, DEFAULT_STATE_FILE, state)
            print(f"Processed and posted {count} clean event(s).")
        except ConnectionError as e:
            print(f"Error: {e}")
            sys.exit(1)
        return

    # Continuous loop mode
    print("Running in continuous tail mode... Press Ctrl+C to stop.")
    try:
        while True:
            current_found = find_latest_transcript(DEFAULT_BRAIN_DIR)
            if current_found:
                current_transcript, current_conv_id = current_found
                if current_conv_id != conv_id:
                    print(f"Switched to newer conversation: {current_conv_id}")
                    conv_id = current_conv_id
                    transcript_path = current_transcript

            count = process_new_lines(transcript_path, conv_id, DEFAULT_STATE_FILE, state)
            if count > 0:
                print(f"Captured {count} event(s) at {time.strftime('%H:%M:%S')}")
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nWatcher stopped.")


if __name__ == "__main__":
    main()
