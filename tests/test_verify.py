import json
import subprocess
import sys

from ghostkeep import cli, ledger, verify


def test_claims_tests():
    yes = ["All tests pass.", "Tests are passing now.", "Done, 34 passed.", "The test suite passes.",
           "Added X; tests still pass", "all green"]
    no = ["The tests don't pass yet.", "3 passed, 2 failed.", "I did not run the tests.", "Tests fail on Windows.",
          "I'll make the tests pass next.", "Updated the README."]
    assert all(verify.claims_tests(t) for t in yes), [t for t in yes if not verify.claims_tests(t)]
    assert not any(verify.claims_tests(t) for t in no), [t for t in no if verify.claims_tests(t)]


def test_parse_and_verdict():
    assert verify.parse("..\n34 passed, 2 skipped in 1.2s") == {"passed": 34, "skipped": 2}
    assert verify.parse("Ran 12 tests in 0.3s\n\nOK") == {"ran": 12}
    ok, why = verify.verdict({"exit": 0, "counts": {"passed": 34}}, None)
    assert ok and why == "34 passed"
    assert verify.verdict({"exit": 0, "counts": {}}, None) == (False, "exit 0 but no tests ran")
    assert verify.verdict({"exit": 1, "counts": {"passed": 3, "failed": 2}}, None) == (False, "exit 1, 2 failed")
    ok, why = verify.verdict({"exit": 0, "counts": {"passed": 30}}, {"counts": {"passed": 34}})
    assert not ok and "fewer than last run (34)" in why
    assert verify.verdict({"exit": None, "summary": "timed out after 5s", "counts": {}}, None) == (False, "timed out after 5s")


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    ledger.init(tmp_path)
    return tmp_path


def test_pin_test_cli(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    assert cli.main(["pin-test", "python -m pytest -q", "--timeout", "90"]) == 0
    assert verify.load_config(root) == {"test_command": "python -m pytest -q", "test_timeout": 90}
    assert cli.main(["pin-test", "--clear"]) == 0
    assert verify.load_config(root) == {}


def test_run_only_once_per_claim_and_state(tmp_path):
    root = _repo(tmp_path / "proj") if (tmp_path / "proj").mkdir() is None else None
    marker = tmp_path / "count.txt"  # outside the repo, so writing it doesn't change the checked files
    verify.pin(root, f'"{sys.executable}" -c "import pathlib; p=pathlib.Path(r\'{marker}\'); '
                     f'p.write_text(p.read_text()+\'x\' if p.exists() else \'x\'); print(\'2 passed\')"')
    ledger.append(root, {"v": 1, "kind": "claim", "id": "e_1", "ts": "2026-11-21T10:00:00", "tool": "claude-code",
                         "asked": "a", "claimed": "tests pass", "files": [], "tests_claimed": True})
    first = verify.run(root)
    assert first["ok"] and first["why"] == "2 passed"
    assert verify.run(root) is None  # same claim, same files: not run again
    assert marker.read_text() == "x"


def test_chain_detects_edits_and_ack_clears_them(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    for k in range(4):
        ledger.append(root, {"v": 1, "kind": "decision", "id": f"d_{k}", "ts": "t", "text": f"use lib{k}"})
    assert ledger.chain_breaks(root) == []
    p = ledger.ledger_path(root)
    lines = p.read_text().splitlines()
    lines[1] = lines[1].replace("lib1", "libX")
    p.write_text("\n".join(lines) + "\n")
    assert ledger.chain_breaks(root) == [3]
    del lines[2]  # and remove a line
    p.write_text("\n".join(lines) + "\n")
    assert ledger.chain_breaks(root) == [3]
    monkeypatch.chdir(root)
    assert cli.main(["ack-ledger", "--reason", "fixed a typo by hand"]) == 0
    assert ledger.chain_breaks(root) == []
    ledger.append(root, {"v": 1, "kind": "decision", "id": "d_9", "ts": "t", "text": "later"})
    assert ledger.chain_breaks(root) == []  # new lines chain on from the ack


def test_old_unchained_ledger_is_not_a_break(tmp_path):
    root = _repo(tmp_path)
    p = ledger.ledger_path(root)
    p.write_text(json.dumps({"v": 1, "kind": "decision", "id": "d_old", "ts": "t", "text": "pre v0.6"}) + "\n")
    ledger.append(root, {"v": 1, "kind": "decision", "id": "d_new", "ts": "t", "text": "v0.6"})
    assert ledger.chain_breaks(root) == []


def test_same_session_owns_a_file_once(tmp_path):
    from ghostkeep import check, handoff
    root = _repo(tmp_path)
    (root / "demo.md").write_text("x\n")
    for rev in ("1:1", "2:2"):  # the same session read twice because its log grew
        ledger.append(root, {"v": 1, "kind": "claim", "id": f"e_{rev[0]}", "ts": "2026-11-16T21:43:00",
                             "tool": "claude-code", "session": "s1", "source_rev": rev, "asked": "a", "claimed": "c",
                             "files": [{"path": "demo.md", "added": None, "removed": None}]})
    text = handoff.build(root, check.run(root, write=False))
    line = next(ln for ln in text.splitlines() if "`demo.md`" in ln)
    assert line.count("claude-code") == 1, line
