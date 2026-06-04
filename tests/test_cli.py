from pathlib import Path

import paper_crawler.cli as cli


def test_main_loads_root_dotenv_without_overriding_existing_env(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    dotenv_path = project_root / ".env"
    dotenv_path.write_text(
        "SMTP_PASSWORD=from-dotenv\nDEEPSEEK_API_KEY=dotenv-key\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli,
        "PROJECT_ROOT",
        project_root,
    )
    monkeypatch.setenv("SMTP_PASSWORD", "from-shell")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(cli, "configure_logging", lambda: None)
    monkeypatch.setattr(
        cli,
        "run_application",
        lambda path: "ok",
    )
    monkeypatch.setattr(
        cli.argparse.ArgumentParser,
        "parse_args",
        lambda self: type("Args", (), {"command": "run", "config": "config"})(),
    )

    assert cli.main() == 0
    assert cli.os.getenv("SMTP_PASSWORD") == "from-shell"
    assert cli.os.getenv("DEEPSEEK_API_KEY") == "dotenv-key"


def test_main_skips_missing_root_dotenv(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    called: list[Path] = []
    monkeypatch.setattr(cli, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(cli, "configure_logging", lambda: None)
    monkeypatch.setattr(
        cli,
        "run_application",
        lambda path: called.append(path) or "ok",
    )
    monkeypatch.setattr(
        cli.argparse.ArgumentParser,
        "parse_args",
        lambda self: type("Args", (), {"command": "run", "config": "config"})(),
    )

    assert cli.main() == 0
    assert called == [Path("config")]


def test_env_example_contains_deepseek_api_key() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "SMTP_PASSWORD=" in env_example
    assert "DEEPSEEK_API_KEY=" in env_example
