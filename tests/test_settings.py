from pathlib import Path

import yaml

from paper_crawler.settings import load_settings


def test_load_settings_reads_all_yaml_files():
    root = Path(__file__).resolve().parents[1]
    config_dir = root / "config"
    config = yaml.safe_load((config_dir / "config.yaml").read_text(encoding="utf-8"))

    settings = load_settings(config_dir)

    assert settings.contact_email == config["contact_email"]
    assert settings.arxiv_categories == config["sources"]["arxiv_categories"]
    assert "photonics" not in settings.arxiv_categories
    assert settings.openalex_filters == config["sources"]["openalex_filters"]
    assert settings.lookback_hours == config["runtime"]["lookback_hours"]
    assert "silicon photonics" in settings.keyword_groups["硅光"]
    assert settings.issn_whitelist["Optics Express"]["issn"] == "1094-4087"


def test_load_settings_reads_smtp_and_llm_fields_from_temp_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_dir.joinpath("config.yaml").write_text(
        "\n".join(
            [
                "contact_email: test@example.com",
                "database_url: sqlite:///data/test.db",
                "smtp:",
                "  host: smtp.test.local",
                "  port: 2525",
                "  username: sender@test.local",
                "  from_address: sender@test.local",
                "  to_address: receiver@test.local",
                "  use_tls: false",
                "llm:",
                "  enabled: true",
                "  provider: deepseek",
                "  base_url: https://api.deepseek.com",
                "  model: deepseek-chat",
                "  timeout_seconds: 45",
                "runtime:",
                "  lookback_hours: 12",
                "  semantic_threshold: 0.7",
                "  enable_semantic_matching: false",
                "sources:",
                "  arxiv_categories:",
                "    - physics.optics",
                "  openalex_filters:",
                "    - concepts.id:C123",
            ]
        ),
        encoding="utf-8",
    )
    config_dir.joinpath("keywords.yaml").write_text("硅光:\n  - silicon photonics\n", encoding="utf-8")
    config_dir.joinpath("issn_whitelist.yaml").write_text("{}", encoding="utf-8")
    config_dir.joinpath("synonyms.yaml").write_text("{}", encoding="utf-8")

    settings = load_settings(config_dir)

    assert settings.smtp.host == "smtp.test.local"
    assert settings.smtp.port == 2525
    assert settings.smtp.username == "sender@test.local"
    assert settings.smtp.from_address == "sender@test.local"
    assert settings.smtp.to_address == "receiver@test.local"
    assert settings.smtp.use_tls is False
    assert settings.llm.enabled is True
    assert settings.llm.provider == "deepseek"
    assert settings.llm.base_url == "https://api.deepseek.com"
    assert settings.llm.model == "deepseek-chat"
    assert settings.llm.timeout_seconds == 45


def test_load_settings_reads_tavily_runtime_fields(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_dir.joinpath("config.yaml").write_text(
        "\n".join(
            [
                "contact_email: test@example.com",
                "database_url: sqlite:///data/test.db",
                "smtp:",
                "  host: smtp.test.local",
                "  port: 2525",
                "  username: sender@test.local",
                "  from_address: sender@test.local",
                "  to_address: receiver@test.local",
                "  use_tls: false",
                "runtime:",
                "  lookback_hours: 12",
                "  semantic_threshold: 0.7",
                "  enable_semantic_matching: false",
                "  enable_tavily_fallback: true",
                "  tavily_max_results: 7",
                "sources:",
                "  arxiv_categories:",
                "    - physics.optics",
                "  openalex_filters:",
                "    - concepts.id:C123",
            ]
        ),
        encoding="utf-8",
    )
    config_dir.joinpath("keywords.yaml").write_text("硅光:\n  - silicon photonics\n", encoding="utf-8")
    config_dir.joinpath("issn_whitelist.yaml").write_text("{}", encoding="utf-8")
    config_dir.joinpath("synonyms.yaml").write_text("{}", encoding="utf-8")

    settings = load_settings(config_dir)

    assert settings.enable_tavily_fallback is True
    assert settings.tavily_max_results == 7


def test_load_settings_defaults_tavily_runtime_fields_when_omitted(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_dir.joinpath("config.yaml").write_text(
        "\n".join(
            [
                "contact_email: test@example.com",
                "database_url: sqlite:///data/test.db",
                "smtp:",
                "  host: smtp.test.local",
                "  port: 2525",
                "  username: sender@test.local",
                "  from_address: sender@test.local",
                "  to_address: receiver@test.local",
                "  use_tls: false",
                "runtime:",
                "  lookback_hours: 12",
                "  semantic_threshold: 0.7",
                "  enable_semantic_matching: false",
                "sources:",
                "  arxiv_categories:",
                "    - physics.optics",
                "  openalex_filters:",
                "    - concepts.id:C123",
            ]
        ),
        encoding="utf-8",
    )
    config_dir.joinpath("keywords.yaml").write_text("硅光:\n  - silicon photonics\n", encoding="utf-8")
    config_dir.joinpath("issn_whitelist.yaml").write_text("{}", encoding="utf-8")
    config_dir.joinpath("synonyms.yaml").write_text("{}", encoding="utf-8")

    settings = load_settings(config_dir)

    assert settings.enable_tavily_fallback is False
    assert settings.tavily_max_results == 5


def test_load_settings_remains_compatible_with_existing_config_files(
    tmp_path: Path,
) -> None:
    (tmp_path / "config.yaml").write_text(
        """
contact_email: team@example.com
database_url: sqlite:///data/papers.db
smtp:
  host: smtp.example.com
  port: 465
  username: sender@example.com
  from_address: sender@example.com
  to_address: receiver@example.com
  use_tls: true
runtime:
  lookback_hours: 24
  semantic_threshold: 0.5
  enable_semantic_matching: true
sources:
  arxiv_categories: [physics.optics]
  openalex_filters: [photonics]
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "keywords.yaml").write_text(
        "silicon:\n  - silicon photonics\n",
        encoding="utf-8",
    )
    (tmp_path / "issn_whitelist.yaml").write_text("{}", encoding="utf-8")
    (tmp_path / "synonyms.yaml").write_text("{}", encoding="utf-8")

    settings = load_settings(tmp_path)

    assert settings.smtp.to_address == "receiver@example.com"
    assert settings.arxiv_categories == ["physics.optics"]
