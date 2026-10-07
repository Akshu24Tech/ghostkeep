# Phase 0 spike

Goal: see real hook data arrive from each agent. Nothing smarter yet.

## 1. Start the server
    pip install fastapi uvicorn
    uvicorn server:app --port 8765

## 2. Test it without any agent (new terminal)
    curl -X POST http://127.0.0.1:8765/observe -H "Content-Type: application/json" -d '{"agent":"test","event":"ping"}'
A line should print in the server terminal and appear in events.jsonl.

## 3. Wire ONE agent first

### Cursor (hooks confirmed in Cursor docs)
Create <project>/.cursor/hooks.json (Cursor reloads it automatically):

    {
      "version": 1,
      "hooks": {
        "beforeSubmitPrompt": [ { "command": "python /ABSOLUTE/PATH/TO/phase0/hook.py --agent cursor" } ],
        "afterFileEdit":      [ { "command": "python /ABSOLUTE/PATH/TO/phase0/hook.py --agent cursor" } ],
        "stop":               [ { "command": "python /ABSOLUTE/PATH/TO/phase0/hook.py --agent cursor" } ]
      }
    }

### Claude Code
Copy settings.example.json to <project>/.claude/settings.json and replace
/ABSOLUTE/PATH/TO. Restart Claude Code (hooks load at session start).

### Gemini CLI, Antigravity
Hook support is NOT verified here. Check each tool's current docs for a
hooks or lifecycle-events feature. If one exists, point it at:
    python /ABSOLUTE/PATH/TO/phase0/hook.py --agent gemini-cli   (or antigravity)
If none exists, say so and stop. Do not invent a config format.

## 4. Use the agent
Send a prompt, let it edit a file. Watch the server terminal and events.jsonl.

## 5. Report back
Share the first 3 to 5 lines of events.jsonl (or ~/.shared-memory/fallback.jsonl
if the server was down). The log schema is designed from real data.

Notes
- The hook always exits 0. It prints nothing, except {"continue": true} for Cursor.
- If the server is down, events go to ~/.shared-memory/fallback.jsonl.
- "raw" keeps up to 4000 characters of each payload so we can see what each
  agent really sends.