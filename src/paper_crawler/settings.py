from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Settings:
    contact_email: str
    database_url: str
    arxiv_categories: list[str]
    lookback_hours: int
    keyword_groups: dict[str, list[str]]
    issn_whitelist: dict[str, dict[str, Any]]
    synonyms: dict[str, list[str]]
    semantic_threshold: float
    enable_semantic_matching: bool


def _read_yaml(file_path: Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_settings(config_dir: Path) -> Settings:
    config = _read_yaml(config_dir / "config.yaml")
    keywords = _read_yaml(config_dir / "keywords.yaml")
    issn_whitelist = _read_yaml(config_dir / "issn_whitelist.yaml")
    synonyms = _read_yaml(config_dir / "synonyms.yaml")
    runtime = config["runtime"]
    sources = config["sources"]

    return Settings(
        contact_email=config["contact_email"],
        database_url=config["database_url"],
        arxiv_categories=sources["arxiv_categories"],
        lookback_hours=int(runtime["lookback_hours"]),
        keyword_groups=keywords,
        issn_whitelist=issn_whitelist,
        synonyms=synonyms,
        semantic_threshold=float(runtime["semantic_threshold"]),
        enable_semantic_matching=bool(runtime["enable_semantic_matching"]),
    )
