import os
import subprocess
import sys
from pathlib import Path


def test_cli_run_command_succeeds():
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "paper_crawler.cli",
            "run",
            "--config",
            str(root / "config"),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
        env=env,
    )

    assert result.returncode == 0
    assert "Pipeline finished" in result.stdout
