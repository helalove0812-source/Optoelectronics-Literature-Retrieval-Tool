# Unpaywall Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为命中关键词且有 DOI 的论文补上 `Unpaywall` 开放获取增强能力，在入库前回写 `pdf_url` 与 `access`，并保证查询失败不阻断主流程。

**Architecture:** `fetchers/unpaywall.py` 只负责 DOI 查询与最小字段解析，返回标准化 OA 结果；`pipeline.py` 只负责判断哪些论文要查、如何跳过 `arXiv` 与全 OA 期刊、以及如何在成功或失败后回写 `PaperRecord`。测试分为客户端单元测试和主流程集成测试，确保行为可独立验证。

**Tech Stack:** Python 3.11、requests、pytest、SQLite、dataclasses

---

## File Map

- Create: `tests/test_unpaywall.py`
- Modify: `src/paper_crawler/fetchers/unpaywall.py`
- Modify: `src/paper_crawler/processing/pipeline.py`
- Modify: `tests/test_pipeline.py`

### Task 1: 实现 Unpaywall 客户端与最小返回结构

**Files:**
- Create: `tests/test_unpaywall.py`
- Modify: `src/paper_crawler/fetchers/unpaywall.py`

- [ ] **Step 1: 写失败测试，验证 OA 响应解析**

```python
from paper_crawler.fetchers.unpaywall import UnpaywallClient


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class DummySession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url: str, params: dict[str, object], timeout: int):
        self.calls.append((url, params, timeout))
        return DummyResponse(self.payload)


def test_unpaywall_lookup_returns_oa_fields() -> None:
    session = DummySession(
        {
            "is_oa": True,
            "best_oa_location": {
                "url": "https://repository.example.com/landing",
                "url_for_pdf": "https://repository.example.com/paper.pdf",
            },
        }
    )
    client = UnpaywallClient(contact_email="team@example.com", session=session)

    result = client.lookup("10.1000/example")

    assert result == {
        "is_oa": True,
        "pdf_url": "https://repository.example.com/paper.pdf",
        "landing_url": "https://repository.example.com/landing",
    }
    assert session.calls[0][0].endswith("/10.1000/example")
    assert session.calls[0][1] == {"email": "team@example.com"}
```

- [ ] **Step 2: 写第二个失败测试，验证非 OA 响应解析**

```python
from paper_crawler.fetchers.unpaywall import UnpaywallClient


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class DummySession:
    def __init__(self, payload):
        self.payload = payload

    def get(self, url: str, params: dict[str, object], timeout: int):
        return DummyResponse(self.payload)


def test_unpaywall_lookup_returns_subscription_fields() -> None:
    client = UnpaywallClient(
        contact_email="team@example.com",
        session=DummySession({"is_oa": False, "best_oa_location": None}),
    )

    result = client.lookup("10.1000/subscription")

    assert result == {
        "is_oa": False,
        "pdf_url": None,
        "landing_url": None,
    }
```

- [ ] **Step 3: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_unpaywall.py -q`

Expected:

```text
2 failed
```

失败原因应为 `UnpaywallClient` 还未支持构造参数或 `lookup()` 仍返回空字典。

- [ ] **Step 4: 写最小实现**

`src/paper_crawler/fetchers/unpaywall.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import requests


UNPAYWALL_API_BASE = "https://api.unpaywall.org/v2"


class SupportsGet(Protocol):
    def get(self, url: str, params: dict[str, object], timeout: int): ...


@dataclass(slots=True)
class UnpaywallClient:
    contact_email: str
    session: SupportsGet | requests.Session | None = None
    request_timeout: int = 30

    def lookup(self, doi: str) -> dict[str, object]:
        session = self.session or requests.Session()
        response = session.get(
            f"{UNPAYWALL_API_BASE}/{doi}",
            params={"email": self.contact_email},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        best_location = payload.get("best_oa_location") or {}
        return {
            "is_oa": bool(payload.get("is_oa")),
            "pdf_url": best_location.get("url_for_pdf"),
            "landing_url": best_location.get("url"),
        }
```

- [ ] **Step 5: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_unpaywall.py -q`

Expected:

```text
2 passed
```

- [ ] **Step 6: 提交本任务**

```bash
git add tests/test_unpaywall.py src/paper_crawler/fetchers/unpaywall.py
git commit -m "feat: add unpaywall client"
```

### Task 2: 将 Unpaywall 增强接入 Pipeline

**Files:**
- Modify: `src/paper_crawler/processing/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: 写失败测试，验证只对命中且有 DOI 的记录调用 Unpaywall**

```python
from paper_crawler.fetchers.base import FetchResult
from paper_crawler.processing.pipeline import run_pipeline


class DummyUnpaywallClient:
    def __init__(self, response: dict[str, object]):
        self.response = response
        self.calls = []

    def lookup(self, doi: str) -> dict[str, object]:
        self.calls.append(doi)
        return self.response


def test_run_pipeline_enriches_only_matched_records_with_doi(tmp_path: Path) -> None:
    settings = build_settings()
    settings.database_url = f"sqlite:///{tmp_path / 'papers.db'}"

    matched_record = build_record()
    matched_record.paper_id = "paper-oa"
    matched_record.source = "crossref"
    matched_record.title = "Silicon photonics coherent link packaging"
    matched_record.abstract = "Photonics integration for datacenter optics."
    matched_record.doi = "10.1000/example"
    matched_record.pdf_url = None
    matched_record.access = "subscription"

    unmatched_record = build_record()
    unmatched_record.paper_id = "paper-no-match"
    unmatched_record.source = "crossref"
    unmatched_record.title = "Battery chemistry advances"
    unmatched_record.abstract = "Electrochemistry only."
    unmatched_record.doi = "10.1000/ignored"
    unmatched_record.pdf_url = None
    unmatched_record.access = "subscription"

    no_doi_record = build_record()
    no_doi_record.paper_id = "paper-no-doi"
    no_doi_record.source = "crossref"
    no_doi_record.title = "Silicon photonics integration"
    no_doi_record.abstract = "Datacenter optics."
    no_doi_record.doi = None
    no_doi_record.pdf_url = None
    no_doi_record.access = "subscription"

    client = DummyUnpaywallClient(
        {
            "is_oa": True,
            "pdf_url": "https://repository.example.com/paper.pdf",
            "landing_url": "https://repository.example.com/landing",
        }
    )

    run_pipeline(
        settings,
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(FetchResult(source="arxiv")),
        crossref_fetcher_factory=lambda _: DummyCrossrefFetcher(
            FetchResult(source="crossref", records=[matched_record, unmatched_record, no_doi_record])
        ),
        openalex_fetcher_factory=lambda _: DummyOpenAlexFetcher(FetchResult(source="openalex")),
        unpaywall_client_factory=lambda _: client,
    )

    assert client.calls == ["10.1000/example"]
    assert matched_record.access == "open"
    assert matched_record.pdf_url == "https://repository.example.com/paper.pdf"
    assert unmatched_record.access == "subscription"
    assert no_doi_record.access == "subscription"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline.py::test_run_pipeline_enriches_only_matched_records_with_doi -q`

Expected:

```text
1 failed
```

失败原因应为 `run_pipeline()` 尚未接收 `unpaywall_client_factory` 或未回写 OA 字段。

- [ ] **Step 3: 写最小实现**

`src/paper_crawler/processing/pipeline.py`

```python
from paper_crawler.fetchers.unpaywall import UnpaywallClient


def build_unpaywall_client(settings: Settings) -> UnpaywallClient:
    return UnpaywallClient(contact_email=settings.contact_email)


def run_pipeline(
    settings: Settings,
    arxiv_fetcher_factory: Callable[[Settings], ArxivFetcher] = build_arxiv_fetcher,
    crossref_fetcher_factory: Callable[[Settings], CrossrefFetcher] = build_crossref_fetcher,
    openalex_fetcher_factory: Callable[[Settings], OpenAlexFetcher] = build_openalex_fetcher,
    unpaywall_client_factory: Callable[[Settings], UnpaywallClient] = build_unpaywall_client,
) -> PipelineResult:
    ...
    unpaywall_client = unpaywall_client_factory(settings)
    for record in records:
        record.matched_keywords = match_keywords(...)
        if record.matched_keywords:
            matched_count += 1
        if (
            record.matched_keywords
            and record.doi
            and record.source != "arxiv"
        ):
            try:
                lookup = unpaywall_client.lookup(record.doi)
            except Exception as exc:
                logging.getLogger(__name__).warning("Unpaywall lookup failed for %s: %s", record.doi, exc)
                continue
            if lookup["is_oa"]:
                record.access = "open"
                record.pdf_url = lookup["pdf_url"]
                if lookup["landing_url"]:
                    record.landing_url = str(lookup["landing_url"])
            else:
                record.access = "subscription"
```

- [ ] **Step 4: 运行定向测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline.py::test_run_pipeline_enriches_only_matched_records_with_doi -q`

Expected:

```text
1 passed
```

- [ ] **Step 5: 提交本任务**

```bash
git add src/paper_crawler/processing/pipeline.py tests/test_pipeline.py
git commit -m "feat: enrich matched papers with unpaywall"
```

### Task 3: 验证容错与持久化

**Files:**
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: 写失败测试，验证查询失败不阻断主流程**

```python
import sqlite3

from paper_crawler.fetchers.base import FetchResult
from paper_crawler.processing.pipeline import run_pipeline


class FailingUnpaywallClient:
    def lookup(self, doi: str) -> dict[str, object]:
        raise RuntimeError("temporary upstream failure")


def test_run_pipeline_continues_when_unpaywall_lookup_fails(tmp_path: Path) -> None:
    settings = build_settings()
    db_path = tmp_path / "papers.db"
    settings.database_url = f"sqlite:///{db_path}"

    record = build_record()
    record.paper_id = "paper-failing-unpaywall"
    record.source = "crossref"
    record.title = "Silicon photonics coherent link packaging"
    record.abstract = "Photonics integration for datacenter optics."
    record.doi = "10.1000/example"
    record.pdf_url = None
    record.access = "subscription"

    result = run_pipeline(
        settings,
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(FetchResult(source="arxiv")),
        crossref_fetcher_factory=lambda _: DummyCrossrefFetcher(
            FetchResult(source="crossref", records=[record])
        ),
        openalex_fetcher_factory=lambda _: DummyOpenAlexFetcher(FetchResult(source="openalex")),
        unpaywall_client_factory=lambda _: FailingUnpaywallClient(),
    )

    with sqlite3.connect(db_path) as connection:
        stored = connection.execute(
            "SELECT access, pdf_url FROM papers WHERE paper_id = ?",
            (record.paper_id,),
        ).fetchone()

    assert result.fetched_count == 1
    assert result.matched_count == 1
    assert stored == ("subscription", None)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline.py::test_run_pipeline_continues_when_unpaywall_lookup_fails -q`

Expected:

```text
1 failed
```

失败原因应为异常未被吞掉或数据库未完成写入。

- [ ] **Step 3: 运行 Unpaywall 相关测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_unpaywall.py tests/test_pipeline.py -q`

Expected:

```text
13 passed
```

- [ ] **Step 4: 运行全量测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests -q`

Expected:

```text
30 passed
```

- [ ] **Step 5: 提交本任务**

```bash
git add tests/test_pipeline.py
git commit -m "test: cover unpaywall fallback behavior"
```

## Self-Review

- 规格覆盖：任务 1 覆盖客户端解析和 `email` 参数；任务 2 覆盖“仅命中且有 DOI”的增强规则；任务 3 覆盖失败容错与入库结果。
- 占位检查：无 `TODO`、`TBD`、"适当处理" 之类空泛描述，每步都给出代码和命令。
- 一致性检查：统一使用 `UnpaywallClient.lookup()`、`unpaywall_client_factory`、`pdf_url`、`access` 这些命名，与现有 `PaperRecord` 结构一致。
