# Tavily 空跑兜底 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 当某个 topic 在 `arXiv + Crossref + OpenAlex` 三源抓取后仍然 `fetched=0` 时，按 spec 触发一次 Tavily 搜索兜底，并把结果送入现有匹配、入库、去重与邮件链路。

**Architecture:** 保持现有三源主链路和 `main.py` 的订阅分发逻辑不变，只在 `pipeline` 中增加“空跑后再尝试 Tavily”的分支。Tavily 逻辑收敛在独立的 `fetchers/tavily.py`，配置仍经由 `settings.py` 读取，密钥通过项目根目录 `.env` 的 `TAVILY_API_KEY` 注入。

**Tech Stack:** Python 3.11, requests, pytest, PyYAML

---

### Task 1: Tavily 抓取器测试先行

**Files:**
- Create: `src/paper_crawler/fetchers/tavily.py`
- Create: `tests/test_tavily_fetcher.py`
- Test: `tests/test_tavily_fetcher.py`

- [ ] **Step 1: 写失败测试，锁定查询词构造、字段映射和 DOI 优先规则**

```python
from datetime import UTC, datetime

from paper_crawler.fetchers.tavily import TavilyFetcher


class DummyResponse:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class DummySession:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload
        self.calls: list[tuple[str, dict[str, object], int]] = []

    def post(self, url: str, json: dict[str, object], timeout: int) -> DummyResponse:
        self.calls.append((url, json, timeout))
        return DummyResponse(self.payload)


def test_tavily_fetcher_builds_compact_topic_query_and_maps_result() -> None:
    session = DummySession(
        {
            "results": [
                {
                    "title": "Integrated photonics paper with DOI",
                    "url": "https://example.com/paper",
                    "content": "A recent paper about integrated photonics and sensing.",
                    "published_date": "2026-06-04T08:00:00Z",
                }
            ]
        }
    )
    fetcher = TavilyFetcher(
        api_key="test-key",
        keyword_groups={
            "光计算": ["integrated photonics", "optical sensing", "optical computing"]
        },
        max_results=5,
        session=session,
        now_func=lambda: datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
    )

    records = fetcher.fetch().records

    assert session.calls[0][0] == "https://api.tavily.com/search"
    assert session.calls[0][1]["query"] == (
        "integrated photonics optical sensing optical computing paper arxiv doi"
    )
    assert session.calls[0][1]["max_results"] == 5
    assert records[0].source == "tavily"
    assert records[0].title == "Integrated photonics paper with DOI"
    assert records[0].landing_url == "https://example.com/paper"
    assert records[0].abstract.startswith("A recent paper")
    assert records[0].access == "subscription"


def test_tavily_fetcher_uses_doi_as_paper_id_and_falls_back_to_fingerprint() -> None:
    session = DummySession(
        {
            "results": [
                {
                    "title": "First result",
                    "url": "https://doi.org/10.1000/example",
                    "content": "Snippet with DOI 10.1000/example inside.",
                },
                {
                    "title": "Second result without doi",
                    "url": "https://example.com/no-doi",
                    "content": "No DOI here.",
                },
            ]
        }
    )
    fetcher = TavilyFetcher(
        api_key="test-key",
        keyword_groups={"机器人": ["motion planning", "embodied ai", "vla"]},
        session=session,
        now_func=lambda: datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
    )

    records = fetcher.fetch().records

    assert records[0].doi == "10.1000/example"
    assert records[0].paper_id == "10.1000/example"
    assert records[1].doi is None
    assert "::unknown" in records[1].paper_id
```

- [ ] **Step 2: 运行定向测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_tavily_fetcher.py -q`
Expected: FAIL，当前仓库还没有 `src/paper_crawler/fetchers/tavily.py`

- [ ] **Step 3: 再补失败测试，覆盖日期兜底与空结果行为**

```python
def test_tavily_fetcher_uses_now_when_result_has_no_parseable_date() -> None:
    now = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
    session = DummySession(
        {
            "results": [
                {
                    "title": "Undated result",
                    "url": "https://example.com/undated",
                    "content": "Snippet only.",
                }
            ]
        }
    )
    fetcher = TavilyFetcher(
        api_key="test-key",
        keyword_groups={"光学": ["integrated photonics"]},
        session=session,
        now_func=lambda: now,
    )

    records = fetcher.fetch().records

    assert records[0].published_at == now


def test_tavily_fetcher_returns_empty_fetch_result_when_api_returns_no_results() -> None:
    session = DummySession({"results": []})
    fetcher = TavilyFetcher(
        api_key="test-key",
        keyword_groups={"光学": ["integrated photonics"]},
        session=session,
    )

    result = fetcher.fetch()

    assert result.source == "tavily"
    assert result.records == []
```

- [ ] **Step 4: 再次运行定向测试确认仍失败在预期位置**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_tavily_fetcher.py -q`
Expected: FAIL，失败点集中在 `TavilyFetcher` 不存在或未实现查询词/字段映射

- [ ] **Step 5: 提交测试骨架**

```bash
git add tests/test_tavily_fetcher.py
git commit -m "test(fetchers): cover tavily fallback fetcher"
```

### Task 2: 实现 Tavily 抓取器

**Files:**
- Create: `src/paper_crawler/fetchers/tavily.py`
- Test: `tests/test_tavily_fetcher.py`

- [ ] **Step 1: 实现最小 TavilyFetcher，负责请求 API 并映射 `PaperRecord`**

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

import requests

from paper_crawler.fetchers.base import BaseFetcher, FetchResult
from paper_crawler.models import PaperRecord
from paper_crawler.utils.fingerprint import build_paper_fingerprint
from paper_crawler.utils.time_utils import parse_utc_datetime, utc_now


class SupportsPost(Protocol):
    def post(self, url: str, json: dict[str, object], timeout: int): ...


@dataclass(slots=True)
class TavilyFetcher(BaseFetcher):
    api_key: str
    keyword_groups: dict[str, list[str]]
    max_results: int = 5
    request_timeout: int = 30
    session: SupportsPost | requests.Session | None = None
    now_func: Callable[[], datetime] = utc_now
    source_name: str = "tavily"

    def fetch(self) -> FetchResult:
        session = self.session or requests.Session()
        response = session.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self.api_key,
                "query": self._build_query(),
                "max_results": self.max_results,
            },
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        return FetchResult(
            source=self.source_name,
            records=self._parse_results(response.json().get("results", [])),
        )
```

- [ ] **Step 2: 补 `_build_query()`、DOI 提取和日期兜底逻辑**

```python
    def _build_query(self) -> str:
        core_terms: list[str] = []
        for terms in self.keyword_groups.values():
            for term in terms:
                normalized = " ".join(str(term).split()).strip()
                if normalized and normalized not in core_terms:
                    core_terms.append(normalized)
                if len(core_terms) >= 3:
                    break
            if len(core_terms) >= 3:
                break
        return " ".join([*core_terms, "paper", "arxiv", "doi"])

    def _parse_results(self, results: list[dict[str, object]]) -> list[PaperRecord]:
        records: list[PaperRecord] = []
        for item in results:
            title = " ".join(str(item.get("title", "")).split())
            landing_url = str(item.get("url", "")).strip()
            abstract = " ".join(str(item.get("content", "")).split())
            doi = self._extract_doi(f"{landing_url}\n{abstract}")
            published_at = self._parse_published_at(item.get("published_date"))
            records.append(
                PaperRecord(
                    paper_id=doi or build_paper_fingerprint(title=title, authors=[]),
                    title=title,
                    authors=[],
                    abstract=abstract,
                    doi=doi,
                    source=self.source_name,
                    published_at=published_at,
                    landing_url=landing_url,
                    pdf_url=None,
                    access="subscription",
                )
            )
        return records
```

- [ ] **Step 3: 运行 Tavily 抓取器测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_tavily_fetcher.py -q`
Expected: PASS

- [ ] **Step 4: 检查新文件诊断**

Run: 使用编辑器诊断检查 `src/paper_crawler/fetchers/tavily.py` 与 `tests/test_tavily_fetcher.py`
Expected: 无新增 diagnostics

- [ ] **Step 5: 提交实现**

```bash
git add src/paper_crawler/fetchers/tavily.py tests/test_tavily_fetcher.py
git commit -m "feat(fetchers): add tavily fallback fetcher"
```

### Task 3: 配置层与 Pipeline 触发测试

**Files:**
- Modify: `src/paper_crawler/settings.py`
- Modify: `tests/test_settings.py`
- Modify: `tests/test_pipeline.py`
- Test: `tests/test_settings.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: 写失败测试，覆盖 Tavily 运行配置读取与默认值**

```python
def test_load_settings_reads_tavily_runtime_fields(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_dir.joinpath("config.yaml").write_text(
        "\n".join(
            [
                "contact_email: test@example.com",
                "database_url: sqlite:///data/test.db",
                "smtp:",
                "  host: smtp.test.local",
                "  port: 2525",
                "  username: sender@test.local",
                "  from_address: sender@test.local",
                "  to_address: receiver@test.local",
                "  use_tls: false",
                "runtime:",
                "  lookback_hours: 12",
                "  semantic_threshold: 0.7",
                "  enable_semantic_matching: false",
                "  enable_tavily_fallback: true",
                "  tavily_max_results: 7",
                "sources:",
                "  arxiv_categories: [physics.optics]",
                "  openalex_filters: [photonics]",
            ]
        ),
        encoding="utf-8",
    )
    config_dir.joinpath("keywords.yaml").write_text("硅光:\n  - silicon photonics\n", encoding="utf-8")
    config_dir.joinpath("issn_whitelist.yaml").write_text("{}", encoding="utf-8")
    config_dir.joinpath("synonyms.yaml").write_text("{}", encoding="utf-8")

    settings = load_settings(config_dir)

    assert settings.enable_tavily_fallback is True
    assert settings.tavily_max_results == 7


def test_load_settings_defaults_tavily_runtime_fields_when_omitted(tmp_path: Path) -> None:
    ...
    assert settings.enable_tavily_fallback is False
    assert settings.tavily_max_results == 5
```

- [ ] **Step 2: 运行 settings 定向测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_settings.py -q`
Expected: FAIL，`Settings` 目前没有 Tavily 相关字段

- [ ] **Step 3: 在 `tests/test_pipeline.py` 增加失败测试，锁定空跑触发与跳过边界**

```python
class DummyTavilyFetcher:
    def __init__(self, result: FetchResult):
        self.result = result
        self.called = False

    def fetch(self) -> FetchResult:
        self.called = True
        return self.result


def test_run_pipeline_triggers_tavily_only_when_three_sources_return_no_records(
    tmp_path: Path,
) -> None:
    settings = build_settings()
    settings.database_url = f"sqlite:///{tmp_path / 'papers.db'}"
    settings.enable_tavily_fallback = True
    settings.tavily_max_results = 5
    tavily_record = build_record()
    tavily_record.paper_id = "paper-tavily"
    tavily_record.source = "tavily"
    tavily_record.title = "Silicon photonics from tavily"
    tavily_record.abstract = "Photonics integration for datacenter optics."
    tavily_record.landing_url = "https://example.com/tavily"
    tavily_record.pdf_url = None
    tavily_record.access = "subscription"
    tavily_fetcher = DummyTavilyFetcher(FetchResult(source="tavily", records=[tavily_record]))

    result = run_pipeline(
        settings,
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(FetchResult(source="arxiv")),
        crossref_fetcher_factory=lambda _: DummyCrossrefFetcher(FetchResult(source="crossref")),
        openalex_fetcher_factory=lambda _: DummyOpenAlexFetcher(FetchResult(source="openalex")),
        tavily_fetcher_factory=lambda _: tavily_fetcher,
    )

    assert tavily_fetcher.called is True
    assert result.fetched_count == 1
    assert result.matched_count == 1
    assert [record.paper_id for record in result.matched_records] == ["paper-tavily"]


def test_run_pipeline_skips_tavily_when_primary_sources_already_return_records(
    tmp_path: Path,
) -> None:
    ...
    assert tavily_fetcher.called is False


def test_run_pipeline_skips_tavily_when_disabled_or_factory_returns_none(
    tmp_path: Path,
) -> None:
    ...
    assert result.fetched_count == 0
```

- [ ] **Step 4: 再补一个 Tavily 异常不阻断主流程的失败测试**

```python
class FailingTavilyFetcher:
    def fetch(self) -> FetchResult:
        raise RuntimeError("temporary tavily outage")


def test_run_pipeline_continues_when_tavily_fallback_fails(tmp_path: Path) -> None:
    settings = build_settings()
    settings.database_url = f"sqlite:///{tmp_path / 'papers.db'}"
    settings.enable_tavily_fallback = True

    result = run_pipeline(
        settings,
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(FetchResult(source="arxiv")),
        crossref_fetcher_factory=lambda _: DummyCrossrefFetcher(FetchResult(source="crossref")),
        openalex_fetcher_factory=lambda _: DummyOpenAlexFetcher(FetchResult(source="openalex")),
        tavily_fetcher_factory=lambda _: FailingTavilyFetcher(),
    )

    assert result.fetched_count == 0
    assert result.matched_count == 0
    assert result.matched_records == []
```

- [ ] **Step 5: 运行 pipeline 与 settings 定向测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_settings.py tests/test_pipeline.py -q`
Expected: FAIL，当前 `run_pipeline()` 不接收 `tavily_fetcher_factory`，`Settings` 也没有 Tavily 配置字段

- [ ] **Step 6: 提交测试骨架**

```bash
git add tests/test_settings.py tests/test_pipeline.py
git commit -m "test(pipeline): cover tavily empty-run fallback"
```

### Task 4: 接入 Tavily 配置与 Pipeline 兜底逻辑

**Files:**
- Modify: `src/paper_crawler/settings.py`
- Modify: `src/paper_crawler/processing/pipeline.py`
- Modify: `.env.example`
- Test: `tests/test_settings.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/test_tavily_fetcher.py`

- [ ] **Step 1: 在 `settings.py` 加 Tavily 运行配置，并保持旧配置兼容**

```python
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
    enable_tavily_fallback: bool
    tavily_max_results: int


    ...
    return Settings(
        ...
        enable_tavily_fallback=bool(runtime.get("enable_tavily_fallback", False)),
        tavily_max_results=int(runtime.get("tavily_max_results", 5)),
    )
```

- [ ] **Step 2: 在 `pipeline.py` 新增 Tavily 工厂，并只在三源空跑时触发一次**

```python
from typing import Callable
import os

from paper_crawler.fetchers.tavily import TavilyFetcher


def build_tavily_fetcher(
    settings: Settings,
    api_key_getter: Callable[[], str | None] = lambda: os.getenv("TAVILY_API_KEY"),
) -> TavilyFetcher | None:
    if not settings.enable_tavily_fallback:
        return None
    api_key = api_key_getter()
    if not api_key:
        return None
    return TavilyFetcher(
        api_key=api_key,
        keyword_groups=settings.keyword_groups,
        max_results=settings.tavily_max_results,
    )


def run_pipeline(
    settings: Settings,
    arxiv_fetcher_factory=build_arxiv_fetcher,
    crossref_fetcher_factory=build_crossref_fetcher,
    openalex_fetcher_factory=build_openalex_fetcher,
    unpaywall_client_factory=build_unpaywall_client,
    tavily_fetcher_factory: Callable[[Settings], TavilyFetcher | None] = build_tavily_fetcher,
) -> PipelineResult:
    records = []
    ...
    if not records:
        tavily_fetcher = tavily_fetcher_factory(settings)
        if tavily_fetcher is not None:
            try:
                records.extend(tavily_fetcher.fetch().records)
            except Exception as exc:
                logging.getLogger(__name__).warning("Tavily fallback failed: %s", exc)
```

- [ ] **Step 3: 在 `.env.example` 增加 Tavily 密钥示例**

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USERNAME=research-alert@example.com
SMTP_PASSWORD=change-me
SMTP_FROM=research-alert@example.com
CONTACT_EMAIL=team@example.com
DATABASE_URL=sqlite:///data/papers.db
DEEPSEEK_API_KEY=change-me
TAVILY_API_KEY=change-me
```

- [ ] **Step 4: 运行定向测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_settings.py tests/test_tavily_fetcher.py tests/test_pipeline.py -q`
Expected: PASS

- [ ] **Step 5: 运行回归测试，确保主流程与订阅邮件未受影响**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_main.py tests/test_settings.py tests/test_tavily_fetcher.py tests/test_pipeline.py -q`
Expected: PASS

- [ ] **Step 6: 检查最近修改文件诊断**

Run: 使用编辑器诊断检查 `src/paper_crawler/fetchers/tavily.py`、`src/paper_crawler/settings.py`、`src/paper_crawler/processing/pipeline.py`、`tests/test_tavily_fetcher.py`、`tests/test_settings.py`、`tests/test_pipeline.py`
Expected: 无新增 diagnostics

- [ ] **Step 7: 提交实现**

```bash
git add .env.example src/paper_crawler/fetchers/tavily.py src/paper_crawler/settings.py src/paper_crawler/processing/pipeline.py tests/test_tavily_fetcher.py tests/test_settings.py tests/test_pipeline.py
git commit -m "feat(pipeline): add tavily empty-run fallback"
```

### Task 5: 最终验证与计划收尾

**Files:**
- Modify: `docs/superpowers/plans/2026-06-04-tavily-empty-run-fallback.md`

- [ ] **Step 1: 跑全量测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests -q`
Expected: PASS

- [ ] **Step 2: 对照 spec 自检覆盖情况**

```text
- 触发条件：Task 3/4 覆盖三源空跑才触发
- 配置与密钥：Task 3/4 覆盖 runtime 字段和 .env.example
- Tavily 结果模型：Task 1/2 覆盖 title/url/content/doi/paper_id/source
- 容错：Task 3/4 覆盖 key 缺失与 Tavily 异常
```

- [ ] **Step 3: 更新计划勾选状态并记录测试结果**

```markdown
- [x] Step 1 ...
- [x] Step 2 ...
- [x] Step 3 ...
```

- [ ] **Step 4: 提交计划收尾**

```bash
git add docs/superpowers/plans/2026-06-04-tavily-empty-run-fallback.md
git commit -m "docs: mark tavily fallback plan complete"
```
