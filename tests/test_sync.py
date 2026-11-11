"""Session readers, decision capture and handoff, using log shapes mapped from real files."""
import json
import subprocess
from pathlib import Path

import pytest

from ghostkeep import check, decisions, handoff, ledger, sources, sync
from ghostkeep.cli import main


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def env(tmp_path, monkeypatch):
    repo = tmp_path / "teamcaptain"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    (repo / "docs").mkdir()
    (repo / "docs/RESULTS.md").write_text("# Results\nNext: run the evals.\n")
    (repo / "dates.py").write_text("def parse():\n    return None\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base", "--date", "2026-11-01T00:00:00")
    home = tmp_path / "home"
    claude = home / ".claude/projects"
    ide, cli = home / ".gemini/antigravity/brain", home / ".gemini/antigravity-cli/brain"
    codex = home / ".codex/sessions"
    monkeypatch.setenv("GHOSTKEEP_CLAUDE_DIR", str(claude))
    monkeypatch.setenv("GHOSTKEEP_ANTIGRAVITY_DIRS", f"antigravity-ide={ide};antigravity-cli={cli}")
    monkeypatch.setenv("GHOSTKEEP_CODEX_DIR", str(codex))
    monkeypatch.chdir(repo)
    main(["init"])
    return {"repo": repo, "claude": claude / sources.claude_slug(repo), "ide": ide, "cli": cli, "codex": codex}


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def claude_session(env, sid, rows):
    write_jsonl(env["claude"] / f"{sid}.jsonl", rows)


def ag_session(env, which, sid, rows):
    write_jsonl(env[which] / sid / ".system_generated/logs/transcript.jsonl", rows)


def c_user(text, ts="2026-11-10T15:50:00Z"):
    return {"type": "user", "timestamp": ts, "cwd": "x", "origin": {"kind": "human"},
            "message": {"role": "user", "content": text}}


def c_edit(path, old, new, ts="2026-11-10T15:52:00Z"):
    return {"type": "assistant", "timestamp": ts, "message": {"model": "claude-opus-5", "role": "assistant",
            "content": [{"type": "tool_use", "name": "Edit", "input":
                         {"file_path": str(path), "old_string": old, "new_string": new}}]}}


def ag(step_type, ts="2026-11-10T15:30:00Z", **kw):
    return {"step_index": 0, "source": "MODEL", "type": step_type, "status": "DONE", "created_at": ts, **kw}


# --- unit pieces ---------------------------------------------------------------------

def test_line_delta_matches_git_counting():
    assert sources.line_delta("a\nb\n", "a\nb\nc\n") == (1, 0)
    assert sources.line_delta("a\nb\n", "a\nB\n") == (1, 1)
    assert sources.line_delta("x", "x\n<!-- TODO -->\nit is completed") == (2, 0)


def test_relpath_windows_and_outside():
    root = Path("E:\\Projects\\teamcaptain")
    assert sources.relpath("E:\\Projects\\teamcaptain\\docs\\RESULTS.md", root) == "docs/RESULTS.md"
    assert sources.relpath("e:\\projects\\TEAMCAPTAIN\\a.py", root) == "a.py"
    assert sources.relpath("E:\\Projects\\other\\a.py", root) is None


def test_redaction():
    assert "sk-" not in sources.clip("key is sk-abcdefghijklmnopqrstuvwx ok")
    assert "[redacted]" in sources.clip("api_key=hunter2")
    assert sources.clip("docs/LINKEDIN_FEATURE_ARCHITECTURE.md") == "docs/LINKEDIN_FEATURE_ARCHITECTURE.md"


def test_decisions_from_user_words():
    found = decisions.find("Go with Option 1, the /export Telegram command. Option 2 (the FastAPI "
                           "CSV endpoint) is rejected: it would expose every team's commitments. "
                           "Now write the architecture. Should we use SQLite?")
    kinds = [k for k, _ in found]
    assert kinds == ["decision", "decision"]
    assert found[1][1].startswith("Option 2")
    assert decisions.find("Always run the rules evaluation after changing extraction.")[0][0] == "preference"


# --- the baseline scenarios ------------------------------------------------------------

def test_s1_ide_edit_claims_one_line_but_three_landed(env):
    repo = env["repo"]
    ag_session(env, "ide", "a4ddd84e", [
        ag("USER_INPUT", source="USER_EXPLICIT",
           content=f"<USER_REQUEST>\nAdd one line \"it is completed\" at the end of docs/RESULTS.md.\n</USER_REQUEST>\nworkspace {repo}"),
        ag("PLANNER_RESPONSE", tool_calls=[{"name": "edit_file", "args": {
            "Path": str(repo / "docs/RESULTS.md"), "Target": "Next: run the evals.",
            "Replacement": "Next: run the evals.\nit is completed"}}]),
        ag("PLANNER_RESPONSE", content="Added the line \"it is completed\" at the end of docs/RESULTS.md."),
    ])
    with (repo / "docs/RESULTS.md").open("a") as fh:  # what actually landed: +3
        fh.write("\n<!-- TODO: placeholder -->\nit is completed\n")
    rep, _ = sync.run(repo)
    assert rep.claims_added == 1
    [c] = ledger.claims(ledger.read(repo))
    assert c.tool == "antigravity-ide" and c.asked.startswith("Add one line")
    assert (c.files[0].added, c.files[0].removed) == (1, 0)
    results = check.run(repo)
    assert [r.status for r in results] == ["mismatch"]  # and NOT an orphan: attribution is known


def test_s3_interrupted_claude_task_is_first_in_handoff(env):
    repo = env["repo"]
    claude_session(env, "c03c16ef", [
        c_user('Fix known limitation ex007: "give me 3 days" isn\'t recognised. Steps: (1) add the phrase '
               "to dates.py, (2) add a unit test, (3) run the rules evaluation and update docs/RESULTS.md."),
        c_edit(repo / "dates.py", "    return None\n", "    return None\n\nDURATION = r'give me (\\d+) days'\n"),
        {"type": "user", "timestamp": "2026-11-10T15:56:00Z", "interruptedMessageId": "m1",
         "message": {"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user]"}]}},
    ])
    with (repo / "dates.py").open("a") as fh:
        fh.write("\nDURATION = r'give me (\\d+) days'\n")
    # An unrelated, finished Antigravity session from earlier (the CSV export doc).
    ag_session(env, "cli", "4492d3f0", [
        ag("USER_INPUT", ts="2026-11-10T15:20:00Z", content=f"<USER_REQUEST>What new feature?</USER_REQUEST> {repo}"),
        ag("PLANNER_RESPONSE", ts="2026-11-10T15:21:00Z", content="The CSV export feature."),
    ])
    rep, _ = sync.run(repo)
    assert rep.claims_added == 1 and rep.skipped_no_edits == 1
    [c] = ledger.claims(ledger.read(repo))
    assert c.interrupted and "interrupted" in c.open[0] and "ex007" in c.open[0]
    text = handoff.build(repo, check.run(repo))
    unfinished = text.split("## Unfinished")[1].split("##")[0]
    assert "claude-code" in unfinished and "dates.py" in unfinished
    assert "CSV export" not in unfinished
    assert len(text.splitlines()) <= 60


def test_s2_decision_in_chat_reaches_handoff(env):
    repo = env["repo"]
    ag_session(env, "ide", "60903289", [
        ag("USER_INPUT", source="USER_EXPLICIT", content=f"<USER_REQUEST>Propose two options for a CSV export.</USER_REQUEST> {repo}"),
        ag("USER_INPUT", source="USER_EXPLICIT", content="<USER_REQUEST>Go with Option 1, the /export Telegram command. "
           "Option 2 (the FastAPI CSV endpoint) is rejected: it exposes data with no login. "
           "Now write the architecture to docs/EXPORT_FEATURE.md.</USER_REQUEST>"),
        ag("PLANNER_RESPONSE", tool_calls=[{"name": "write_file", "args": {
            "Path": str(repo / "docs/EXPORT_FEATURE.md"), "Content": "# Export\nOption 1\n", "Overwrite": "false"}}]),
        ag("PLANNER_RESPONSE", content="Wrote docs/EXPORT_FEATURE.md."),
    ])
    (repo / "docs/EXPORT_FEATURE.md").write_text("# Export\nOption 1\n")
    rep, _ = sync.run(repo)
    assert rep.decisions_added == 2
    results = check.run(repo)
    assert [r.status for r in results] == ["uncommitted"]
    text = handoff.build(repo, results)
    assert "Option 2 (the FastAPI CSV endpoint) is rejected" in text
    assert "EXPORT_FEATURE.md` (new file) by antigravity-ide" in text


def test_change_with_no_session_is_still_orphan(env):
    repo = env["repo"]
    (repo / "stray.py").write_text("x = 1\n")
    sync.run(repo)
    text = handoff.build(repo, check.run(repo))
    assert "`stray.py` (new file) by **unknown: no session claims it**" in text


def test_sync_is_idempotent_and_growing_session_supersedes(env):
    repo = env["repo"]
    rows = [c_user("add X to dates.py"), c_edit(repo / "dates.py", "    return None\n", "    return None\nX = 1\n")]
    claude_session(env, "s1", rows)
    with (repo / "dates.py").open("a") as fh:
        fh.write("X = 1\n")
    assert sync.run(repo)[0].claims_added == 1
    assert sync.run(repo)[0].claims_added == 0  # nothing new
    claude_session(env, "s1", rows + [c_edit(repo / "dates.py", "X = 1\n", "X = 1\nY = 2\n", ts="2026-11-10T16:00:00Z")])
    import os, time
    os.utime(env["claude"] / "s1.jsonl", (time.time() + 5, time.time() + 5))
    assert sync.run(repo)[0].claims_added == 1
    statuses = [r.status for r in check.run(repo)]
    assert statuses[0] == "superseded"


def codex_session(env, name, rows):
    d = env["codex"] / "2026/11/11"
    write_jsonl(d / f"{name}.jsonl", rows)


def cx_meta(repo, commit="abc123", branch="main"):
    return {"timestamp": "2026-11-11T10:00:00Z", "type": "session_meta",
            "payload": {"type": "session_meta", "cwd": str(repo), "cli_version": "0.161.0",
                        "source": "vscode", "git": {"commit_hash": commit, "branch": branch}}}


def cx_user(text, ts="2026-11-11T10:01:00Z"):
    return {"timestamp": ts, "type": "response_item",
            "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}}


def cx_exec(cmd, ts="2026-11-11T10:02:00Z"):
    return {"timestamp": ts, "type": "response_item",
            "payload": {"type": "function_call", "name": "exec_command",
                        "arguments": json.dumps({"cmd": cmd})}}


def cx_assistant(text, ts="2026-11-11T10:03:00Z"):
    return {"timestamp": ts, "type": "response_item",
            "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}}


def cx_event(ptype, ts="2026-11-11T10:04:00Z"):
    return {"timestamp": ts, "type": "event_msg", "payload": {"type": ptype}}


def test_codex_apply_patch_counts_and_base_commit(env):
    repo = env["repo"]
    patch = ("apply_patch << 'EOF'\n*** Begin Patch\n*** Update File: dates.py\n"
             "@@\n-    return None\n+    return None\n+X = 1\n*** End Patch\nEOF")
    codex_session(env, "rollout-a", [
        cx_meta(repo, commit="feedface"), cx_user("add X to dates.py"),
        cx_exec(patch), cx_assistant("Added X."), cx_event("task_started"), cx_event("task_complete"),
    ])
    with (repo / "dates.py").open("a") as fh:
        fh.write("X = 1\n")
    rep, _ = sync.run(repo)
    assert rep.claims_added == 1
    [c] = ledger.claims(ledger.read(repo))
    assert c.tool == "codex" and c.base == "feedface"  # base commit read straight from session_meta
    assert (c.files[0].path, c.files[0].added, c.files[0].removed) == ("dates.py", 2, 1)


def test_codex_shell_write_detected_counts_unknown(env):
    repo = env["repo"]
    codex_session(env, "rollout-b", [
        cx_meta(repo), cx_user("write a note"),
        cx_exec('Set-Content -Path docs\\RESULTS.md -Value "done"'),
        cx_assistant("Wrote it."),
    ])
    (repo / "docs/RESULTS.md").write_text("# Results\ndone\n")
    sync.run(repo)
    [c] = ledger.claims(ledger.read(repo))
    assert c.files[0].path == "docs/RESULTS.md" and c.files[0].added is None


def test_codex_interrupted_when_no_task_complete(env):
    repo = env["repo"]
    codex_session(env, "rollout-c", [
        cx_meta(repo), cx_user("fix dates"),
        cx_exec("apply_patch << 'EOF'\n*** Update File: dates.py\n+A = 1\nEOF"),
        cx_event("task_started"),  # no task_complete
    ])
    with (repo / "dates.py").open("a") as fh:
        fh.write("A = 1\n")
    sync.run(repo)
    [c] = ledger.claims(ledger.read(repo))
    assert c.interrupted and "task_complete" in c.open[0]


def test_codex_session_outside_repo_ignored(env):
    repo = env["repo"]
    codex_session(env, "rollout-d", [
        {"timestamp": "2026-11-11T10:00:00Z", "type": "session_meta",
         "payload": {"type": "session_meta", "cwd": "E:\\Other\\project", "git": {"commit_hash": "x"}}},
        cx_user("do a thing"), cx_exec("apply_patch << 'EOF'\n*** Update File: a.py\n+x\nEOF"),
    ])
    assert sync.run(repo)[0].claims_added == 0


def test_cli_handoff_writes_file(env, capsys):
    repo = env["repo"]
    assert main(["handoff"]) == 0
    assert (repo / ".ghostkeep/HANDOFF.md").read_text().startswith("# Handoff")
