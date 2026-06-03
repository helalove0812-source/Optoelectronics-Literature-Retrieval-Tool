from pathlib import Path

from paper_crawler.settings import load_settings


def test_load_settings_reads_all_yaml_files():
    root = Path(__file__).resolve().parents[1]

    settings = load_settings(root / "config")

    assert settings.contact_email == "team@example.com"
    assert "physics.optics" in settings.arxiv_categories
    assert "photonics" not in settings.arxiv_categories
    assert settings.openalex_filters == ["photonics"]
    assert settings.lookback_hours == 24
    assert "silicon photonics" in settings.keyword_groups["硅光"]
    assert settings.issn_whitelist["Optics Express"]["issn"] == "1094-4087"


def test_load_settings_reads_smtp_delivery_fields() -> None:
    root = Path(__file__).resolve().parents[1]

    settings = load_settings(root / "config")

    assert settings.smtp.host == "smtp.example.com"
    assert settings.smtp.port == 587
    assert settings.smtp.username == "research-alert@example.com"
    assert settings.smtp.from_address == "research-alert@example.com"
    assert settings.smtp.to_address == "user@example.com"
    assert settings.smtp.use_tls is True
