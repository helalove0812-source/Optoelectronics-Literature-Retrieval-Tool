import sys
from io import StringIO
from pathlib import Path
from contextlib import redirect_stdout

import paper_crawler.cli as cli


def test_cli_run_command_succeeds(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(
        cli,
        "run_application",
        lambda config_dir: f"Pipeline finished: fetched=2, matched=2 from {config_dir}",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["paper-crawler", "run", "--config", str(root / "config")],
    )
    stdout = StringIO()

    with redirect_stdout(stdout):
        exit_code = cli.main()

    assert exit_code == 0
    assert "Pipeline finished: fetched=2, matched=2" in stdout.getvalue()
