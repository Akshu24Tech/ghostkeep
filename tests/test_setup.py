import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from ghostkeep import cli, health, setup

ALL = ["antigravity", "gemini-cli", "claude-code"]


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


def _run_hook(monkeypatch, capsys, tool, stdin="", cwd=None):
    if cwd:
        monkeypatch.chdir(cwd)
    fake = io.StringIO(stdin)
    fake.isatty = lambda: False
    monkeypatch.setattr(sys, "stdin", fake)
    assert cli.main(["handoff", "--hook", "--format", tool]) == 0
    return capsys.readouterr().out


def test_install_every_tool_keeps_existing_config_and_is_idempotent(tmp_path):
    root = _repo(tmp_path)
    (root / ".agents").mkdir()
    (root / ".agents/hooks.json").write_text(json.dumps({"lint": {"Stop": [{"type": "command", "command": "ruff"}]}}))
    (root / ".gemini").mkdir()
    (root / ".gemini/settings.json").write_text(json.dumps({"theme": "dark"}))
    (root / "AGENTS.md").write_text("# Rules\nUse tabs.\n")
    setup.install(root, tools=ALL)
    setup.install(root, tools=ALL)
    ag = json.loads((root / ".agents/hooks.json").read_text())
    assert ag["lint"] == {"Stop": [{"type": "command", "command": "ruff"}]}
    assert setup.MARK in ag[setup.AG_NAME]["SessionStart"][0]["command"]
    assert "--format antigravity" in ag[setup.AG_NAME]["SessionStart"][0]["command"]
    gm = json.loads((root / ".gemini/settings.json").read_text())
    assert gm["theme"] == "dark" and len(gm["hooks"]["SessionStart"]) == 1
    assert gm["hooks"]["SessionStart"][0]["hooks"][0]["timeout"] == 60000  # Gemini counts milliseconds
    cc = json.loads((root / ".claude/settings.local.json").read_text())
    assert len(cc["hooks"]["SessionStart"]) == 1
    assert (root / "AGENTS.md").read_text().count(setup.BLOCK_START) == 1
    st = setup.status(root)
    assert all(st[t]["installed"] for t in ALL) and st["agents-md"]["installed"]
    assert not (root / ".gitignore").exists()  # the project's .gitignore is never edited


def test_portable_command_when_ghostkeep_is_on_path(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/usr/bin/ghostkeep")
    setup.install(root, tools=["antigravity"], agents_md=False)
    cmd = json.loads((root / ".agents/hooks.json").read_text())[setup.AG_NAME]["SessionStart"][0]["command"]
    assert cmd == "ghostkeep handoff --hook --format antigravity"
    exclude = root / ".git/info/exclude"
    assert ".agents/hooks.json" not in (exclude.read_text() if exclude.exists() else "")  # shareable, so committable


def test_pinned_python_command_is_kept_out_of_git(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    setup.install(root, tools=["gemini-cli"], agents_md=False)
    assert ".gemini/settings.json" in (root / ".git/info/exclude").read_text()


def test_remove_undoes_only_ghostkeep(tmp_path):
    root = _repo(tmp_path)
    (root / ".agents").mkdir()
    (root / ".agents/hooks.json").write_text(json.dumps({"lint": {"Stop": [{"type": "command", "command": "ruff"}]}}))
    (root / "AGENTS.md").write_text("# Rules\nUse tabs.\n")
    setup.install(root, tools=ALL)
    setup.remove(root)
    assert json.loads((root / ".agents/hooks.json").read_text()) == {"lint": {"Stop": [{"type": "command", "command": "ruff"}]}}
    assert (root / "AGENTS.md").read_text() == "# Rules\nUse tabs.\n"
    assert not any(setup.status(root)[t]["installed"] for t in ALL)


def test_bad_json_is_never_overwritten(tmp_path):
    root = _repo(tmp_path)
    (root / ".agents").mkdir()
    (root / ".agents/hooks.json").write_text("{not json")
    with pytest.raises(SystemExit):
        setup.install(root, tools=["antigravity"])
    assert (root / ".agents/hooks.json").read_text() == "{not json"


def test_each_tool_gets_its_own_output_shape(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    ag = json.loads(_run_hook(monkeypatch, capsys, "antigravity", cwd=root))
    assert "# Handoff" in ag["injectSteps"][0]["systemMessage"]["systemMessage"]
    gm = json.loads(_run_hook(monkeypatch, capsys, "gemini-cli", cwd=root))
    assert gm["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "# Handoff" in gm["hookSpecificOutput"]["additionalContext"]
    cc = _run_hook(monkeypatch, capsys, "claude-code", cwd=root)
    assert "# Handoff" in cc and not cc.lstrip().startswith("{")
    runs = setup.runs(root)
    assert set(runs) == set(ALL) and all(r["ok"] for r in runs.values())


def test_hook_finds_the_project_from_stdin(tmp_path, monkeypatch, capsys):
    """Antigravity passes workspacePaths; the hook process may start somewhere else."""
    root = _repo(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    out = _run_hook(monkeypatch, capsys, "antigravity", json.dumps({"workspacePaths": [str(root)]}), cwd=elsewhere)
    assert "# Handoff" in json.loads(out)["injectSteps"][0]["systemMessage"]["systemMessage"]
    assert setup.runs(root)["antigravity"]["ok"]


def test_hook_failure_still_prints_valid_output(tmp_path, monkeypatch, capsys):
    nogit = tmp_path / "nogit"
    nogit.mkdir()
    assert json.loads(_run_hook(monkeypatch, capsys, "antigravity", cwd=nogit)) == {}
    assert json.loads(_run_hook(monkeypatch, capsys, "gemini-cli", cwd=nogit)) == {}
    assert _run_hook(monkeypatch, capsys, "claude-code", cwd=nogit).strip() == ""


def test_v050_flat_hook_record_still_reads_as_claude(tmp_path):
    root = _repo(tmp_path)
    (root / ".ghostkeep").mkdir()
    (root / ".ghostkeep/hook.json").write_text(json.dumps({"last_run": "2026-11-17T22:20", "ok": True, "error": None}))
    assert setup.runs(root)["claude-code"]["ok"]


def test_detect_uses_home_folders(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".gemini/antigravity-cli").mkdir(parents=True)
    (home / ".gemini/settings.json").write_text("{}")  # Antigravity writes this too: not a Gemini CLI sign
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    assert setup.detect() == ["antigravity"]


def test_doctor_reports_each_hook(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    assert any(ln.what == "auto-handoff" and ln.level == health.WARN for ln in health.check(root))
    setup.install(root, tools=["antigravity"], agents_md=False)
    assert any("never run" in ln.msg for ln in health.check(root))
    _run_hook(monkeypatch, capsys, "antigravity", cwd=root)
    lines = [ln for ln in health.check(root) if ln.what == "auto-handoff"]
    assert len(lines) == 1 and lines[0].level == health.OK and "Antigravity" in lines[0].msg
