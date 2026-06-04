# Lab Shared Topic Subscriptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让系统按研究方向分池抓取公共论文，并按课题组成员的邮箱和个人关键词分别过滤、分别去重、分别发送邮件。

**Architecture:** 在现有单用户链路上增加两层配置：`topics.yaml` 描述方向池抓取与第一层匹配规则，`subscriptions.yaml` 描述成员邮箱与第二层个人关键词。主流程按 `topic_id` 分组运行 `pipeline`，再以 `topic_id + subscriber_email + paper_id` 为粒度做发送去重，保持抓取器、中文总结和邮件渲染尽量复用。

**Tech Stack:** Python 3.11、PyYAML、SQLite、pytest、dataclasses、现有 fetchers/matchers/SMTP/DeepSeek 客户端

---

## File Map

- Create: `config/topics.yaml`
- Create: `config/subscriptions.yaml`
- Modify: `src/paper_crawler/settings.py`
- Modify: `src/paper_crawler/main.py`
- Modify: `src/paper_crawler/storage/repositories.py`
- Modify: `src/paper_crawler/storage/database.py`
- Modify: `sql/schema.sql`
- Create: `src/paper_crawler/subscriptions.py`
- Create: `tests/test_subscriptions.py`
- Modify: `tests/test_settings.py`
- Modify: `tests/test_main.py`
- Modify: `tests/test_database.py`

### Task 1: 定义方向池与订阅人配置模型

**Files:**
- Create: `config/topics.yaml`
- Create: `config/subscriptions.yaml`
- Modify: `src/paper_crawler/settings.py`
- Create: `src/paper_crawler/subscriptions.py`
- Test: `tests/test_settings.py`
- Test: `tests/test_subscriptions.py`

- [ ] **Step 1: 先写配置读取测试，定义目标接口**

在 `tests/test_subscriptions.py` 新建以下测试：

```python
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
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_subscriptions.py -q`

Expected:

```text
E   ModuleNotFoundError: No module named 'paper_crawler.subscriptions'
```

- [ ] **Step 3: 写最小实现，新增配置模型与读取入口**

创建 `src/paper_crawler/subscriptions.py`：

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


def _read_yaml(file_path: Path) -> dict:
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
```

- [ ] **Step 4: 提供示例配置文件**

创建 `config/topics.yaml`：

```yaml
topics:
  - topic_id: optoelectronics
    name: 光电子
    arxiv_categories:
      - physics.optics
      - physics.app-ph
    openalex_filters:
      - photonics
    keyword_groups:
      silicon_photonics:
        - silicon photonics
      emitter_detector:
        - vcsel
        - photodetector
    synonyms:
      vcsel:
        - vertical-cavity surface-emitting laser
```

创建 `config/subscriptions.yaml`：

```yaml
subscriptions:
  - name: 示例成员
    email: member@example.com
    topic_id: optoelectronics
    keywords:
      - optical interconnect
      - silicon photonics
```

- [ ] **Step 5: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_subscriptions.py -q`

Expected:

```text
2 passed
```

- [ ] **Step 6: 提交本任务**

```bash
git add config/topics.yaml config/subscriptions.yaml src/paper_crawler/subscriptions.py tests/test_subscriptions.py
git commit -m "feat(config): add topic and subscription models"
```

### Task 2: 把 push_log 去重升级为方向池 + 订阅人粒度

**Files:**
- Modify: `sql/schema.sql`
- Modify: `src/paper_crawler/storage/database.py`
- Modify: `src/paper_crawler/storage/repositories.py`
- Test: `tests/test_database.py`

- [ ] **Step 1: 先写数据库迁移与去重测试**

在 `tests/test_database.py` 追加：

```python
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from paper_crawler.storage.database import initialize_database
from paper_crawler.storage.repositories import PushLogRepository


def test_initialize_database_adds_push_log_topic_and_subscriber_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE push_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT NOT NULL,
                pushed_at TEXT NOT NULL,
                channel TEXT NOT NULL
            )
            """
        )
        connection.commit()

    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(push_log)").fetchall()
        }

    assert "topic_id" in columns
    assert "subscriber_email" in columns


def test_push_log_repository_tracks_delivery_by_topic_and_subscriber(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        repository = PushLogRepository(connection)
        repository.mark_pushed(
            paper_id="paper-1",
            topic_id="optoelectronics",
            subscriber_email="zhangsan@example.com",
            pushed_at=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
            channel="email",
        )
        connection.commit()

        assert repository.has_been_pushed(
            paper_id="paper-1",
            topic_id="optoelectronics",
            subscriber_email="zhangsan@example.com",
        ) is True
        assert repository.has_been_pushed(
            paper_id="paper-1",
            topic_id="optoelectronics",
            subscriber_email="lisi@example.com",
        ) is False
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_database.py -q`

Expected:

```text
TypeError 或 sqlite3.OperationalError
```

- [ ] **Step 3: 修改 schema、迁移和仓储接口**

把 `sql/schema.sql` 中 `push_log` 调整为：

```sql
CREATE TABLE IF NOT EXISTS push_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL,
    topic_id TEXT NOT NULL DEFAULT '',
    subscriber_email TEXT NOT NULL DEFAULT '',
    pushed_at TEXT NOT NULL,
    channel TEXT NOT NULL
);
```

在 `src/paper_crawler/storage/repositories.py` 中把 `PushLogRepository` 改成：

```python
class PushLogRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def has_been_pushed(
        self,
        paper_id: str,
        topic_id: str,
        subscriber_email: str,
    ) -> bool:
        row = self._connection.execute(
            """
            SELECT 1
            FROM push_log
            WHERE paper_id = ?
              AND topic_id = ?
              AND subscriber_email = ?
            LIMIT 1
            """,
            (paper_id, topic_id, subscriber_email),
        ).fetchone()
        return row is not None

    def mark_pushed(
        self,
        paper_id: str,
        topic_id: str,
        subscriber_email: str,
        pushed_at: datetime,
        channel: str,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO push_log (
                paper_id,
                topic_id,
                subscriber_email,
                pushed_at,
                channel
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (paper_id, topic_id, subscriber_email, pushed_at.isoformat(), channel),
        )
```

- [ ] **Step 4: 在数据库初始化中加入轻量迁移**

在 `src/paper_crawler/storage/database.py` 中加入类似逻辑：

```python
def _ensure_push_log_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(push_log)").fetchall()
    }
    if "topic_id" not in columns:
        connection.execute(
            "ALTER TABLE push_log ADD COLUMN topic_id TEXT NOT NULL DEFAULT ''"
        )
    if "subscriber_email" not in columns:
        connection.execute(
            "ALTER TABLE push_log ADD COLUMN subscriber_email TEXT NOT NULL DEFAULT ''"
        )
```

并在初始化完成 schema 后调用它。

- [ ] **Step 5: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_database.py -q`

Expected:

```text
2 passed
```

- [ ] **Step 6: 提交本任务**

```bash
git add sql/schema.sql src/paper_crawler/storage/database.py src/paper_crawler/storage/repositories.py tests/test_database.py
git commit -m "feat(storage): scope push logs by topic and subscriber"
```

### Task 3: 让主流程支持按方向池运行并按订阅人过滤

**Files:**
- Modify: `src/paper_crawler/main.py`
- Modify: `src/paper_crawler/settings.py`
- Create: `tests/test_main.py`（在现有文件中追加测试）

- [ ] **Step 1: 先写主流程测试，钉住多人共享行为**

在 `tests/test_main.py` 追加：

```python
from paper_crawler.subscriptions import LabSubscriptions, SubscriptionConfig, TopicConfig


def test_run_application_sends_same_paper_to_different_subscribers(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)
    sender = DummySender()
    paper = build_record("paper-1", matched_keywords=["silicon photonics"])

    topic = TopicConfig(
        topic_id="optoelectronics",
        name="光电子",
        arxiv_categories=["physics.optics"],
        openalex_filters=["photonics"],
        keyword_groups={"silicon": ["silicon photonics"]},
        synonyms={},
    )
    subscriptions = LabSubscriptions(
        topics={"optoelectronics": topic},
        subscriptions=[
            SubscriptionConfig(
                name="张三",
                email="zhangsan@example.com",
                topic_id="optoelectronics",
                keywords=["silicon photonics"],
            ),
            SubscriptionConfig(
                name="李四",
                email="lisi@example.com",
                topic_id="optoelectronics",
                keywords=["silicon photonics"],
            ),
        ],
    )

    summary = run_application(
        tmp_path,
        settings_loader=lambda _: build_settings_for_main(db_path),
        pipeline_runner=lambda settings: build_pipeline_result(paper),
        email_sender=sender,
        subscriptions_loader=lambda _: subscriptions,
        smtp_password_getter=lambda: "secret",
        now_func=lambda: datetime(2026, 6, 4, 13, 0, tzinfo=UTC),
    )

    assert "email_sent=yes" in summary
    assert len(sender.calls) == 2
    assert {call[0].to_address for call in sender.calls} == {
        "zhangsan@example.com",
        "lisi@example.com",
    }


def test_run_application_skips_empty_subscriber_digest(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)
    sender = DummySender()
    paper = build_record("paper-1", matched_keywords=["silicon photonics"])

    topic = TopicConfig(
        topic_id="optoelectronics",
        name="光电子",
        arxiv_categories=["physics.optics"],
        openalex_filters=["photonics"],
        keyword_groups={"silicon": ["silicon photonics"]},
        synonyms={},
    )
    subscriptions = LabSubscriptions(
        topics={"optoelectronics": topic},
        subscriptions=[
            SubscriptionConfig(
                name="张三",
                email="zhangsan@example.com",
                topic_id="optoelectronics",
                keywords=["vcsel"],
            ),
        ],
    )

    summary = run_application(
        tmp_path,
        settings_loader=lambda _: build_settings_for_main(db_path),
        pipeline_runner=lambda settings: build_pipeline_result(paper),
        email_sender=sender,
        subscriptions_loader=lambda _: subscriptions,
        smtp_password_getter=lambda: "secret",
        now_func=lambda: datetime(2026, 6, 4, 13, 0, tzinfo=UTC),
    )

    assert "email_sent=no" in summary
    assert sender.calls == []
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_main.py -q`

Expected:

```text
TypeError: run_application() got an unexpected keyword argument 'subscriptions_loader'
```

- [ ] **Step 3: 在主流程中引入 subscriptions_loader 和订阅人循环**

把 `src/paper_crawler/main.py` 的主流程改造成以下骨架：

```python
def _record_matches_keywords(record: PaperRecord, keywords: list[str]) -> bool:
    haystack = " ".join(
        [
            record.title.lower(),
            record.abstract.lower(),
            " ".join(record.matched_keywords).lower(),
        ]
    )
    return any(keyword.lower() in haystack for keyword in keywords)


def run_application(
    config_dir: Path,
    settings_loader: Callable[[Path], Settings] = load_settings,
    pipeline_runner: Callable[[Settings], PipelineResult] = run_pipeline,
    email_renderer: Callable[[list], str] = render_email_summary,
    email_sender: Callable[[SMTPConfig, str, str], None] = send_email,
    summary_client_builder: Callable[[Settings], SummaryClient | None] = build_summary_client,
    subscriptions_loader: Callable[[Path], LabSubscriptions] = load_lab_subscriptions,
    smtp_password_getter: Callable[[], str | None] = lambda: os.getenv("SMTP_PASSWORD"),
    now_func: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    settings = settings_loader(config_dir)
    lab_subscriptions = subscriptions_loader(config_dir)
    db_path = resolve_sqlite_path(settings.database_url)
    initialize_database(db_path)

    fetched_count = 0
    matched_count = 0
    email_sent = "no"
    total_to_push = 0

    with connect_sqlite(db_path) as connection:
        paper_repository = PaperRepository(connection)
        push_log = PushLogRepository(connection)

        for topic_id, topic in lab_subscriptions.topics.items():
            topic_settings = replace(
                settings,
                arxiv_categories=topic.arxiv_categories,
                openalex_filters=topic.openalex_filters,
                keyword_groups=topic.keyword_groups,
                synonyms=topic.synonyms,
                issn_whitelist=topic.issn_whitelist or {},
            )
            result = pipeline_runner(topic_settings)
            fetched_count += result.fetched_count
            matched_count += result.matched_count

            topic_subscribers = [
                item
                for item in lab_subscriptions.subscriptions
                if item.topic_id == topic_id
            ]
            summary_client = summary_client_builder(settings) if result.matched_records else None

            for subscriber in topic_subscribers:
                subscriber_records = [
                    record
                    for record in result.matched_records
                    if _record_matches_keywords(record, subscriber.keywords)
                    and not push_log.has_been_pushed(
                        record.paper_id,
                        topic_id,
                        subscriber.email,
                    )
                ]
                if not subscriber_records:
                    continue

                if summary_client is not None:
                    for record in subscriber_records:
                        if record.zh_summary:
                            continue
                        zh_summary = summary_client.summarize_paper(
                            title=record.title,
                            abstract=record.abstract,
                            matched_keywords=record.matched_keywords,
                        )
                        record.zh_summary = zh_summary
                        paper_repository.update_zh_summary(record.paper_id, zh_summary)
                        connection.commit()

                body = email_renderer(subscriber_records)
                email_sender(
                    SMTPConfig(
                        host=settings.smtp.host,
                        port=settings.smtp.port,
                        username=settings.smtp.username,
                        password=smtp_password_getter() or "",
                        from_address=settings.smtp.from_address,
                        to_address=subscriber.email,
                        use_tls=settings.smtp.use_tls,
                    ),
                    f"Daily paper digest for {subscriber.name} - {topic.name} ({len(subscriber_records)})",
                    body,
                )
                pushed_at = now_func()
                for record in subscriber_records:
                    push_log.mark_pushed(
                        paper_id=record.paper_id,
                        topic_id=topic_id,
                        subscriber_email=subscriber.email,
                        pushed_at=pushed_at,
                        channel="email",
                    )
                connection.commit()
                total_to_push += len(subscriber_records)
                email_sent = "yes"

    return (
        f"Pipeline finished: fetched={fetched_count}, "
        f"matched={matched_count}, "
        f"to_push={total_to_push}, "
        f"email_sent={email_sent}"
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_main.py -q`

Expected:

```text
全部通过
```

- [ ] **Step 5: 提交本任务**

```bash
git add src/paper_crawler/main.py tests/test_main.py
git commit -m "feat(main): send digests by topic and subscriber"
```

### Task 4: 做配置与主链路回归，确保课题组版可交付

**Files:**
- Modify: `tests/test_settings.py`
- Modify: `tests/test_main.py`
- Modify: `tests/test_database.py`
- Test: `tests/test_settings.py`
- Test: `tests/test_main.py`
- Test: `tests/test_database.py`
- Test: `tests/test_subscriptions.py`

- [ ] **Step 1: 补 settings 兼容性测试，确保老配置仍可用**

在 `tests/test_settings.py` 增加：

```python
from pathlib import Path

from paper_crawler.settings import load_settings


def test_load_settings_remains_compatible_with_existing_config_files(tmp_path: Path) -> None:
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
    (tmp_path / "keywords.yaml").write_text("silicon:\n  - silicon photonics\n", encoding="utf-8")
    (tmp_path / "issn_whitelist.yaml").write_text("{}", encoding="utf-8")
    (tmp_path / "synonyms.yaml").write_text("{}", encoding="utf-8")

    settings = load_settings(tmp_path)

    assert settings.smtp.to_address == "receiver@example.com"
    assert settings.arxiv_categories == ["physics.optics"]
```

- [ ] **Step 2: 运行聚焦回归**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_settings.py tests/test_subscriptions.py tests/test_database.py tests/test_main.py -q`

Expected:

```text
全部通过
```

- [ ] **Step 3: 运行全量回归**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests -q`

Expected:

```text
全部通过
```

- [ ] **Step 4: 提交本任务**

```bash
git add tests/test_settings.py tests/test_subscriptions.py tests/test_database.py tests/test_main.py
git commit -m "test: cover lab shared topic subscriptions flow"
```

## Self-Review

- **Spec coverage:** Task 1 覆盖 `topics.yaml`、`subscriptions.yaml` 与订阅配置模型；Task 2 覆盖 `push_log` 迁移与按方向池/订阅人去重；Task 3 覆盖方向池运行与成员级发送；Task 4 覆盖兼容性和全链路回归。
- **Placeholder scan:** 无 `TODO`、`TBD` 或“后续实现”之类占位项；每一步都有明确代码、命令和预期结果。
- **Type consistency:** 统一使用 `TopicConfig`、`SubscriptionConfig`、`LabSubscriptions`、`topic_id`、`subscriber_email` 这些名称，与规格中的方向池/订阅人模型一致。
