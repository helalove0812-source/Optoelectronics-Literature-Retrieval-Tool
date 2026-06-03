# Output And Email Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为文献抓取系统补上结果导出与邮件推送能力，使主流程在完成抓取和筛选后，能够渲染本次命中的新论文摘要、通过 SMTP 发送，并记录 `push_log` 防止重复推送。

**Architecture:** `pipeline.py` 只返回结构化结果，不负责渲染或发送。`notify/email_renderer.py` 负责正文生成，`notify/smtp_sender.py` 负责 SMTP 发送，`main.py` 负责编排“过滤已推送论文 -> 渲染 -> 发送 -> 写 push_log -> 输出摘要”，并保持发送失败不影响已完成入库。

**Tech Stack:** Python 3.11、pytest、sqlite3、smtplib、email.message、dataclasses

---

## File Map

- Create: `tests/test_email_renderer.py`
- Create: `tests/test_smtp_sender.py`
- Modify: `src/paper_crawler/notify/email_renderer.py`
- Modify: `src/paper_crawler/notify/smtp_sender.py`
- Modify: `src/paper_crawler/processing/pipeline.py`
- Modify: `src/paper_crawler/main.py`
- Modify: `src/paper_crawler/settings.py`
- Modify: `src/paper_crawler/storage/repositories.py`
- Modify: `tests/test_pipeline.py`
- Create: `tests/test_main.py`
- Modify: `tests/test_settings.py`
- Modify: `config/config.yaml`

### Task 1: 完成邮件正文渲染器

**Files:**
- Create: `tests/test_email_renderer.py`
- Modify: `src/paper_crawler/notify/email_renderer.py`

- [ ] **Step 1: 写失败测试，验证单篇论文渲染**

```python
from datetime import UTC, datetime

from paper_crawler.models import PaperRecord
from paper_crawler.notify.email_renderer import render_email_summary


def test_render_email_summary_renders_single_record() -> None:
    record = PaperRecord(
        paper_id="paper-1",
        title="Silicon photonics coherent transceiver",
        authors=["Alice Smith", "Bob Chen"],
        abstract="A compact coherent transceiver for datacenter optics.",
        doi="10.1000/example",
        source="crossref",
        published_at=datetime(2026, 6, 3, 10, 0, tzinfo=UTC),
        landing_url="https://doi.org/10.1000/example",
        pdf_url="https://example.com/paper.pdf",
        access="open",
        matched_keywords=["硅光"],
    )

    body = render_email_summary([record])

    assert "# 今日光电子相关论文摘要" in body
    assert "共 1 篇新论文" in body
    assert "Silicon photonics coherent transceiver" in body
    assert "Alice Smith, Bob Chen" in body
    assert "Matched Keywords: 硅光" in body
    assert "PDF URL: https://example.com/paper.pdf" in body
```

- [ ] **Step 2: 写第二个失败测试，验证订阅论文渲染**

```python
from datetime import UTC, datetime

from paper_crawler.models import PaperRecord
from paper_crawler.notify.email_renderer import render_email_summary


def test_render_email_summary_renders_subscription_marker() -> None:
    record = PaperRecord(
        paper_id="paper-2",
        title="Battery chemistry advances",
        authors=["Carol Zhang"],
        abstract="Electrochemistry only.",
        doi=None,
        source="openalex",
        published_at=datetime(2026, 6, 3, 11, 0, tzinfo=UTC),
        landing_url="https://openalex.org/W123",
        pdf_url=None,
        access="subscription",
        matched_keywords=["其他"],
    )

    body = render_email_summary([record])

    assert "Access: subscription" in body
    assert "PDF URL: 需订阅" in body
```

- [ ] **Step 3: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_email_renderer.py -q`

Expected:

```text
2 failed
```

- [ ] **Step 4: 写最小实现**

`src/paper_crawler/notify/email_renderer.py`

```python
from __future__ import annotations

from paper_crawler.models import PaperRecord


def render_email_summary(records: list[PaperRecord]) -> str:
    lines = [
        "# 今日光电子相关论文摘要",
        "",
        f"共 {len(records)} 篇新论文。",
        "",
    ]

    for index, record in enumerate(records, start=1):
        lines.extend(
            [
                f"## {index}. {record.title}",
                f"Authors: {', '.join(record.authors)}",
                f"Source: {record.source}",
                f"Published At: {record.published_at.isoformat()}",
                f"DOI: {record.doi or 'N/A'}",
                f"Matched Keywords: {', '.join(record.matched_keywords) or 'N/A'}",
                f"Access: {record.access}",
                f"Landing URL: {record.landing_url}",
                f"PDF URL: {record.pdf_url or '需订阅'}",
                f"Abstract: {record.abstract or 'N/A'}",
                "",
            ]
        )

    return "\n".join(lines).strip()
```

- [ ] **Step 5: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_email_renderer.py -q`

Expected:

```text
2 passed
```

- [ ] **Step 6: 提交本任务**

```bash
git add tests/test_email_renderer.py src/paper_crawler/notify/email_renderer.py
git commit -m "feat: add email summary renderer"
```

### Task 2: 完成 SMTP 发送器

**Files:**
- Create: `tests/test_smtp_sender.py`
- Modify: `src/paper_crawler/notify/smtp_sender.py`
- Modify: `src/paper_crawler/settings.py`
- Modify: `tests/test_settings.py`
- Modify: `config/config.yaml`

- [ ] **Step 1: 写失败测试，验证 SMTP 发送调用**

```python
from paper_crawler.notify.smtp_sender import SMTPConfig, send_email


class DummySMTP:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.started_tls = False
        self.logged_in = None
        self.sent_messages = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.logged_in = (username, password)

    def send_message(self, message) -> None:
        self.sent_messages.append(message)


def test_send_email_uses_smtp_config_and_sends_message() -> None:
    dummy_smtp = DummySMTP("smtp.example.com", 587)
    config = SMTPConfig(
        host="smtp.example.com",
        port=587,
        username="research-alert@example.com",
        password="secret",
        from_address="research-alert@example.com",
        to_address="user@example.com",
        use_tls=True,
    )

    send_email(
        config=config,
        subject="Daily paper digest",
        body="Matched papers: 1",
        smtp_factory=lambda host, port: dummy_smtp,
    )

    assert dummy_smtp.started_tls is True
    assert dummy_smtp.logged_in == ("research-alert@example.com", "secret")
    assert len(dummy_smtp.sent_messages) == 1
    assert dummy_smtp.sent_messages[0]["To"] == "user@example.com"
    assert dummy_smtp.sent_messages[0]["Subject"] == "Daily paper digest"
```

- [ ] **Step 2: 写配置加载失败测试**

```python
from pathlib import Path

from paper_crawler.settings import load_settings


def test_load_settings_reads_smtp_delivery_fields() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root / "config")

    assert settings.smtp.host == "smtp.example.com"
    assert settings.smtp.to_address == "user@example.com"
    assert settings.smtp.use_tls is True
```

- [ ] **Step 3: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_smtp_sender.py tests/test_settings.py -q`

Expected:

```text
2 failed
```

- [ ] **Step 4: 写最小实现**

`config/config.yaml`

```yaml
smtp:
  host: smtp.example.com
  port: 587
  username: research-alert@example.com
  from_address: research-alert@example.com
  to_address: user@example.com
  use_tls: true
```

`src/paper_crawler/settings.py`

```python
from dataclasses import dataclass


@dataclass
class SMTPSettings:
    host: str
    port: int
    username: str
    from_address: str
    to_address: str
    use_tls: bool


@dataclass
class Settings:
    ...
    smtp: SMTPSettings


def load_settings(config_dir: Path) -> Settings:
    ...
    smtp = config["smtp"]
    return Settings(
        ...
        smtp=SMTPSettings(
            host=smtp["host"],
            port=int(smtp["port"]),
            username=smtp["username"],
            from_address=smtp["from_address"],
            to_address=smtp["to_address"],
            use_tls=bool(smtp.get("use_tls", True)),
        ),
    )
```

`src/paper_crawler/notify/smtp_sender.py`

```python
from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Callable


@dataclass(slots=True)
class SMTPConfig:
    host: str
    port: int
    username: str
    password: str
    from_address: str
    to_address: str
    use_tls: bool = True


def send_email(
    config: SMTPConfig,
    subject: str,
    body: str,
    smtp_factory: Callable[[str, int], object] = smtplib.SMTP,
) -> None:
    message = EmailMessage()
    message["From"] = config.from_address
    message["To"] = config.to_address
    message["Subject"] = subject
    message.set_content(body)

    with smtp_factory(config.host, config.port) as smtp:
        if config.use_tls:
            smtp.starttls()
        smtp.login(config.username, config.password)
        smtp.send_message(message)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_smtp_sender.py tests/test_settings.py -q`

Expected:

```text
3 passed
```

- [ ] **Step 6: 提交本任务**

```bash
git add config/config.yaml src/paper_crawler/settings.py src/paper_crawler/notify/smtp_sender.py tests/test_smtp_sender.py tests/test_settings.py
git commit -m "feat: add smtp email sender"
```

### Task 3: 扩展 Pipeline 返回命中记录

**Files:**
- Modify: `src/paper_crawler/processing/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: 写失败测试，验证 PipelineResult 返回 matched_records**

```python
from paper_crawler.fetchers.base import FetchResult
from paper_crawler.processing.pipeline import run_pipeline


def test_run_pipeline_returns_matched_records(tmp_path: Path) -> None:
    settings = build_settings()
    settings.database_url = f"sqlite:///{tmp_path / 'papers.db'}"

    matched_record = build_record()
    matched_record.paper_id = "paper-match"
    matched_record.title = "Silicon photonics coherent link packaging"
    matched_record.abstract = "Photonics integration for datacenter optics."

    unmatched_record = build_record()
    unmatched_record.paper_id = "paper-unmatched"
    unmatched_record.title = "Battery chemistry advances"
    unmatched_record.abstract = "Electrochemistry only."

    result = run_pipeline(
        settings,
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(
            FetchResult(source="arxiv", records=[matched_record, unmatched_record])
        ),
        crossref_fetcher_factory=lambda _: DummyCrossrefFetcher(FetchResult(source="crossref")),
        openalex_fetcher_factory=lambda _: DummyOpenAlexFetcher(FetchResult(source="openalex")),
        unpaywall_client_factory=lambda _: DummyUnpaywallClient({"is_oa": False, "pdf_url": None, "landing_url": None}),
    )

    assert [record.paper_id for record in result.matched_records] == ["paper-match"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline.py::test_run_pipeline_returns_matched_records -q`

Expected:

```text
1 failed
```

- [ ] **Step 3: 写最小实现**

`src/paper_crawler/processing/pipeline.py`

```python
@dataclass(slots=True)
class PipelineResult:
    fetched_count: int
    matched_count: int
    matched_records: list[PaperRecord]
...
    if not records:
        return PipelineResult(fetched_count=0, matched_count=0, matched_records=[])
...
    matched_records = [record for record in records if record.matched_keywords]
...
    return PipelineResult(
        fetched_count=fetched_count,
        matched_count=matched_count,
        matched_records=matched_records,
    )
```

- [ ] **Step 4: 运行定向测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline.py::test_run_pipeline_returns_matched_records -q`

Expected:

```text
1 passed
```

- [ ] **Step 5: 提交本任务**

```bash
git add src/paper_crawler/processing/pipeline.py tests/test_pipeline.py
git commit -m "feat: expose matched records from pipeline"
```

### Task 4: 编排导出、发送与 push_log 去重

**Files:**
- Modify: `src/paper_crawler/main.py`
- Modify: `src/paper_crawler/storage/repositories.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: 写失败测试，验证只发送未推送的命中论文**

```python
from datetime import UTC, datetime
from pathlib import Path

from paper_crawler.models import PaperRecord
from paper_crawler.processing.pipeline import PipelineResult
from paper_crawler.main import run_application


class DummySender:
    def __init__(self):
        self.calls = []

    def __call__(self, config, subject, body):
        self.calls.append((config, subject, body))


def build_pipeline_result() -> PipelineResult:
    return PipelineResult(
        fetched_count=3,
        matched_count=2,
        matched_records=[
            PaperRecord(
                paper_id="paper-1",
                title="Silicon photonics coherent transceiver",
                authors=["Alice Smith"],
                abstract="A compact coherent transceiver.",
                doi="10.1000/example",
                source="crossref",
                published_at=datetime(2026, 6, 3, 10, 0, tzinfo=UTC),
                landing_url="https://doi.org/10.1000/example",
                pdf_url="https://example.com/paper.pdf",
                access="open",
                matched_keywords=["硅光"],
            ),
            PaperRecord(
                paper_id="paper-2",
                title="Metasurface packaging",
                authors=["Bob Chen"],
                abstract="A metasurface packaging method.",
                doi="10.1000/example2",
                source="openalex",
                published_at=datetime(2026, 6, 3, 11, 0, tzinfo=UTC),
                landing_url="https://doi.org/10.1000/example2",
                pdf_url=None,
                access="subscription",
                matched_keywords=["超表面"],
            ),
        ],
    )


def test_run_application_sends_only_unpushed_records(tmp_path: Path) -> None:
    sender = DummySender()
    summary = run_application(
        tmp_path,
        pipeline_runner=lambda settings: build_pipeline_result(),
        email_renderer=lambda records: f"Matched papers: {len(records)}",
        email_sender=sender,
        smtp_password_getter=lambda: "secret",
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    assert "to_push=2" in summary
    assert "email_sent=yes" in summary
    assert len(sender.calls) == 1
```

- [ ] **Step 2: 写第二个失败测试，验证重复推送过滤**

```python
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from paper_crawler.main import run_application
from paper_crawler.processing.pipeline import PipelineResult
from paper_crawler.storage.database import initialize_database


def test_run_application_skips_already_pushed_records(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO push_log (paper_id, pushed_at, channel) VALUES (?, ?, ?)",
            ("paper-1", datetime(2026, 6, 3, 8, 0, tzinfo=UTC).isoformat(), "email"),
        )
        connection.commit()

    sender_calls = []
    summary = run_application(
        tmp_path,
        settings_loader=lambda _: build_settings_for_main(db_path),
        pipeline_runner=lambda settings: build_pipeline_result(),
        email_renderer=lambda records: f"Matched papers: {len(records)}",
        email_sender=lambda config, subject, body: sender_calls.append((subject, body)),
        smtp_password_getter=lambda: "secret",
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    assert "to_push=1" in summary
    assert len(sender_calls) == 1
```

- [ ] **Step 3: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_main.py -q`

Expected:

```text
2 failed
```

- [ ] **Step 4: 写最小实现**

`src/paper_crawler/main.py`

```python
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from paper_crawler.notify.email_renderer import render_email_summary
from paper_crawler.notify.smtp_sender import SMTPConfig, send_email
from paper_crawler.processing import run_pipeline
from paper_crawler.settings import Settings, load_settings
from paper_crawler.storage import PushLogRepository, connect_sqlite, resolve_sqlite_path


def run_application(
    config_dir: Path,
    settings_loader: Callable[[Path], Settings] = load_settings,
    pipeline_runner: Callable[[Settings], object] = run_pipeline,
    email_renderer: Callable[[list], str] = render_email_summary,
    email_sender: Callable[[SMTPConfig, str, str], None] = send_email,
    smtp_password_getter: Callable[[], str | None] = lambda: os.getenv("SMTP_PASSWORD"),
    now_func: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    settings = settings_loader(config_dir)
    result = pipeline_runner(settings)
    db_path = resolve_sqlite_path(settings.database_url)

    with connect_sqlite(db_path) as connection:
        push_log = PushLogRepository(connection)
        to_push = [
            record for record in result.matched_records
            if not push_log.has_been_pushed(record.paper_id)
        ]

        email_sent = "no"
        if to_push:
            config = SMTPConfig(
                host=settings.smtp.host,
                port=settings.smtp.port,
                username=settings.smtp.username,
                password=smtp_password_getter() or "",
                from_address=settings.smtp.from_address,
                to_address=settings.smtp.to_address,
                use_tls=settings.smtp.use_tls,
            )
            body = email_renderer(to_push)
            subject = f"Daily paper digest ({len(to_push)})"
            email_sender(config, subject, body)
            for record in to_push:
                push_log.mark_pushed(record.paper_id, pushed_at=now_func(), channel="email")
            connection.commit()
            email_sent = "yes"

    return (
        f"Pipeline finished: fetched={result.fetched_count}, "
        f"matched={result.matched_count}, "
        f"to_push={len(to_push)}, "
        f"email_sent={email_sent}"
    )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_main.py -q`

Expected:

```text
2 passed
```

- [ ] **Step 6: 运行回归测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_email_renderer.py tests/test_smtp_sender.py tests/test_main.py tests/test_pipeline.py tests/test_settings.py -q`

Expected:

```text
18 passed
```

- [ ] **Step 7: 运行全量测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests -q`

Expected:

```text
36 passed
```

- [ ] **Step 8: 提交本任务**

```bash
git add src/paper_crawler/main.py src/paper_crawler/storage/repositories.py tests/test_main.py
git commit -m "feat: deliver matched papers by email"
```

## Self-Review

- 规格覆盖：任务 1 覆盖摘要渲染，任务 2 覆盖 SMTP 配置和发送，任务 3 覆盖 `matched_records` 返回，任务 4 覆盖去重推送、`push_log` 写入和 CLI 摘要输出。
- 占位检查：无 `TODO`、`TBD`、"后续完善" 等空泛描述，每个步骤都提供了代码和命令。
- 一致性检查：统一使用 `matched_records`、`SMTPSettings`、`SMTPConfig`、`render_email_summary()`、`send_email()`、`PushLogRepository.mark_pushed()` 这些名称，与当前代码结构兼容。
