# Crossref Fetcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为项目接入第二个真实数据源 `Crossref`，支持按 ISSN 白名单逐个查询，解析元数据，按时间窗口过滤，并输出标准化 `PaperRecord` 列表。

**Architecture:** 保持 `fetcher` 层只负责请求、解析和源内过滤，不把去重、入库和推送逻辑混进来。通过注入 `session`、`sleep_func`、`now_func` 保证网络、节流和时间判断都可测试。

**Tech Stack:** Python 3.11、requests、pytest、datetime、dataclasses

---

## File Map

- Modify: `src/paper_crawler/settings.py`
- Modify: `src/paper_crawler/fetchers/crossref.py`
- Modify: `src/paper_crawler/utils/time_utils.py`
- Create: `tests/test_crossref_fetcher.py`

### Task 1: 扩展配置模型，暴露 Crossref 所需字段

**Files:**
- Modify: `src/paper_crawler/settings.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: 写失败测试，验证 Settings 暴露白名单与联系邮箱**

```python
from pathlib import Path

from paper_crawler.settings import load_settings


def test_load_settings_exposes_crossref_inputs():
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root / "config")
    assert settings.contact_email == "team@example.com"
    assert settings.issn_whitelist["Optics Express"]["issn"] == "1094-4087"
```

- [ ] **Step 2: 运行测试确认失败或不完整**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_settings.py -q`

Expected: 若字段尚未按 fetcher 使用方式准备好，则测试失败或需要补齐类型/结构

- [ ] **Step 3: 仅做最小必要调整**

保持 `Settings` 中：

```python
contact_email: str
issn_whitelist: dict[str, dict[str, Any]]
lookback_hours: int
```

若已满足则不改配置文件，仅确认现有结构可直接供 `CrossrefFetcher` 使用。

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_settings.py -q`

Expected:

```text
1 passed
```

### Task 2: 实现 Crossref 基础拉取与解析

**Files:**
- Modify: `src/paper_crawler/fetchers/crossref.py`
- Create: `tests/test_crossref_fetcher.py`

- [ ] **Step 1: 写失败测试，验证 Crossref 解析最近论文**

```python
from datetime import UTC, datetime

from paper_crawler.fetchers.crossref import CrossrefFetcher


class DummyResponse:
    def __init__(self, payload: dict[str, object]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class DummySession:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload
        self.calls = []

    def get(self, url: str, params: dict[str, object], timeout: int):
        self.calls.append((url, params, timeout))
        return DummyResponse(self.payload)


def test_crossref_fetcher_parses_recent_items():
    payload = {
        "message": {
            "items": [
                {
                    "title": ["Integrated photonics for coherent links"],
                    "author": [
                        {"given": "Alice", "family": "Smith"},
                        {"given": "Bob", "family": "Chen"},
                    ],
                    "DOI": "10.1000/example",
                    "URL": "https://doi.org/10.1000/example",
                    "abstract": "<jats:p>Recent progress.</jats:p>",
                    "indexed": {"date-time": "2026-06-03T10:00:00Z"},
                },
                {
                    "title": ["Old paper"],
                    "author": [{"given": "Old", "family": "Author"}],
                    "DOI": "10.1000/old",
                    "URL": "https://doi.org/10.1000/old",
                    "indexed": {"date-time": "2026-05-20T10:00:00Z"},
                },
            ]
        }
    }
    session = DummySession(payload)
    fetcher = CrossrefFetcher(
        issn_whitelist={"Optics Express": {"issn": "1094-4087", "oa": True}},
        contact_email="team@example.com",
        lookback_hours=24,
        session=session,
        sleep_func=lambda _: None,
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    result = fetcher.fetch()

    assert result.source == "crossref"
    assert len(result.records) == 1
    paper = result.records[0]
    assert paper.doi == "10.1000/example"
    assert paper.title == "Integrated photonics for coherent links"
    assert paper.authors == ["Alice Smith", "Bob Chen"]
    assert paper.landing_url == "https://doi.org/10.1000/example"
    assert paper.access == "open"
    assert session.calls[0][1]["mailto"] == "team@example.com"
    assert "issn:1094-4087" in session.calls[0][1]["filter"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_crossref_fetcher.py::test_crossref_fetcher_parses_recent_items -q`

Expected: FAIL because `CrossrefFetcher` is still a placeholder

- [ ] **Step 3: 写最小实现**

`src/paper_crawler/fetchers/crossref.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from time import sleep
from typing import Callable, Protocol
import re

import requests

from paper_crawler.fetchers.base import BaseFetcher, FetchResult
from paper_crawler.models import PaperRecord
from paper_crawler.utils.fingerprint import build_paper_fingerprint
from paper_crawler.utils.time_utils import parse_utc_datetime, utc_now, within_lookback_window


CROSSREF_API_URL = "https://api.crossref.org/works"


class SupportsGet(Protocol):
    def get(self, url: str, params: dict[str, object], timeout: int): ...


@dataclass(slots=True)
class CrossrefFetcher(BaseFetcher):
    issn_whitelist: dict[str, dict[str, object]]
    contact_email: str
    lookback_hours: int = 24
    rows: int = 100
    request_timeout: int = 30
    request_interval_seconds: int = 1
    session: SupportsGet | requests.Session | None = None
    sleep_func: Callable[[int], None] = sleep
    now_func: Callable[[], object] = utc_now
    source_name: str = "crossref"

    def fetch(self) -> FetchResult:
        session = self.session or requests.Session()
        now = self.now_func()
        from_date = (now - timedelta(hours=self.lookback_hours)).date().isoformat()
        records: list[PaperRecord] = []

        for index, journal in enumerate(self.issn_whitelist.values()):
            if index > 0:
                self.sleep_func(self.request_interval_seconds)
            issn = str(journal["issn"])
            response = session.get(
                CROSSREF_API_URL,
                params={
                    "filter": f"issn:{issn},from-index-date:{from_date}",
                    "rows": min(self.rows, 100),
                    "mailto": self.contact_email,
                },
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            items = response.json().get("message", {}).get("items", [])
            for item in items:
                indexed_at = parse_utc_datetime(item["indexed"]["date-time"])
                if not within_lookback_window(indexed_at, self.lookback_hours, now=now):
                    continue
                title = (item.get("title") or [""])[0].strip()
                authors = [
                    " ".join(part for part in [author.get("given", ""), author.get("family", "")] if part).strip()
                    for author in item.get("author", [])
                ]
                doi = item.get("DOI")
                url = item.get("URL", "")
                abstract = re.sub(r"<[^>]+>", "", item.get("abstract", "") or "").strip()
                paper_id = doi or build_paper_fingerprint(title=title, authors=authors)
                records.append(
                    PaperRecord(
                        paper_id=paper_id,
                        title=title,
                        authors=authors,
                        abstract=abstract,
                        doi=doi,
                        source=self.source_name,
                        published_at=indexed_at,
                        landing_url=url,
                        pdf_url=None,
                        access="open" if journal.get("oa") else "subscription",
                    )
                )
        return FetchResult(source=self.source_name, records=records)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_crossref_fetcher.py::test_crossref_fetcher_parses_recent_items -q`

Expected:

```text
1 passed
```

### Task 3: 验证 Crossref 节流与全量测试

**Files:**
- Modify: `tests/test_crossref_fetcher.py`

- [ ] **Step 1: 增加失败测试，验证多 ISSN 间隔调用**

```python
from datetime import UTC, datetime

from paper_crawler.fetchers.crossref import CrossrefFetcher


def test_crossref_fetcher_sleeps_between_issn_requests():
    payload = {"message": {"items": []}}
    sleeps = []

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return payload

    class DummySession:
        def get(self, url: str, params: dict[str, object], timeout: int):
            return DummyResponse()

    fetcher = CrossrefFetcher(
        issn_whitelist={
            "Optics Express": {"issn": "1094-4087", "oa": True},
            "Photonics Research": {"issn": "2327-9125", "oa": True},
        },
        contact_email="team@example.com",
        session=DummySession(),
        sleep_func=lambda seconds: sleeps.append(seconds),
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    fetcher.fetch()

    assert sleeps == [1]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_crossref_fetcher.py::test_crossref_fetcher_sleeps_between_issn_requests -q`

Expected: FAIL if request interval handling is missing

- [ ] **Step 3: 保持最小实现通过**

确保 `fetch()` 中存在：

```python
for index, journal in enumerate(self.issn_whitelist.values()):
    if index > 0:
        self.sleep_func(self.request_interval_seconds)
```

- [ ] **Step 4: 运行定向测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_crossref_fetcher.py -q`

Expected:

```text
2 passed
```

- [ ] **Step 5: 运行全量测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests -q`

Expected:

```text
15 passed
```

## Self-Review

- 覆盖范围：已覆盖 Crossref 的 ISSN 白名单查询、`mailto`、`from-index-date`、`rows`、时间过滤和基础字段解析。
- 占位检查：无 `TODO` / `TBD`，每步都有代码和命令。
- 一致性检查：输出统一为 `PaperRecord` + `FetchResult`，时间统一使用 `parse_utc_datetime()` 与 `within_lookback_window()`。
