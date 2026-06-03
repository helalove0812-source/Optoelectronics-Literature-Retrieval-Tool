# OpenAlex Fetcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为项目接入 `OpenAlex` 数据源，支持按配置的 topic/concept 过滤片段查询近 24 小时新增 works，解析标准化字段并接入现有 `pipeline` 落库。

**Architecture:** `OpenAlexFetcher` 只负责请求、解析和时间过滤；`Settings` 只暴露 `openalex_filters` 配置，不在抓取器内猜测 topic 名称对应的真实 ID。`pipeline` 将 `OpenAlex` 作为第三个独立源接入，与 `arXiv`、`Crossref` 一样单源失败不阻断总流程。

**Tech Stack:** Python 3.11、requests、pytest、datetime、SQLite

---

## File Map

- Modify: `config/config.yaml`
- Modify: `src/paper_crawler/settings.py`
- Modify: `src/paper_crawler/fetchers/openalex.py`
- Modify: `src/paper_crawler/processing/pipeline.py`
- Modify: `tests/test_settings.py`
- Create: `tests/test_openalex_fetcher.py`
- Modify: `tests/test_pipeline.py`

### Task 1: 扩展配置，暴露 OpenAlex 过滤片段

**Files:**
- Modify: `config/config.yaml`
- Modify: `src/paper_crawler/settings.py`
- Modify: `tests/test_settings.py`

- [ ] **Step 1: 写失败测试，验证 Settings 读取 OpenAlex 过滤片段**

```python
from pathlib import Path

from paper_crawler.settings import load_settings


def test_load_settings_exposes_openalex_filters():
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root / "config")
    assert settings.openalex_filters == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_settings.py -q`

Expected: FAIL because `Settings` does not expose `openalex_filters`

- [ ] **Step 3: 写最小实现**

`config/config.yaml`

```yaml
sources:
  arxiv_categories:
    - physics.optics
    - physics.app-ph
  openalex_filters: []
```

`src/paper_crawler/settings.py`

```python
@dataclass
class Settings:
    ...
    openalex_filters: list[str]


def load_settings(config_dir: Path) -> Settings:
    ...
    return Settings(
        ...
        openalex_filters=sources.get("openalex_filters", []),
        ...
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_settings.py -q`

Expected:

```text
2 passed
```

### Task 2: 实现 OpenAlex 抓取与解析

**Files:**
- Modify: `src/paper_crawler/fetchers/openalex.py`
- Create: `tests/test_openalex_fetcher.py`

- [ ] **Step 1: 写失败测试，验证 OpenAlex 解析最近 works**

```python
from datetime import UTC, datetime

from paper_crawler.fetchers.openalex import OpenAlexFetcher


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class DummySession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        return DummyResponse(self.payload)


def test_openalex_fetcher_parses_recent_items():
    payload = {
        "results": [
            {
                "id": "https://openalex.org/W123",
                "display_name": "Integrated photonics packaging",
                "authorships": [
                    {"author": {"display_name": "Alice Smith"}},
                    {"author": {"display_name": "Bob Chen"}},
                ],
                "abstract_inverted_index": {
                    "Integrated": [0],
                    "photonics": [1],
                    "packaging": [2],
                },
                "doi": "https://doi.org/10.1000/example",
                "primary_location": {"landing_page_url": "https://doi.org/10.1000/example"},
                "created_date": "2026-06-03",
                "publication_date": "2026-06-03",
                "open_access": {
                    "is_oa": True,
                    "oa_url": "https://example.com/paper.pdf",
                },
            },
            {
                "id": "https://openalex.org/W124",
                "display_name": "Old photonics paper",
                "authorships": [{"author": {"display_name": "Old Author"}}],
                "created_date": "2026-05-01",
                "publication_date": "2026-05-01",
                "open_access": {"is_oa": False, "oa_url": None},
            },
        ]
    }
    session = DummySession(payload)
    fetcher = OpenAlexFetcher(
        filters=["topics.id:T123"],
        contact_email="team@example.com",
        lookback_hours=24,
        session=session,
        sleep_func=lambda _: None,
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    result = fetcher.fetch()

    assert result.source == "openalex"
    assert len(result.records) == 1
    paper = result.records[0]
    assert paper.paper_id == "https://openalex.org/W123"
    assert paper.title == "Integrated photonics packaging"
    assert paper.authors == ["Alice Smith", "Bob Chen"]
    assert paper.abstract == "Integrated photonics packaging"
    assert paper.doi == "10.1000/example"
    assert paper.access == "open"
    assert paper.pdf_url == "https://example.com/paper.pdf"
    assert "from_created_date:2026-06-02" in session.calls[0][1]["filter"]
    assert "topics.id:T123" in session.calls[0][1]["filter"]
    assert session.calls[0][1]["mailto"] == "team@example.com"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_openalex_fetcher.py::test_openalex_fetcher_parses_recent_items -q`

Expected: FAIL because `OpenAlexFetcher` is still placeholder

- [ ] **Step 3: 写最小实现**

`src/paper_crawler/fetchers/openalex.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, UTC
from time import sleep
from typing import Callable, Protocol

import requests

from paper_crawler.fetchers.base import BaseFetcher, FetchResult
from paper_crawler.models import PaperRecord
from paper_crawler.utils.time_utils import utc_now, within_lookback_window


OPENALEX_API_URL = "https://api.openalex.org/works"


class SupportsGet(Protocol):
    def get(self, url: str, params: dict[str, object], timeout: int): ...


def _rebuild_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    size = max(max(positions) for positions in index.values()) + 1
    words = [""] * size
    for token, positions in index.items():
        for position in positions:
            words[position] = token
    return " ".join(word for word in words if word)


def _parse_created_date(value: str) -> datetime:
    parsed = date.fromisoformat(value)
    return datetime.combine(parsed, time.min, tzinfo=UTC)


@dataclass(slots=True)
class OpenAlexFetcher(BaseFetcher):
    filters: list[str]
    contact_email: str
    lookback_hours: int = 24
    per_page: int = 100
    request_timeout: int = 30
    request_interval_seconds: int = 1
    session: SupportsGet | requests.Session | None = None
    sleep_func: Callable[[int], None] = sleep
    now_func: Callable[[], datetime] = utc_now
    source_name: str = "openalex"

    def fetch(self) -> FetchResult:
        session = self.session or requests.Session()
        now = self.now_func()
        from_date = (now - timedelta(hours=self.lookback_hours)).date().isoformat()
        records: list[PaperRecord] = []

        for index, filter_fragment in enumerate(self.filters):
            if index > 0:
                self.sleep_func(self.request_interval_seconds)
            response = session.get(
                OPENALEX_API_URL,
                params={
                    "filter": f"from_created_date:{from_date},{filter_fragment}",
                    "per-page": min(self.per_page, 100),
                    "mailto": self.contact_email,
                },
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            for item in response.json().get("results", []):
                created_at = _parse_created_date(item["created_date"])
                if not within_lookback_window(created_at, self.lookback_hours, now=now):
                    continue
                open_access = item.get("open_access") or {}
                doi_url = item.get("doi")
                landing_url = (item.get("primary_location") or {}).get("landing_page_url") or doi_url or item["id"]
                records.append(
                    PaperRecord(
                        paper_id=item["id"],
                        title=item.get("display_name", "").strip(),
                        authors=[
                            authorship.get("author", {}).get("display_name", "").strip()
                            for authorship in item.get("authorships", [])
                            if authorship.get("author", {}).get("display_name")
                        ],
                        abstract=_rebuild_abstract(item.get("abstract_inverted_index")),
                        doi=doi_url.removeprefix("https://doi.org/") if doi_url else None,
                        source=self.source_name,
                        published_at=created_at,
                        landing_url=landing_url,
                        pdf_url=open_access.get("oa_url"),
                        access="open" if open_access.get("is_oa") else "subscription",
                    )
                )
        return FetchResult(source=self.source_name, records=records)
```

- [ ] **Step 4: 运行定向测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_openalex_fetcher.py::test_openalex_fetcher_parses_recent_items -q`

Expected:

```text
1 passed
```

### Task 3: 接入 Pipeline

**Files:**
- Modify: `src/paper_crawler/processing/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: 写失败测试，验证 pipeline 会调用 OpenAlex**

```python
class DummyOpenAlexFetcher:
    def __init__(self, result: FetchResult):
        self.result = result
        self.called = False

    def fetch(self) -> FetchResult:
        self.called = True
        return self.result


def test_run_pipeline_uses_openalex_fetcher_and_counts_records() -> None:
    record = build_record()
    record.paper_id = "paper-openalex"
    record.source = "openalex"
    record.doi = "10.1000/example-openalex"
    record.landing_url = "https://openalex.org/W123"
    record.pdf_url = "https://example.com/paper.pdf"
    openalex_fetcher = DummyOpenAlexFetcher(
        FetchResult(source="openalex", records=[record])
    )

    result = run_pipeline(
        build_settings(),
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(FetchResult(source="arxiv")),
        crossref_fetcher_factory=lambda _: DummyCrossrefFetcher(FetchResult(source="crossref")),
        openalex_fetcher_factory=lambda _: openalex_fetcher,
    )

    assert openalex_fetcher.called is True
    assert result.fetched_count == 1
    assert result.matched_count == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline.py::test_run_pipeline_uses_openalex_fetcher_and_counts_records -q`

Expected: FAIL because `run_pipeline()` does not accept `openalex_fetcher_factory`

- [ ] **Step 3: 写最小实现**

`src/paper_crawler/processing/pipeline.py`

```python
from paper_crawler.fetchers.openalex import OpenAlexFetcher


def build_openalex_fetcher(settings: Settings) -> OpenAlexFetcher:
    return OpenAlexFetcher(
        filters=settings.openalex_filters,
        contact_email=settings.contact_email,
        lookback_hours=settings.lookback_hours,
    )


def run_pipeline(
    settings: Settings,
    arxiv_fetcher_factory: Callable[[Settings], ArxivFetcher] = build_arxiv_fetcher,
    crossref_fetcher_factory: Callable[[Settings], CrossrefFetcher] = build_crossref_fetcher,
    openalex_fetcher_factory: Callable[[Settings], OpenAlexFetcher] = build_openalex_fetcher,
) -> PipelineResult:
    ...
    try:
        openalex_result = openalex_fetcher_factory(settings).fetch()
        records.extend(openalex_result.records)
    except Exception as exc:
        logging.getLogger(__name__).warning("OpenAlex fetch failed: %s", exc)
```

- [ ] **Step 4: 运行定向测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline.py::test_run_pipeline_uses_openalex_fetcher_and_counts_records -q`

Expected:

```text
1 passed
```

- [ ] **Step 5: 运行全量测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests -q`

Expected:

```text
22 passed
```

## Self-Review

- 规格覆盖：覆盖了 OpenAlex 的日期过滤、`mailto`、topic/concept 过滤、标准化输出和接入 pipeline。
- 占位检查：无 `TODO` / `TBD`。
- 一致性检查：`Settings.openalex_filters`、`OpenAlexFetcher.filters` 和 `pipeline` 的工厂签名保持一致。
