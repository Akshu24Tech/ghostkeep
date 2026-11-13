from pathlib import Path

from ghostkeep import ledger


def test_init_keeps_ledger_out_of_git(tmp_path: Path):
    ledger.init(tmp_path)
    assert (tmp_path / ".ghostkeep" / ".gitignore").read_text().strip().endswith("*")
    assert not (tmp_path / ".gitignore").exists()  # the project's own .gitignore is untouched
