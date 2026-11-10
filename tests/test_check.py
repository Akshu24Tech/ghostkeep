"""Scenarios taken from the Day 1 baseline on teamcaptain (10 Nov 2026)."""
import json
import subprocess
from pathlib import Path

import pytest

from ghostkeep import check, ledger
from ghostkeep.cli import main


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "RESULTS.md").write_text("# Results\n\nNext: run the evals.\n")
    (tmp_path / "dates.py").write_text("def parse():\n    return None\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    return tmp_path


def append(path: Path, text: str):
    with path.open("a") as fh:
        fh.write(text)


def statuses(results):
    return {r.status for r in results}


def test_s1_agent_claims_one_line_but_writes_three(repo):
    # The IDE agent in video 1 was asked for one line and also added a TODO comment.
    append(repo / "docs/RESULTS.md", "\n<!-- TODO: placeholder -->\nit is completed\n")
    main(["log", "--tool", "antigravity-ide",
          "--asked", 'Add one line "it is completed" at the end of docs/RESULTS.md.',
          "--claimed", "Added the line.", "--file", "docs/RESULTS.md:+1-0"])
    [r] = check.run(repo)
    assert r.status == "mismatch"
    assert r.findings[0].code == "count_mismatch"
    assert r.findings[0].expected == "+1 -0" and r.findings[0].actual == "+3 -0"


def test_s1_change_with_no_claim_is_orphan(repo):
    # Baseline: both CLIs guessed who made this change, and both guessed wrong.
    append(repo / "docs/RESULTS.md", "it is completed\n")
    [r] = check.run(repo)
    assert r.status == "orphan"
    assert r.findings[0].path == "docs/RESULTS.md"


def test_s2_untracked_design_doc_is_uncommitted_not_final(repo):
    # Baseline: Antigravity CLI called this uncommitted draft "complete and final".
    (repo / "docs/EXPORT_FEATURE.md").write_text("# Export\nOption 1 chosen.\nOption 2 rejected.\n")
    main(["log", "--tool", "antigravity-ide", "--asked", "Write the architecture to docs/EXPORT_FEATURE.md",
          "--claimed", "Wrote the design.", "--file", "docs/EXPORT_FEATURE.md:+3"])
    [r] = check.run(repo)
    assert r.status == "uncommitted"
    assert r.findings[0].code == "untracked"


def test_s3_interrupted_task_keeps_open_items(repo):
    append(repo / "dates.py", "DURATION = r'give me (\\d+) days'\n")
    main(["log", "--tool", "claude-code", "--asked", "Fix known limitation ex007",
          "--claimed", "Added the duration pattern (step 1 of 3).", "--file", "dates.py:+1-0",
          "--open", "Add a unit test", "--open", "Run rules evaluation and update RESULTS.md"])
    [r] = check.run(repo)
    assert r.status == "uncommitted"
    [c] = ledger.claims(ledger.read(repo))
    assert c.open == ["Add a unit test", "Run rules evaluation and update RESULTS.md"]


def test_verified_after_commit(repo):
    append(repo / "dates.py", "X = 1\n")
    main(["log", "--tool", "codex", "--asked", "add X", "--claimed", "added X", "--file", "dates.py:+1-0"])
    git(repo, "commit", "-qam", "add X")
    [r] = check.run(repo)
    assert r.status == "verified" and r.findings == []


def test_claimed_file_never_changed(repo):
    main(["log", "--tool", "gemini-cli", "--asked", "fix dates", "--claimed", "Fixed dates.py",
          "--file", "dates.py"])
    [r] = check.run(repo)
    assert r.status == "mismatch"
    assert r.findings[0].code == "claimed_not_found"


def test_newer_claim_supersedes_older_for_same_file(repo):
    append(repo / "dates.py", "A = 1\n")
    main(["log", "--tool", "claude-code", "--asked", "a", "--claimed", "a", "--file", "dates.py:+1"])
    append(repo / "dates.py", "B = 2\n")
    main(["log", "--tool", "antigravity-cli", "--asked", "b", "--claimed", "b", "--file", "dates.py:+2"])
    results = check.run(repo)
    assert [r.status for r in results] == ["superseded", "uncommitted"]


def test_ledger_is_append_only_and_checks_not_repeated(repo):
    append(repo / "dates.py", "X = 1\n")
    main(["log", "--tool", "manual", "--asked", "x", "--claimed", "x", "--file", "dates.py:+1"])
    check.run(repo)
    n1 = len(ledger.read(repo))
    check.run(repo)  # nothing changed -> no new record
    assert len(ledger.read(repo)) == n1
    append(repo / "dates.py", "Y = 2\n")  # now counts differ -> new record
    check.run(repo)
    records = ledger.read(repo)
    assert len(records) == n1 + 1
    assert records[-1]["status"] == "mismatch"
    assert records[0]["kind"] == "claim"  # first line untouched


def test_ledger_file_itself_is_never_an_orphan(repo):
    assert check.run(repo) == []


def test_exit_code_and_json(repo, capsys):
    append(repo / "docs/RESULTS.md", "x\n")
    assert main(["check", "--json"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out[0]["status"] == "orphan"


def test_unknown_tool_rejected(repo):
    assert main(["log", "--tool", "chatgpt-pro", "--asked", "a", "--claimed", "b"]) == 2


@pytest.mark.parametrize("spec,exp", [
    ("docs/a.md", ("docs/a.md", None, None)),
    ("docs/a.md:+3", ("docs/a.md", 3, None)),
    ("docs/a.md:+3-1", ("docs/a.md", 3, 1)),
    ("docs\\a.md:-2", ("docs/a.md", None, 2)),
    ("E:\\Projects\\a.md", ("E:/Projects/a.md", None, None)),
])
def test_file_spec_parsing(spec, exp):
    f = ledger.FileClaim.parse(spec)
    assert (f.path, f.added, f.removed) == exp
