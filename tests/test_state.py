import subprocess
from pathlib import Path

from ghostkeep import cli, ledger, state


def test_reversed_terms():
    assert state.reversed_terms("Let's use SQLite instead of JSON.") == {"json"}
    assert state.reversed_terms("switching from Flask to FastAPI") == {"flask"}
    assert state.reversed_terms("We no longer use Redis") == {"redis"}
    assert state.reversed_terms("Don't use Redis for sessions") == {"redis"}
    assert state.reversed_terms("Let's go with Option 1") == set()


def _repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    ledger.init(tmp_path)
    for k, text in enumerate(["Let's use Flask for the API.", "Let's use FastAPI for the API."]):
        ledger.append(tmp_path, {"v": 1, "kind": "decision", "id": f"d_{k}", "ts": f"2026-11-0{k + 1}T10:00:00",
                                 "tool": "claude-code", "session": f"s{k}", "text": text})
    return tmp_path


def test_cli_supersede_retire_reopen(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    assert cli.main(["supersede", "d_0", "d_1"]) == 0
    st = state.build(ledger.read(root))
    assert [d.text for d in st.active()] == ["Let's use FastAPI for the API."]
    assert cli.main(["reopen", "d_0"]) == 0
    assert len(state.build(ledger.read(root)).active()) == 2
    assert cli.main(["retire", "d_1", "--note", "dropped the API"]) == 0
    assert "`d_1` retired by you (dropped the API)" in (root / ".ghostkeep" / "STATE.md").read_text()
    assert cli.main(["retire", "nope"]) == 2
    assert cli.main(["done", "d_0"]) == 2  # done is for threads


def test_ledger_stays_append_only(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    before = ledger.ledger_path(root).read_text()
    cli.main(["retire", "d_0"])
    assert ledger.ledger_path(root).read_text().startswith(before)
