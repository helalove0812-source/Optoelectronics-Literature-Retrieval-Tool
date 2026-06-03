# Arxiv Fetcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为项目接入第一个真实数据源 `arXiv`，能够按分类拉取最新论文、解析 Atom 响应、执行 24 小时过滤，并输出标准化 `PaperRecord` 列表。

**Architecture:** 保持 fetcher 只负责请求、解析与源内过滤，不把匹配、去重和入库逻辑塞进同一层。实现中通过注入 `session`、`sleep` 和 `now` 依赖来保证网络调用和时间窗口都可测试。

**Tech Stack:** Python 3.11、requests、feedparser、pytest、dataclasses、datetime

---

## File Map

- Modify: `src/paper_crawler/fetchers/base.py`
- Modify: `src/paper_crawler/fetchers/arxiv.py`
- Modify: `src/paper_crawler/utils/time_utils.py`
- Create: `tests/test_arxiv_fetcher.py`

### Task 1: 定义可复用的 fetcher 基类契约

**Files:**
- Modify: `src/paper_crawler/fetchers/base.py`
- Test: `tests/test_arxiv_fetcher.py`

- [ ] **Step 1: 写失败测试，要求 fetch result 可带来源统计**

```python
from paper_crawler.fetchers.base import FetchResult


def test_fetch_result_defaults_to_empty_records_and_count():
    result = FetchResult()
    assert result.records == []
    assert result.source == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_arxiv_fetcher.py::test_fetch_result_defaults_to_empty_records_and_count -q`

Expected: FAIL with `file or directory not found` or import error because test file/module is not ready

- [ ] **Step 3: 写最小基类契约**

```python
from dataclasses import dataclass, field

from paper_crawler.models import PaperRecord


@dataclass(slots=True)
class FetchResult:
    source: str = ""
    records: list[PaperRecord] = field(default_factory=list)


class BaseFetcher:
    source_name: str = ""

    def fetch(self) -> FetchResult:
        return FetchResult(source=self.source_name)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_arxiv_fetcher.py::test_fetch_result_defaults_to_empty_records_and_count -q`

Expected:

```text
1 passed
```

### Task 2: 实现 arXiv 请求与解析

**Files:**
- Modify: `src/paper_crawler/fetchers/arxiv.py`
- Modify: `src/paper_crawler/utils/time_utils.py`
- Create: `tests/test_arxiv_fetcher.py`

- [ ] **Step 1: 写失败测试，验证 arXiv fetcher 解析最新论文**

```python
from datetime import UTC, datetime

from paper_crawler.fetchers.arxiv import ArxivFetcher


class DummyResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        return None


class DummySession:
    def __init__(self, payload: str):
        self.payload = payload
        self.calls = []

    def get(self, url: str, params: dict[str, object], timeout: int):
        self.calls.append((url, params, timeout))
        return DummyResponse(self.payload)


def test_arxiv_fetcher_parses_recent_entries():
    feed = \"\"\"<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2506.00001v1</id>
        <published>2026-06-03T10:00:00Z</published>
        <title> Silicon Photonics for Coherent Links </title>
        <summary>Recent progress in coherent links.</summary>
        <author><name>Alice Smith</name></author>
        <author><name>Bob Chen</name></author>
        <link rel="alternate" href="http://arxiv.org/abs/2506.00001v1" />
        <link title="pdf" href="http://arxiv.org/pdf/2506.00001v1" />
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2505.99999v1</id>
        <published>2026-05-31T10:00:00Z</published>
        <title>Old Paper</title>
        <summary>Too old.</summary>
        <author><name>Older Author</name></author>
        <link rel="alternate" href="http://arxiv.org/abs/2505.99999v1" />
      </entry>
    </feed>\"\"\"

    session = DummySession(feed)
    fetcher = ArxivFetcher(
        categories=["physics.optics"],
        session=session,
        sleep_func=lambda _: None,
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    result = fetcher.fetch()

    assert result.source == "arxiv"
    assert len(result.records) == 1
    paper = result.records[0]
    assert paper.source == "arxiv"
    assert paper.title == "Silicon Photonics for Coherent Links"
    assert paper.authors == ["Alice Smith", "Bob Chen"]
    assert paper.access == "open"
    assert paper.pdf_url == "http://arxiv.org/pdf/2506.00001v1"
    assert paper.landing_url == "http://arxiv.org/abs/2506.00001v1"
    assert session.calls[0][1]["search_query"] == "cat:physics.optics"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_arxiv_fetcher.py::test_arxiv_fetcher_parses_recent_entries -q`

Expected: FAIL because `ArxivFetcher` constructor / fetch implementation is still missing

- [ ] **Step 3: 写最小实现**

`src/paper_crawler/utils/time_utils.py`

```python
from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_utc_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def within_lookback_window(value: datetime, hours: int, now: datetime | None = None) -> bool:
    reference = now or utc_now()
    return value >= reference - timedelta(hours=hours)
```

`src/paper_crawler/fetchers/arxiv.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import feedparser
import requests

from paper_crawler.fetchers.base import BaseFetcher, FetchResult
from paper_crawler.models import PaperRecord
from paper_crawler.utils.fingerprint import build_paper_fingerprint
from paper_crawler.utils.text_utils import normalize_text
from paper_crawler.utils.time_utils import parse_utc_datetime, utc_now, within_lookback_window


ARXIV_API_URL = "http://export.arxiv.org/api/query"


@dataclass(slots=True)
class ArxivFetcher(BaseFetcher):
    categories: list[str]
    max_results: int = 100
    lookback_hours: int = 24
    request_timeout: int = 30
    request_interval_seconds: int = 3
    session: requests.Session | object | None = None
    sleep_func: Callable[[float], None] | None = None
    now_func: Callable[[], object] = utc_now
    source_name: str = "arxiv"

    def fetch(self) -> FetchResult:
        session = self.session or requests.Session()
        sleep = self.sleep_func or (lambda _: None)
        now = self.now_func()
        records: list[PaperRecord] = []

        for index, category in enumerate(self.categories):
            if index > 0:
                sleep(self.request_interval_seconds)
            response = session.get(
                ARXIV_API_URL,
                params={
                    "search_query": f"cat:{category}",
                    "start": 0,
                    "max_results": min(self.max_results, 100),
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                },
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            parsed = feedparser.parse(response.text)
            for entry in parsed.entries:
                published_at = parse_utc_datetime(entry.published)
                if not within_lookback_window(published_at, self.lookback_hours, now=now):
                    continue
                title = normalize_text(entry.title).title()
                authors = [author.name for author in getattr(entry, "authors", [])]
                landing_url = next(
                    (link.href for link in entry.links if getattr(link, "rel", "") == "alternate"),
                    entry.id,
                )
                pdf_url = next(
                    (link.href for link in entry.links if getattr(link, "title", "") == "pdf"),
                    None,
                )
                paper_id = build_paper_fingerprint(title=title, authors=authors)
                records.append(
                    PaperRecord(
                        paper_id=paper_id,
                        title=title,
                        authors=authors,
                        abstract=normalize_text(entry.summary),
                        doi=None,
                        source=self.source_name,
                        published_at=published_at,
                        landing_url=landing_url,
                        pdf_url=pdf_url,
                        access="open",
                    )
                )

        return FetchResult(source=self.source_name, records=records)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_arxiv_fetcher.py::test_arxiv_fetcher_parses_recent_entries -q`

Expected:

```text
1 passed
```

### Task 3: 验证请求间隔与完整测试

**Files:**
- Modify: `tests/test_arxiv_fetcher.py`

- [ ] **Step 1: 增加失败测试，验证多分类时遵守间隔调用**

```python
from datetime import UTC, datetime

from paper_crawler.fetchers.arxiv import ArxivFetcher


def test_arxiv_fetcher_sleeps_between_categories():
    feed = """<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>"""
    sleeps = []

    class DummyResponse:
        text = feed

        def raise_for_status(self) -> None:
            return None

    class DummySession:
        def get(self, url: str, params: dict[str, object], timeout: int):
            return DummyResponse()

    fetcher = ArxivFetcher(
        categories=["physics.optics", "physics.app-ph"],
        session=DummySession(),
        sleep_func=lambda seconds: sleeps.append(seconds),
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    fetcher.fetch()

    assert sleeps == [3]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_arxiv_fetcher.py::test_arxiv_fetcher_sleeps_between_categories -q`

Expected: FAIL if request interval handling has not been implemented correctly

- [ ] **Step 3: 调整实现到最小通过**

保持 `ArxivFetcher.fetch()` 中：

```python
for index, category in enumerate(self.categories):
    if index > 0:
        sleep(self.request_interval_seconds)
```

- [ ] **Step 4: 运行 arXiv 全量测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_arxiv_fetcher.py -q`

Expected:

```text
3 passed
```

- [ ] **Step 5: 运行完整测试套件**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests -q`

Expected:

```text
10 passed
```

## Self-Review

- 覆盖范围：本计划覆盖了执行方案里 arXiv 的 API 地址、排序参数、Atom 解析、24 小时过滤和请求间隔要求。
- 占位检查：计划中未留下 `TODO` 或抽象描述，每一步都给出明确代码和命令。
- 一致性检查：输出统一使用 `PaperRecord` 和 `FetchResult`，时间处理统一走 `time_utils.py`。
