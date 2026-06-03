from pathlib import Path

from paper_crawler.settings import load_settings


def test_load_settings_reads_all_yaml_files():
    root = Path(__file__).resolve().parents[1]

    settings = load_settings(root / "config")

    assert settings.contact_email == "team@example.com"
    assert "physics.optics" in settings.arxiv_categories
    assert "silicon photonics" in settings.keyword_groups["硅光"]
    assert settings.issn_whitelist["Optics Express"]["issn"] == "1094-4087"
