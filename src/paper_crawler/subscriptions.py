from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class TopicConfig:
    topic_id: str
    name: str
    arxiv_categories: list[str]
    openalex_filters: list[str]
    keyword_groups: dict[str, list[str]]
    synonyms: dict[str, list[str]]
    issn_whitelist: dict[str, dict[str, str]] | None = None


@dataclass(slots=True)
class SubscriptionConfig:
    name: str
    email: str
    topic_id: str
    keywords: list[str]


@dataclass(slots=True)
class LabSubscriptions:
    topics: dict[str, TopicConfig]
    subscriptions: list[SubscriptionConfig]


def _read_yaml(file_path: Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_lab_subscriptions(config_dir: Path) -> LabSubscriptions:
    topics_payload = _read_yaml(config_dir / "topics.yaml")
    subscriptions_payload = _read_yaml(config_dir / "subscriptions.yaml")

    topics = {
        item["topic_id"]: TopicConfig(
            topic_id=item["topic_id"],
            name=item["name"],
            arxiv_categories=item.get("arxiv_categories", []),
            openalex_filters=item.get("openalex_filters", []),
            keyword_groups=item.get("keyword_groups", {}),
            synonyms=item.get("synonyms", {}),
            issn_whitelist=item.get("issn_whitelist"),
        )
        for item in topics_payload.get("topics", [])
    }

    subscriptions = [
        SubscriptionConfig(
            name=item["name"],
            email=item["email"],
            topic_id=item["topic_id"],
            keywords=item.get("keywords", []),
        )
        for item in subscriptions_payload.get("subscriptions", [])
    ]

    for subscription in subscriptions:
        if subscription.topic_id not in topics:
            raise ValueError(f"Unknown topic_id: {subscription.topic_id}")

    return LabSubscriptions(topics=topics, subscriptions=subscriptions)
