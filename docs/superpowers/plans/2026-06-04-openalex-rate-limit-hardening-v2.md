# OpenAlex 限流增强（v2） Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 OpenAlex 抓取器在免费配额场景下以 `per_page=100`、429 重试和退避等待的方式更稳定运行。

**Architecture:** 保持现有 `pipeline` 容错边界不变，只在 `OpenAlexFetcher` 内部实现请求参数收紧、限流重试和日志增强。测试集中在 `tests/test_openalex_fetcher.py`，验证参数、退避、失败边界和非 429 错误语义。

**Tech Stack:** Python 3.11, requests, pytest

---

### Task 1: OpenAlex 参数与重试测试

**Files:**
- Modify: `tests/test_openalex_fetcher.py`
- Test: `tests/test_openalex_fetcher.py`

- [ ] **Step 1: 写失败测试，覆盖 per_page=100 与 Retry-After 重试**

```python
def test_openalex_fetcher_caps_per_page_at_100() -> None:
    ...
    assert session.calls[0][1]["per-page"] == 100


def test_openalex_fetcher_retries_429_with_retry_after_header() -> None:
    ...
    assert sleep_calls == [7]
    assert len(session.calls) == 2
```

- [ ] **Step 2: 运行定向测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_openalex_fetcher.py -q`
Expected: FAIL，现有实现仍然发送 `per-page=200`，且没有 429 重试能力

- [ ] **Step 3: 补失败测试，覆盖指数退避、最大重试与非 429 错误**

```python
def test_openalex_fetcher_retries_429_with_exponential_backoff() -> None:
    ...
    assert sleep_calls == [5, 10, 20]


def test_openalex_fetcher_raises_after_exhausting_429_retries() -> None:
    with pytest.raises(requests.HTTPError):
        fetcher.fetch()


def test_openalex_fetcher_does_not_retry_non_429_http_error() -> None:
    with pytest.raises(requests.HTTPError):
        fetcher.fetch()
    assert sleep_calls == []
```

- [ ] **Step 4: 再次运行测试确认新增场景都失败在预期位置**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_openalex_fetcher.py -q`
Expected: FAIL，错误集中在缺少退避逻辑、最大重试和非 429 区分

- [ ] **Step 5: 提交测试骨架**

```bash
git add tests/test_openalex_fetcher.py
git commit -m "test(fetchers): cover openalex rate limit retry behavior"
```

### Task 2: OpenAlex 抓取器实现

**Files:**
- Modify: `src/paper_crawler/fetchers/openalex.py`
- Test: `tests/test_openalex_fetcher.py`

- [ ] **Step 1: 实现最小代码，让请求参数限制为 100 并增加 429 重试**

```python
def _request_with_retry(...):
    for attempt in range(max_attempts):
        response = session.get(...)
        try:
            response.raise_for_status()
            return response
        except requests.HTTPError as exc:
            if response.status_code != 429:
                raise
            wait_seconds = self._resolve_retry_delay(response, attempt)
            self.sleep_func(wait_seconds)
```

- [ ] **Step 2: 添加限流日志与 `Retry-After` / `X-RateLimit-*` 解析**

```python
logger.warning(
    "OpenAlex rate limited for filter=%s, attempt=%s/%s, retry_after=%s, remaining=%s, waiting=%ss",
    filter_fragment,
    attempt + 1,
    self.max_retry_attempts,
    retry_after,
    remaining,
    wait_seconds,
)
```

- [ ] **Step 3: 运行 OpenAlex 测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_openalex_fetcher.py -q`
Expected: PASS

- [ ] **Step 4: 运行相关回归，确保主流程未受影响**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline.py tests/test_main.py tests/test_openalex_fetcher.py -q`
Expected: PASS

- [ ] **Step 5: 提交实现**

```bash
git add src/paper_crawler/fetchers/openalex.py tests/test_openalex_fetcher.py
git commit -m "fix(fetchers): harden openalex rate limit handling"
```

### Task 3: 最终验证与收尾

**Files:**
- Modify: `docs/superpowers/plans/2026-06-04-openalex-rate-limit-hardening-v2.md`

- [ ] **Step 1: 运行全量测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests -q`
Expected: PASS

- [ ] **Step 2: 检查最近修改文件诊断**

Run: 使用编辑器诊断检查 `src/paper_crawler/fetchers/openalex.py` 和 `tests/test_openalex_fetcher.py`
Expected: 无新增诊断错误

- [ ] **Step 3: 更新计划勾选状态并记录结果**

```markdown
- [x] Step 1 ...
- [x] Step 2 ...
```

- [ ] **Step 4: 提交计划勾选收尾**

```bash
git add docs/superpowers/plans/2026-06-04-openalex-rate-limit-hardening-v2.md
git commit -m "docs: mark openalex hardening plan complete"
```
