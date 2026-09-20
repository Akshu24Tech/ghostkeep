# 04: Developer Workflow, Setup & Runbook

This guide details how to install, configure, connect, and operate Ghostkeep across your local development tools.

---

## 1. Installation

Clone the repository and install in editable mode:

```bash
git clone https://github.com/Akshu24Tech/ghostkeep.git
cd ghostkeep
pip install -e .
```

### Enabling TypeSafe Jev Acceleration (Optional)
To replace the local heuristic engine with Jev System 1 RLCD:

```bash
pip install typesafe-sdk
export TYPESAFE_API_KEY="your-typesafe-api-key"
# On Windows PowerShell:
$env:TYPESAFE_API_KEY="your-typesafe-api-key"
```

*Note: Ghostkeep works 100% offline out-of-the-box using its built-in heuristic engine if no API key is set.*

---

## 2. MCP Client Integrations

Point your MCP clients to Ghostkeep to establish a shared cross-client memory layer:

### A. Claude Desktop
Add to your `claude_desktop_config.json`:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ghostkeep": {
      "command": "python",
      "args": ["-m", "ghostkeep.cli", "serve"],
      "env": {
        "GHOSTKEEP_DIR": "~/.ghostkeep"
      }
    }
  }
}
```

### B. Cursor
In `.cursor/mcp.json` (or Cursor Settings > Features > MCP):

```json
{
  "mcpServers": {
    "ghostkeep": {
      "command": "python",
      "args": ["-m", "ghostkeep.cli", "serve"]
    }
  }
}
```

### C. Windsurf
In `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "ghostkeep": {
      "command": "python",
      "args": ["-m", "ghostkeep.cli", "serve"]
    }
  }
}
```

---

## 3. Daily Developer Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                   TYPICAL WORKFLOW                          │
│                                                             │
│  1. In Terminal: You finish an API refactor or bug fix      │
│     ghostkeep ingest "Fixed JWT auth expiration bug"        │
│     -> Passes Sieve in 80ms, logged to facts.json           │
│                                                             │
│  2. In IDE Agent: You start working on frontend             │
│     Agent queries: search_memory("auth")                    │
│     -> Returns fact with author & session info              │
│     -> Implements correct JWT header with 0 re-explaining   │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Verification & Testing Runbook

Run the automated test suite:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

### Expected Output:
```
test_constraint_detected_with_domain (test_sieve.TestMemorySieveAndScribe.test_constraint_detected_with_domain) ... ok
test_durable_decision_captured (test_sieve.TestMemorySieveAndScribe.test_durable_decision_captured) ... ok
test_ephemeral_noise_discarded (test_sieve.TestMemorySieveAndScribe.test_ephemeral_noise_discarded) ... ok
test_add_and_search_memory (test_store.TestMemoryStore.test_add_and_search_memory) ... ok
test_conflict_detection_and_resolution (test_store.TestMemoryStore.test_conflict_detection_and_resolution) ... ok
test_provenance_tracking (test_store.TestMemoryStore.test_provenance_tracking) ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.098s

OK
```

---

## 5. Troubleshooting & FAQs

### Q1: Where are my memories actually saved?
By default, memories are stored in `~/.ghostkeep/` (`C:\Users\<username>\.ghostkeep\` on Windows).
You can customize the storage path by setting the `GHOSTKEEP_DIR` environment variable:
```bash
export GHOSTKEEP_DIR="/path/to/custom/memory"
```

### Q2: What happens when two agents contradict each other?
Ghostkeep detects that the sequence similarity between two active facts from different authors is high (above `0.72`). Both facts are marked `status: "conflicted"` and staged in `conflicts.json`. 
Run:
```bash
ghostkeep conflicts
```
And resolve via the MCP tool `resolve_conflict` or CLI with `keep_a`, `keep_b`, or `merge:<new text>`.

### Q3: Why does `ghostkeep ingest` discard my input?
If an input is fewer than 10 characters or matches an ephemeral noise pattern (e.g. `npm test`, `git status`, casual greetings), the Sieve discards it to prevent context pollution.

---

## 🔗 Navigation
- [[01-system-overview-and-purpose]] — Core problem and 3-Tier architecture.
- [[02-component-deep-dive]] — Line-by-line module breakdowns.
- [[03-io-contracts-and-schemas]] — Complete JSON structures and CLI runs.
- [[Index]] — Back to Map of Content.
