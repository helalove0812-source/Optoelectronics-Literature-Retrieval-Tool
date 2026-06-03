# DeepSeek Zh Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为最终待邮件推送的命中文献生成 2-3 句中文总结，将其持久化到数据库，并在邮件中优先展示，且在模型失败时回退为英文摘要。

**Architecture:** 在现有抓取与入库主链路不变的前提下，给 `PaperRecord`、SQLite schema 和仓储层补上 `zh_summary` 字段与更新能力。`llm/deepseek_client.py` 负责 OpenAI 兼容接口调用，`main.py` 负责“筛选待推送论文 -> 生成并落库中文总结 -> 渲染邮件 -> 发送并写 push_log”的编排，并确保单篇总结失败不影响整体发送、邮件发送失败也不回滚已落库的总结。

**Tech Stack:** Python 3.11、pytest、sqlite3、requests、dataclasses、SMTP、YAML

---

## File Map

- Create: `src/paper_crawler/llm/__init__.py`
- Create: `src/paper_crawler/llm/deepseek_client.py`
- Create: `tests/test_deepseek_client.py`
- Modify: `config/config.yaml`
- Modify: `sql/schema.sql`
- Modify: `src/paper_crawler/main.py`
- Modify: `src/paper_crawler/models.py`
- Modify: `src/paper_crawler/notify/email_renderer.py`
- Modify: `src/paper_crawler/settings.py`
- Modify: `src/paper_crawler/storage/database.py`
- Modify: `src/paper_crawler/storage/repositories.py`
- Modify: `tests/test_database.py`
- Modify: `tests/test_email_renderer.py`
- Modify: `tests/test_main.py`
- Modify: `tests/test_pipeline.py`
- Modify: `tests/test_settings.py`

### Task 1: 扩展数据模型、SQLite schema 和仓储层

**Files:**
- Modify: `src/paper_crawler/models.py`
- Modify: `sql/schema.sql`
- Modify: `src/paper_crawler/storage/database.py`
- Modify: `src/paper_crawler/storage/repositories.py`
- Modify: `tests/test_database.py`

- [ ] **Step 1: 写失败测试，验证 `zh_summary` 能写入和更新**

在 `tests/test_database.py` 末尾追加：

```python
def test_paper_repository_persists_and_updates_zh_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)

    record = PaperRecord(
        paper_id="10.1000/summary",
        title="Silicon Photonics for Coherent Links",
        authors=["Alice Smith", "Bob Chen"],
        abstract="A paper about coherent links.",
        doi="10.1000/summary",
        source="crossref",
        published_at=datetime(2026, 6, 3, tzinfo=UTC),
        landing_url="https://doi.org/10.1000/summary",
        pdf_url=None,
        access="subscription",
        matched_keywords=["silicon photonics"],
        semantic_score=0.72,
        zh_summary="这篇论文研究了相干链路中的硅光器件集成。",
    )

    with connect_sqlite(db_path) as connection:
        repository = PaperRepository(connection)
        assert repository.insert_or_ignore(record) is True
        repository.update_zh_summary(
            record.paper_id,
            "论文提出了面向数据中心互连的紧凑型硅光实现方案。",
        )
        connection.commit()

        stored = connection.execute(
            "SELECT zh_summary FROM papers WHERE paper_id = ?",
            (record.paper_id,),
        ).fetchone()

    assert stored == ("论文提出了面向数据中心互连的紧凑型硅光实现方案。",)
```

- [ ] **Step 2: 写失败测试，验证旧库会被轻量迁移**

继续在 `tests/test_database.py` 末尾追加：

```python
def test_initialize_database_adds_zh_summary_column_to_existing_papers_table(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy.db"

    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE papers (
                paper_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                authors_json TEXT NOT NULL,
                abstract TEXT NOT NULL,
                doi TEXT,
                source TEXT NOT NULL,
                published_at TEXT NOT NULL,
                landing_url TEXT NOT NULL,
                pdf_url TEXT,
                access TEXT NOT NULL,
                matched_keywords_json TEXT NOT NULL,
                semantic_score REAL
            );
            """
        )

    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(papers)")
        }

    assert "zh_summary" in columns
```

- [ ] **Step 3: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_database.py -q`

Expected:

```text
...FF
2 failed, 3 passed
```

- [ ] **Step 4: 写最小实现**

把 `src/paper_crawler/models.py` 改成：

```python
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class PaperRecord:
    paper_id: str
    title: str
    authors: list[str]
    abstract: str
    doi: str | None
    source: str
    published_at: datetime
    landing_url: str
    pdf_url: str | None = None
    access: str = "subscription"
    matched_keywords: list[str] = field(default_factory=list)
    semantic_score: float | None = None
    zh_summary: str | None = None
```

把 `sql/schema.sql` 中 `papers` 表改成：

```sql
CREATE TABLE IF NOT EXISTS papers (
    paper_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors_json TEXT NOT NULL,
    abstract TEXT NOT NULL,
    doi TEXT,
    source TEXT NOT NULL,
    published_at TEXT NOT NULL,
    landing_url TEXT NOT NULL,
    pdf_url TEXT,
    access TEXT NOT NULL,
    matched_keywords_json TEXT NOT NULL,
    semantic_score REAL,
    zh_summary TEXT
);

CREATE TABLE IF NOT EXISTS push_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL,
    pushed_at TEXT NOT NULL,
    channel TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    fetched_count INTEGER NOT NULL DEFAULT 0,
    matched_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL
);
```

把 `src/paper_crawler/storage/database.py` 改成：

```python
import sqlite3
from pathlib import Path


def get_schema_path() -> Path:
    return Path(__file__).resolve().parents[3] / "sql" / "schema.sql"


def resolve_sqlite_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(f"Unsupported database URL: {database_url}")
    return Path(database_url.removeprefix(prefix))


def connect_sqlite(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def _has_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def _run_lightweight_migrations(connection: sqlite3.Connection) -> None:
    if not _has_column(connection, "papers", "zh_summary"):
        connection.execute("ALTER TABLE papers ADD COLUMN zh_summary TEXT")


def initialize_database(db_path: Path) -> None:
    schema = get_schema_path().read_text(encoding="utf-8")

    with connect_sqlite(db_path) as connection:
        connection.executescript(schema)
        _run_lightweight_migrations(connection)
```

把 `src/paper_crawler/storage/repositories.py` 改成：

```python
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from paper_crawler.models import PaperRecord


@dataclass(slots=True)
class RunSummary:
    fetched_count: int = 0
    matched_count: int = 0
    status: str = "success"


class PaperRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert_or_ignore(self, record: PaperRecord) -> bool:
        cursor = self._connection.execute(
            """
            INSERT OR IGNORE INTO papers (
                paper_id,
                title,
                authors_json,
                abstract,
                doi,
                source,
                published_at,
                landing_url,
                pdf_url,
                access,
                matched_keywords_json,
                semantic_score,
                zh_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.paper_id,
                record.title,
                json.dumps(record.authors, ensure_ascii=False),
                record.abstract,
                record.doi,
                record.source,
                record.published_at.isoformat(),
                record.landing_url,
                record.pdf_url,
                record.access,
                json.dumps(record.matched_keywords, ensure_ascii=False),
                record.semantic_score,
                record.zh_summary,
            ),
        )
        return cursor.rowcount == 1

    def update_zh_summary(self, paper_id: str, zh_summary: str) -> None:
        self._connection.execute(
            "UPDATE papers SET zh_summary = ? WHERE paper_id = ?",
            (zh_summary, paper_id),
        )


class PushLogRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def has_been_pushed(self, paper_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM push_log WHERE paper_id = ? LIMIT 1",
            (paper_id,),
        ).fetchone()
        return row is not None

    def mark_pushed(
        self,
        paper_id: str,
        pushed_at: datetime,
        channel: str,
    ) -> None:
        self._connection.execute(
            "INSERT INTO push_log (paper_id, pushed_at, channel) VALUES (?, ?, ?)",
            (paper_id, pushed_at.isoformat(), channel),
        )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_database.py -q`

Expected:

```text
5 passed
```

- [ ] **Step 6: 提交本任务**

```bash
git add src/paper_crawler/models.py sql/schema.sql src/paper_crawler/storage/database.py src/paper_crawler/storage/repositories.py tests/test_database.py
git commit -m "feat(storage): persist zh summaries"
```

### Task 2: 增加 LLM 配置并实现 DeepSeek 客户端

**Files:**
- Create: `src/paper_crawler/llm/__init__.py`
- Create: `src/paper_crawler/llm/deepseek_client.py`
- Create: `tests/test_deepseek_client.py`
- Modify: `config/config.yaml`
- Modify: `src/paper_crawler/settings.py`
- Modify: `tests/test_settings.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: 写失败测试，验证设置文件能读取 LLM 配置**

在 `tests/test_settings.py` 末尾追加：

```python
def test_load_settings_reads_llm_fields() -> None:
    root = Path(__file__).resolve().parents[1]

    settings = load_settings(root / "config")

    assert settings.llm.enabled is False
    assert settings.llm.provider == "deepseek"
    assert settings.llm.base_url == "https://api.deepseek.com"
    assert settings.llm.model == "deepseek-chat"
    assert settings.llm.timeout_seconds == 30
```

- [ ] **Step 2: 写失败测试，验证 DeepSeek 成功返回总结**

创建 `tests/test_deepseek_client.py`：

```python
from paper_crawler.llm.deepseek_client import DeepSeekClient, DeepSeekConfig


class DummyResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def test_deepseek_client_returns_summary_and_sends_openai_payload() -> None:
    captured: dict[str, object] = {}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: int,
    ) -> DummyResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return DummyResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "这篇论文面向相干互连场景，提出了紧凑型硅光收发方案。研究重点放在器件集成与链路实现上。"
                        }
                    }
                ]
            }
        )

    client = DeepSeekClient(
        DeepSeekConfig(
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            api_key="secret",
            timeout_seconds=30,
        ),
        http_post=fake_post,
    )

    summary = client.summarize_paper(
        title="Silicon photonics coherent transceiver",
        abstract="A compact coherent transceiver for datacenter optics.",
        matched_keywords=["硅光", "相干光通信"],
    )

    assert "紧凑型硅光收发方案" in summary
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"] == {
        "Authorization": "Bearer secret",
        "Content-Type": "application/json",
    }
    assert captured["timeout"] == 30
    assert captured["json"]["model"] == "deepseek-chat"
```

- [ ] **Step 3: 写失败测试，验证空内容会被判定为失败**

继续在 `tests/test_deepseek_client.py` 末尾追加：

```python
import pytest

from paper_crawler.llm.deepseek_client import DeepSeekClient, DeepSeekConfig


class EmptyResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"choices": [{"message": {"content": "   "}}]}


def test_deepseek_client_rejects_empty_summary() -> None:
    client = DeepSeekClient(
        DeepSeekConfig(
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            api_key="secret",
            timeout_seconds=30,
        ),
        http_post=lambda url, **kwargs: EmptyResponse(),
    )

    with pytest.raises(ValueError, match="empty summary"):
        client.summarize_paper(
            title="Silicon photonics coherent transceiver",
            abstract="A compact coherent transceiver for datacenter optics.",
            matched_keywords=["硅光"],
        )
```

- [ ] **Step 4: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_settings.py tests/test_deepseek_client.py -q`

Expected:

```text
FFF
3 failed
```

- [ ] **Step 5: 写最小实现**

在 `config/config.yaml` 追加：

```yaml
llm:
  enabled: false
  provider: deepseek
  base_url: https://api.deepseek.com
  model: deepseek-chat
  timeout_seconds: 30
```

把 `src/paper_crawler/settings.py` 改成：

```python
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
```

创建 `src/paper_crawler/llm/__init__.py`：

```python
from paper_crawler.llm.deepseek_client import DeepSeekClient, DeepSeekConfig

__all__ = ["DeepSeekClient", "DeepSeekConfig"]
```

创建 `src/paper_crawler/llm/deepseek_client.py`：

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import requests


@dataclass(slots=True)
class DeepSeekConfig:
    base_url: str
    model: str
    api_key: str
    timeout_seconds: int = 30


class DeepSeekClient:
    def __init__(
        self,
        config: DeepSeekConfig,
        http_post: Callable[..., object] = requests.post,
    ) -> None:
        self._config = config
        self._http_post = http_post

    def summarize_paper(
        self,
        *,
        title: str,
        abstract: str,
        matched_keywords: list[str],
    ) -> str:
        response = self._http_post(
            f"{self._config.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._config.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是科研论文助手。请使用简体中文输出 2-3 句总结，"
                            "只概括研究对象、方法或结果，不要编号，不要杜撰。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"标题：{title}\n"
                            f"摘要：{abstract}\n"
                            f"命中关键词：{', '.join(matched_keywords) or 'N/A'}"
                        ),
                    },
                ],
                "temperature": 0.2,
            },
            timeout=self._config.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        if not content:
            raise ValueError("DeepSeek returned empty summary")
        return content
```

把 `tests/test_pipeline.py` 里的 `build_settings()` 改成：

```python
from paper_crawler.settings import LLMSettings, SMTPSettings, Settings


def build_settings() -> Settings:
    return Settings(
        contact_email="team@example.com",
        database_url="sqlite:///data/papers.db",
        smtp=SMTPSettings(
            host="smtp.example.com",
            port=587,
            username="research-alert@example.com",
            from_address="research-alert@example.com",
            to_address="user@example.com",
            use_tls=True,
        ),
        llm=LLMSettings(
            enabled=False,
            provider="deepseek",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            timeout_seconds=30,
        ),
        arxiv_categories=["physics.optics"],
        openalex_filters=["concepts.id:C123"],
        keyword_groups={"硅光": ["silicon photonics"]},
        issn_whitelist={},
        synonyms={},
        semantic_threshold=0.5,
        enable_semantic_matching=True,
        lookback_hours=24,
    )
```

- [ ] **Step 6: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_settings.py tests/test_deepseek_client.py tests/test_pipeline.py -q`

Expected:

```text
19 passed
```

- [ ] **Step 7: 提交本任务**

```bash
git add config/config.yaml src/paper_crawler/settings.py src/paper_crawler/llm/__init__.py src/paper_crawler/llm/deepseek_client.py tests/test_settings.py tests/test_deepseek_client.py tests/test_pipeline.py
git commit -m "feat(llm): add deepseek summary client"
```

### Task 3: 让邮件渲染器优先展示中文总结

**Files:**
- Modify: `src/paper_crawler/notify/email_renderer.py`
- Modify: `tests/test_email_renderer.py`

- [ ] **Step 1: 写失败测试，验证 `zh_summary` 优先于英文摘要**

在 `tests/test_email_renderer.py` 末尾追加：

```python
def test_render_email_summary_prefers_zh_summary_when_present() -> None:
    record = PaperRecord(
        paper_id="paper-zh",
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
        zh_summary="这篇论文提出了面向数据中心互连的硅光相干收发方案。",
    )

    body = render_email_summary([record])

    assert "中文总结: 这篇论文提出了面向数据中心互连的硅光相干收发方案。" in body
    assert "Abstract: A compact coherent transceiver for datacenter optics." not in body
```

- [ ] **Step 2: 写失败测试，验证缺少 `zh_summary` 时回退为英文摘要**

继续在 `tests/test_email_renderer.py` 末尾追加：

```python
def test_render_email_summary_falls_back_to_abstract_when_zh_summary_missing() -> None:
    record = PaperRecord(
        paper_id="paper-fallback",
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
        zh_summary=None,
    )

    body = render_email_summary([record])

    assert "Abstract: A metasurface packaging method." in body
    assert "中文总结:" not in body
```

- [ ] **Step 3: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_email_renderer.py -q`

Expected:

```text
..FF
2 failed, 2 passed
```

- [ ] **Step 4: 写最小实现**

把 `src/paper_crawler/notify/email_renderer.py` 改成：

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
        summary_line = (
            f"中文总结: {record.zh_summary}"
            if record.zh_summary
            else f"Abstract: {record.abstract or 'N/A'}"
        )
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
                summary_line,
                "",
            ]
        )

    return "\n".join(lines).strip()
```

- [ ] **Step 5: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_email_renderer.py -q`

Expected:

```text
4 passed
```

- [ ] **Step 6: 提交本任务**

```bash
git add src/paper_crawler/notify/email_renderer.py tests/test_email_renderer.py
git commit -m "feat(notify): render zh summaries in email"
```

### Task 4: 在主流程中编排总结生成、回退和持久化

**Files:**
- Modify: `src/paper_crawler/main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: 写失败测试，验证只对待推送且缺少 `zh_summary` 的论文调用 DeepSeek**

在 `tests/test_main.py` 中补充导入：

```python
from paper_crawler.settings import LLMSettings, SMTPSettings, Settings
```

把 `build_settings_for_main()` 改成：

```python
def build_settings_for_main(db_path: Path) -> Settings:
    return Settings(
        contact_email="team@example.com",
        database_url=f"sqlite:///{db_path}",
        smtp=SMTPSettings(
            host="smtp.example.com",
            port=587,
            username="research-alert@example.com",
            from_address="research-alert@example.com",
            to_address="user@example.com",
            use_tls=True,
        ),
        llm=LLMSettings(
            enabled=True,
            provider="deepseek",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            timeout_seconds=30,
        ),
        arxiv_categories=["physics.optics"],
        openalex_filters=["concepts.id:C123"],
        lookback_hours=24,
        keyword_groups={"硅光": ["silicon photonics"]},
        issn_whitelist={},
        synonyms={},
        semantic_threshold=0.5,
        enable_semantic_matching=True,
    )
```

在 `tests/test_main.py` 中追加：

```python
class DummySummaryClient:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, list[str]]] = []

    def summarize_paper(
        self,
        *,
        title: str,
        abstract: str,
        matched_keywords: list[str],
    ) -> str:
        self.calls.append((title, abstract, matched_keywords))
        return self.responses[title]


def seed_records(db_path: Path, records: list[PaperRecord]) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO papers (
                paper_id,
                title,
                authors_json,
                abstract,
                doi,
                source,
                published_at,
                landing_url,
                pdf_url,
                access,
                matched_keywords_json,
                semantic_score,
                zh_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.paper_id,
                    record.title,
                    '["Alice Smith"]' if record.paper_id == "paper-1" else '["Bob Chen"]',
                    record.abstract,
                    record.doi,
                    record.source,
                    record.published_at.isoformat(),
                    record.landing_url,
                    record.pdf_url,
                    record.access,
                    f'["{record.matched_keywords[0]}"]',
                    record.semantic_score,
                    record.zh_summary,
                )
                for record in records
            ],
        )
        connection.commit()


def test_run_application_summarizes_only_unpushed_records_without_zh_summary(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)
    pipeline_result = build_pipeline_result()
    records = pipeline_result.matched_records
    records[1].zh_summary = "这篇论文总结已存在。"
    seed_records(db_path, records)

    summary_client = DummySummaryClient(
        {
            "Silicon photonics coherent transceiver": "这篇论文提出了面向数据中心的硅光相干收发方案。"
        }
    )
    rendered: dict[str, list[str]] = {}

    def renderer(records: list[PaperRecord]) -> str:
        rendered["summaries"] = [record.zh_summary or "" for record in records]
        return "ok"

    summary = run_application(
        tmp_path,
        settings_loader=lambda _: build_settings_for_main(db_path),
        pipeline_runner=lambda settings: pipeline_result,
        email_renderer=renderer,
        email_sender=DummySender(),
        smtp_password_getter=lambda: "smtp-secret",
        deepseek_api_key_getter=lambda: "deepseek-secret",
        summary_client_factory=lambda settings, api_key: summary_client,
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    assert "to_push=2" in summary
    assert summary_client.calls == [
        (
            "Silicon photonics coherent transceiver",
            "A compact coherent transceiver.",
            ["硅光"],
        )
    ]
    assert rendered["summaries"] == [
        "这篇论文提出了面向数据中心的硅光相干收发方案。",
        "这篇论文总结已存在。",
    ]

    with sqlite3.connect(db_path) as connection:
        stored = connection.execute(
            "SELECT zh_summary FROM papers WHERE paper_id = ?",
            ("paper-1",),
        ).fetchone()

    assert stored == ("这篇论文提出了面向数据中心的硅光相干收发方案。",)
```

- [ ] **Step 2: 写失败测试，验证单篇总结失败会回退而不阻塞邮件发送**

继续在 `tests/test_main.py` 末尾追加：

```python
class PartiallyFailingSummaryClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def summarize_paper(
        self,
        *,
        title: str,
        abstract: str,
        matched_keywords: list[str],
    ) -> str:
        self.calls.append(title)
        if title == "Silicon photonics coherent transceiver":
            raise RuntimeError("temporary upstream failure")
        return "这篇论文给出了超表面封装方案。"


def test_run_application_falls_back_when_single_summary_generation_fails(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)
    records = build_pipeline_result().matched_records
    seed_records(db_path, records)
    summary_client = PartiallyFailingSummaryClient()
    rendered: dict[str, list[str | None]] = {}
    sender = DummySender()

    def renderer(records: list[PaperRecord]) -> str:
        rendered["summaries"] = [record.zh_summary for record in records]
        return "body"

    summary = run_application(
        tmp_path,
        settings_loader=lambda _: build_settings_for_main(db_path),
        pipeline_runner=lambda settings: build_pipeline_result(),
        email_renderer=renderer,
        email_sender=sender,
        smtp_password_getter=lambda: "smtp-secret",
        deepseek_api_key_getter=lambda: "deepseek-secret",
        summary_client_factory=lambda settings, api_key: summary_client,
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    assert "email_sent=yes" in summary
    assert summary_client.calls == [
        "Silicon photonics coherent transceiver",
        "Metasurface packaging",
    ]
    assert rendered["summaries"] == [None, "这篇论文给出了超表面封装方案。"]
    assert len(sender.calls) == 1
```

- [ ] **Step 3: 写失败测试，验证邮件发送失败也不会回滚已落库的中文总结**

继续在 `tests/test_main.py` 末尾追加：

```python
import pytest


def test_run_application_keeps_persisted_summary_when_email_send_fails(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)
    records = build_pipeline_result().matched_records
    seed_records(db_path, records)
    summary_client = DummySummaryClient(
        {
            "Silicon photonics coherent transceiver": "这篇论文提出了硅光相干收发实现方案。",
            "Metasurface packaging": "这篇论文给出了超表面封装方法。",
        }
    )

    with pytest.raises(RuntimeError, match="smtp down"):
        run_application(
            tmp_path,
            settings_loader=lambda _: build_settings_for_main(db_path),
            pipeline_runner=lambda settings: build_pipeline_result(),
            email_renderer=lambda records: "body",
            email_sender=lambda config, subject, body: (_ for _ in ()).throw(
                RuntimeError("smtp down")
            ),
            smtp_password_getter=lambda: "smtp-secret",
            deepseek_api_key_getter=lambda: "deepseek-secret",
            summary_client_factory=lambda settings, api_key: summary_client,
            now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
        )

    with sqlite3.connect(db_path) as connection:
        summary_rows = connection.execute(
            "SELECT paper_id, zh_summary FROM papers ORDER BY paper_id"
        ).fetchall()
        push_count = connection.execute(
            "SELECT COUNT(*) FROM push_log"
        ).fetchone()[0]

    assert summary_rows == [
        ("paper-1", "这篇论文提出了硅光相干收发实现方案。"),
        ("paper-2", "这篇论文给出了超表面封装方法。"),
    ]
    assert push_count == 0
```

- [ ] **Step 4: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_main.py -q`

Expected:

```text
...FFF
3 failed, 3 passed
```

- [ ] **Step 5: 写最小实现**

把 `src/paper_crawler/main.py` 改成：

```python
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from paper_crawler.llm import DeepSeekClient, DeepSeekConfig
from paper_crawler.notify.email_renderer import render_email_summary
from paper_crawler.notify.smtp_sender import SMTPConfig, send_email
from paper_crawler.processing import PipelineResult, run_pipeline
from paper_crawler.settings import Settings, load_settings
from paper_crawler.storage import (
    PaperRepository,
    PushLogRepository,
    connect_sqlite,
    initialize_database,
    resolve_sqlite_path,
)


def build_summary_client(
    settings: Settings,
    api_key: str | None,
) -> DeepSeekClient | None:
    if not settings.llm.enabled:
        return None
    if settings.llm.provider != "deepseek":
        return None
    if not api_key:
        return None
    return DeepSeekClient(
        DeepSeekConfig(
            base_url=settings.llm.base_url,
            model=settings.llm.model,
            api_key=api_key,
            timeout_seconds=settings.llm.timeout_seconds,
        )
    )


def run_application(
    config_dir: Path,
    settings_loader: Callable[[Path], Settings] = load_settings,
    pipeline_runner: Callable[[Settings], PipelineResult] = run_pipeline,
    email_renderer: Callable[[list], str] = render_email_summary,
    email_sender: Callable[[SMTPConfig, str, str], None] = send_email,
    smtp_password_getter: Callable[[], str | None] = lambda: os.getenv("SMTP_PASSWORD"),
    deepseek_api_key_getter: Callable[[], str | None] = lambda: os.getenv(
        "DEEPSEEK_API_KEY"
    ),
    summary_client_factory: Callable[[Settings, str | None], DeepSeekClient | None] = build_summary_client,
    now_func: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    settings = settings_loader(config_dir)
    result = pipeline_runner(settings)
    db_path = resolve_sqlite_path(settings.database_url)
    initialize_database(db_path)

    with connect_sqlite(db_path) as connection:
        paper_repository = PaperRepository(connection)
        push_log = PushLogRepository(connection)
        to_push = [
            record
            for record in result.matched_records
            if not push_log.has_been_pushed(record.paper_id)
        ]

        if to_push:
            summary_client = summary_client_factory(
                settings,
                deepseek_api_key_getter(),
            )
            summary_updated = False
            if summary_client is not None:
                for record in to_push:
                    if record.zh_summary:
                        continue
                    try:
                        summary = summary_client.summarize_paper(
                            title=record.title,
                            abstract=record.abstract,
                            matched_keywords=record.matched_keywords,
                        )
                    except Exception as exc:
                        logging.getLogger(__name__).warning(
                            "DeepSeek summary failed for %s: %s",
                            record.paper_id,
                            exc,
                        )
                        continue

                    record.zh_summary = summary
                    paper_repository.update_zh_summary(record.paper_id, summary)
                    summary_updated = True

            if summary_updated:
                connection.commit()

        email_sent = "no"
        if to_push:
            body = email_renderer(to_push)
            email_sender(
                SMTPConfig(
                    host=settings.smtp.host,
                    port=settings.smtp.port,
                    username=settings.smtp.username,
                    password=smtp_password_getter() or "",
                    from_address=settings.smtp.from_address,
                    to_address=settings.smtp.to_address,
                    use_tls=settings.smtp.use_tls,
                ),
                f"Daily paper digest ({len(to_push)})",
                body,
            )
            pushed_at = now_func()
            for record in to_push:
                push_log.mark_pushed(record.paper_id, pushed_at=pushed_at, channel="email")
            connection.commit()
            email_sent = "yes"

    return (
        f"Pipeline finished: fetched={result.fetched_count}, "
        f"matched={result.matched_count}, "
        f"to_push={len(to_push)}, "
        f"email_sent={email_sent}"
    )
```

- [ ] **Step 6: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_main.py -q`

Expected:

```text
6 passed
```

- [ ] **Step 7: 运行功能相关回归测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_database.py tests/test_settings.py tests/test_deepseek_client.py tests/test_email_renderer.py tests/test_pipeline.py tests/test_main.py -q`

Expected:

```text
30 passed
```

- [ ] **Step 8: 运行全量测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests -q`

Expected:

```text
49 passed
```

- [ ] **Step 9: 提交本任务**

```bash
git add src/paper_crawler/main.py tests/test_main.py
git commit -m "feat(main): generate zh summaries before email delivery"
```

## Self-Review

- **Spec coverage:** Task 1 覆盖 `zh_summary` 字段、schema 扩展、旧库迁移和仓储写回；Task 2 覆盖 LLM 配置、DeepSeek 客户端、OpenAI 兼容请求；Task 3 覆盖邮件正文优先展示中文总结；Task 4 覆盖只处理 `to_push`、跳过已有总结、单篇失败回退、邮件失败不回滚总结、`push_log` 仍只在发送成功后写入。
- **Placeholder scan:** 文档中没有 `TODO`、`TBD`、省略实现步骤或“自行处理”类描述；每个步骤都给出明确代码块、命令和预期输出。
- **Type consistency:** 全程统一使用 `PaperRecord.zh_summary`、`LLMSettings`、`DeepSeekConfig`、`DeepSeekClient.summarize_paper()`、`PaperRepository.update_zh_summary()` 和 `build_summary_client()` 这些名称，与规格中的字段和职责保持一致。
