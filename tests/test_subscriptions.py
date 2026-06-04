from pathlib import Path

import pytest

from paper_crawler.subscriptions import load_lab_subscriptions


def test_load_lab_subscriptions_reads_topics_and_subscribers(tmp_path: Path) -> None:
    config_dir = tmp_path
    (config_dir / "topics.yaml").write_text(
        """
topics:
  - topic_id: optoelectronics
    name: 光电子
    arxiv_categories: [physics.optics]
    openalex_filters: [photonics]
    keyword_groups:
      silicon_photonics:
        - silicon photonics
    synonyms:
      vcsel:
        - vertical-cavity surface-emitting laser
""".strip(),
        encoding="utf-8",
    )
    (config_dir / "subscriptions.yaml").write_text(
        """
subscriptions:
  - name: 张三
    email: zhangsan@example.com
    topic_id: optoelectronics
    keywords:
      - optical interconnect
""".strip(),
        encoding="utf-8",
    )

    config = load_lab_subscriptions(config_dir)

    assert list(config.topics) == ["optoelectronics"]
    assert config.topics["optoelectronics"].name == "光电子"
    assert config.subscriptions[0].email == "zhangsan@example.com"
    assert config.subscriptions[0].keywords == ["optical interconnect"]


def test_load_lab_subscriptions_rejects_unknown_topic_id(tmp_path: Path) -> None:
    config_dir = tmp_path
    (config_dir / "topics.yaml").write_text("topics: []", encoding="utf-8")
    (config_dir / "subscriptions.yaml").write_text(
        """
subscriptions:
  - name: 李四
    email: lisi@example.com
    topic_id: missing_topic
    keywords:
      - sram
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing_topic"):
        load_lab_subscriptions(config_dir)
