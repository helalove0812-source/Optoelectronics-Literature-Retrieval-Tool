from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SMTPSettings:
    host: str
    port: int
    username: str
    from_address: str
    to_address: str
    use_tls: bool


@dataclass
class LLMSettings:
    enabled: bool
    provider: str
    base_url: str
    model: str
    timeout_seconds: int


@dataclass
class Settings:
    contact_email: str
    database_url: str
    smtp: SMTPSettings
    llm: LLMSettings
    arxiv_categories: list[str]
    openalex_filters: list[str]
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
    smtp = config["smtp"]
    llm = config.get("llm", {})

    return Settings(
        contact_email=config["contact_email"],
        database_url=config["database_url"],
        smtp=SMTPSettings(
            host=smtp["host"],
            port=int(smtp["port"]),
            username=smtp["username"],
            from_address=smtp["from_address"],
            to_address=smtp["to_address"],
            use_tls=bool(smtp.get("use_tls", True)),
        ),
        llm=LLMSettings(
            enabled=bool(llm.get("enabled", False)),
            provider=str(llm.get("provider", "deepseek")),
            base_url=str(llm.get("base_url", "https://api.deepseek.com")),
            model=str(llm.get("model", "deepseek-chat")),
            timeout_seconds=int(llm.get("timeout_seconds", 30)),
        ),
        arxiv_categories=sources["arxiv_categories"],
        openalex_filters=sources.get("openalex_filters", []),
        lookback_hours=int(runtime["lookback_hours"]),
        keyword_groups=keywords,
        issn_whitelist=issn_whitelist,
        synonyms=synonyms,
        semantic_threshold=float(runtime["semantic_threshold"]),
        enable_semantic_matching=bool(runtime["enable_semantic_matching"]),
    )
