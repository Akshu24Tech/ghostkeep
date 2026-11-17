import json
import subprocess
from pathlib import Path

from ghostkeep import cli, health, setup


def _repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def test_install_is_idempotent_and_keeps_existing_settings(tmp_path):
    root = _repo(tmp_path)
    (root / ".claude").mkdir()
    (root / ".claude/settings.local.json").write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}}))
    (root / "AGENTS.md").write_text("# Rules\nUse tabs.\n")
    setup.install(root)
    setup.install(root)
    data = json.loads((root / ".claude/settings.local.json").read_text())
    assert data["permissions"] == {"allow": ["Bash(ls)"]}
    assert len(data["hooks"]["SessionStart"]) == 1
    assert setup.MARK in data["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    agents = (root / "AGENTS.md").read_text()
    assert agents.startswith("# Rules\nUse tabs.\n") and agents.count(setup.BLOCK_START) == 1
    assert ".claude/settings.local.json" in (root / ".git/info/exclude").read_text()
    assert not (root / ".gitignore").exists()  # the project's own .gitignore is never edited
    assert setup.status(root)["installed"]


def test_remove_undoes_only_ghostkeep(tmp_path):
    root = _repo(tmp_path)
    (root / "AGENTS.md").write_text("# Rules\nUse tabs.\n")
    setup.install(root)
    setup.remove(root)
    assert (root / "AGENTS.md").read_text() == "# Rules\nUse tabs.\n"
    assert "hooks" not in json.loads((root / ".claude/settings.local.json").read_text())
    assert not setup.status(root)["installed"]


def test_bad_settings_json_is_never_overwritten(tmp_path):
    root = _repo(tmp_path)
    (root / ".claude").mkdir()
    (root / ".claude/settings.local.json").write_text("{not json")
    try:
        setup.install(root)
        raise AssertionError("should refuse")
    except SystemExit:
        pass
    assert (root / ".claude/settings.local.json").read_text() == "{not json"


def test_hook_never_fails_and_records_its_run(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    assert cli.main(["handoff", "--hook"]) == 0
    assert "# Handoff" in capsys.readouterr().out
    rec = json.loads((root / ".ghostkeep/hook.json").read_text())
    assert rec["ok"] is True and rec["last_run"]
    outside = tmp_path.parent / (tmp_path.name + "_nogit")
    outside.mkdir()
    monkeypatch.chdir(outside)
    assert cli.main(["handoff", "--hook"]) == 0  # not a git repo: still exits 0


def test_doctor_flags_missing_setup(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    lines = health.check(root)
    assert any(ln.what == "auto-handoff" and ln.level == health.WARN for ln in lines)
    assert cli.main(["doctor"]) == 1
    setup.install(root, agents_md=False)
    cli.main(["handoff", "--hook"])
    assert any(ln.what == "auto-handoff" and ln.level == health.OK for ln in health.check(root))
