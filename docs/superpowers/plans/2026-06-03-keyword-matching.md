# Keyword Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为现有论文抓取主流程补上基于关键词组和同义词表的 MVP 关键词匹配能力，并将命中分组回写到 `PaperRecord.matched_keywords`。

**Architecture:** 匹配逻辑集中在 `matchers/keyword_matcher.py`，拆成“构建关键词索引”和“单篇论文匹配”两层，避免每条记录重复展开同义词。`pipeline.py` 只负责编排调用、填充命中结果、更新 `matched_count`，数据库层沿用现有 `matched_keywords_json` 持久化能力。

**Tech Stack:** Python 3.11、pytest、SQLite、dataclasses

---

## File Map

- Create: `tests/test_keyword_matcher.py`
- Modify: `src/paper_crawler/matchers/keyword_matcher.py`
- Modify: `src/paper_crawler/processing/pipeline.py`
- Modify: `tests/test_pipeline.py`

### Task 1: 实现关键词索引与基础匹配

**Files:**
- Create: `tests/test_keyword_matcher.py`
- Modify: `src/paper_crawler/matchers/keyword_matcher.py`

- [ ] **Step 1: 写失败测试，锁定分组名输出和同义词展开**

```python
from paper_crawler.matchers.keyword_matcher import build_keyword_index, match_keywords


def test_match_keywords_returns_group_names_for_direct_and_synonym_hits() -> None:
    keyword_groups = {
        "硅光": ["silicon photonics"],
        "超表面": ["metasurface"],
    }
    synonyms = {
        "silicon photonics": ["SiPh", "硅光"],
        "metasurface": ["超表面"],
    }

    keyword_index = build_keyword_index(keyword_groups, synonyms)

    matched = match_keywords(
        title="SiPh packaging for datacenter optics",
        abstract="This metasurface platform improves coupling efficiency.",
        keyword_index=keyword_index,
    )

    assert matched == ["硅光", "超表面"]
```

- [ ] **Step 2: 写第二个失败测试，锁定去重与空命中行为**

```python
from paper_crawler.matchers.keyword_matcher import build_keyword_index, match_keywords


def test_match_keywords_deduplicates_group_hits_and_returns_empty_when_unmatched() -> None:
    keyword_groups = {"光通信": ["optical communication", "coherent optics"]}
    synonyms = {"optical communication": ["optical communications"]}
    keyword_index = build_keyword_index(keyword_groups, synonyms)

    matched = match_keywords(
        title="Optical communication systems",
        abstract="Coherent optics remains central to optical communications.",
        keyword_index=keyword_index,
    )
    unmatched = match_keywords(
        title="Solid-state batteries",
        abstract="Electrochemistry only.",
        keyword_index=keyword_index,
    )

    assert matched == ["光通信"]
    assert unmatched == []
```

- [ ] **Step 3: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_keyword_matcher.py -q`

Expected:

```text
2 failed
```

失败原因应为 `build_keyword_index` 未定义或 `match_keywords` 仍返回空列表。

- [ ] **Step 4: 写最小实现**

`src/paper_crawler/matchers/keyword_matcher.py`

```python
from __future__ import annotations

from collections import OrderedDict


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def build_keyword_index(
    keyword_groups: dict[str, list[str]],
    synonyms: dict[str, list[str]],
) -> dict[str, list[str]]:
    keyword_index: dict[str, list[str]] = OrderedDict()

    for group_name, keywords in keyword_groups.items():
        expanded_terms: list[str] = []
        seen_terms: set[str] = set()

        for keyword in keywords:
            candidates = [keyword, *synonyms.get(keyword, [])]
            for candidate in candidates:
                normalized = _normalize_text(candidate)
                if normalized and normalized not in seen_terms:
                    seen_terms.add(normalized)
                    expanded_terms.append(normalized)

        keyword_index[group_name] = expanded_terms

    return keyword_index


def match_keywords(
    title: str,
    abstract: str,
    keyword_index: dict[str, list[str]],
) -> list[str]:
    haystack = _normalize_text(f"{title} {abstract}")
    if not haystack:
        return []

    matched_groups: list[str] = []
    for group_name, candidates in keyword_index.items():
        if any(candidate in haystack for candidate in candidates):
            matched_groups.append(group_name)

    return matched_groups
```

- [ ] **Step 5: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_keyword_matcher.py -q`

Expected:

```text
2 passed
```

- [ ] **Step 6: 提交本任务**

```bash
git add tests/test_keyword_matcher.py src/paper_crawler/matchers/keyword_matcher.py
git commit -m "feat: add keyword matcher"
```

### Task 2: 将关键词匹配接入 Pipeline 计数逻辑

**Files:**
- Modify: `src/paper_crawler/processing/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: 写失败测试，验证 pipeline 填充 matched_keywords 且只统计命中论文**

```python
from paper_crawler.fetchers.base import FetchResult
from paper_crawler.processing.pipeline import run_pipeline


def test_run_pipeline_populates_matched_keywords_and_counts_only_matches(tmp_path) -> None:
    settings = build_settings()
    settings.database_url = f"sqlite:///{tmp_path / 'papers.db'}"

    matched_record = build_record()
    matched_record.paper_id = "paper-match"
    matched_record.title = "SiPh coherent link packaging"
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
    )

    assert matched_record.matched_keywords == ["硅光"]
    assert unmatched_record.matched_keywords == []
    assert result.fetched_count == 2
    assert result.matched_count == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline.py::test_run_pipeline_populates_matched_keywords_and_counts_only_matches -q`

Expected:

```text
1 failed
```

失败原因应为 `matched_keywords` 未被填充或 `matched_count` 仍等于总抓取数。

- [ ] **Step 3: 写最小实现**

`src/paper_crawler/processing/pipeline.py`

```python
from paper_crawler.matchers.keyword_matcher import build_keyword_index, match_keywords


def run_pipeline(
    settings: Settings,
    arxiv_fetcher_factory: Callable[[Settings], ArxivFetcher] = build_arxiv_fetcher,
    crossref_fetcher_factory: Callable[[Settings], CrossrefFetcher] = build_crossref_fetcher,
    openalex_fetcher_factory: Callable[[Settings], OpenAlexFetcher] = build_openalex_fetcher,
) -> PipelineResult:
    records = []
    ...
    if not records:
        return PipelineResult(fetched_count=0, matched_count=0)

    keyword_index = build_keyword_index(settings.keyword_groups, settings.synonyms)
    matched_count = 0
    for record in records:
        record.matched_keywords = match_keywords(
            title=record.title,
            abstract=record.abstract,
            keyword_index=keyword_index,
        )
        if record.matched_keywords:
            matched_count += 1

    db_path = resolve_sqlite_path(settings.database_url)
    initialize_database(db_path)
    ...
    fetched_count = len(records)
    return PipelineResult(fetched_count=fetched_count, matched_count=matched_count)
```

- [ ] **Step 4: 运行定向测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline.py::test_run_pipeline_populates_matched_keywords_and_counts_only_matches -q`

Expected:

```text
1 passed
```

- [ ] **Step 5: 提交本任务**

```bash
git add src/paper_crawler/processing/pipeline.py tests/test_pipeline.py
git commit -m "feat: apply keyword matching in pipeline"
```

### Task 3: 验证匹配结果入库并回归全量测试

**Files:**
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: 写失败测试，验证入库记录保留 matched_keywords**

```python
import json
import sqlite3

from paper_crawler.fetchers.base import FetchResult
from paper_crawler.processing.pipeline import run_pipeline


def test_run_pipeline_persists_matched_keywords_json(tmp_path) -> None:
    settings = build_settings()
    db_path = tmp_path / "papers.db"
    settings.database_url = f"sqlite:///{db_path}"

    record = build_record()
    record.paper_id = "paper-keywords"
    record.title = "Silicon photonics packaging for AI clusters"
    record.abstract = "Photonic integration only."

    run_pipeline(
        settings,
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(
            FetchResult(source="arxiv", records=[record])
        ),
        crossref_fetcher_factory=lambda _: DummyCrossrefFetcher(FetchResult(source="crossref")),
        openalex_fetcher_factory=lambda _: DummyOpenAlexFetcher(FetchResult(source="openalex")),
    )

    with sqlite3.connect(db_path) as connection:
        raw_value = connection.execute(
            "SELECT matched_keywords_json FROM papers WHERE paper_id = ?",
            (record.paper_id,),
        ).fetchone()[0]

    assert json.loads(raw_value) == ["硅光"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline.py::test_run_pipeline_persists_matched_keywords_json -q`

Expected:

```text
1 failed
```

失败原因应为入库前尚未给记录填充 `matched_keywords`。

- [ ] **Step 3: 运行匹配相关测试套件**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_keyword_matcher.py tests/test_pipeline.py -q`

Expected:

```text
8 passed
```

- [ ] **Step 4: 运行全量测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests -q`

Expected:

```text
27 passed
```

- [ ] **Step 5: 提交本任务**

```bash
git add tests/test_pipeline.py
git commit -m "test: verify keyword matches persist in storage"
```

## Self-Review

- 规格覆盖：任务 1 覆盖分组驱动匹配和同义词展开，任务 2 覆盖 `pipeline` 集成与 `matched_count` 行为，任务 3 覆盖入库结果与回归测试。
- 占位检查：无 `TODO`、`TBD`、"handle appropriately" 之类空泛描述，每一步都给出实际代码和命令。
- 一致性检查：计划中统一使用 `build_keyword_index()`、`match_keywords()`、`matched_keywords` 和 `matched_count` 这些名称，与当前代码结构一致。
