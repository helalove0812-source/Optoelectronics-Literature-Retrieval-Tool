# 空订阅关键词回退到 Topic 全量命中 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 当订阅人的 `keywords` 为空时，让该订阅人接收所属 topic 的全部命中文献，而不是被过滤为 0 篇。

**Architecture:** 保持现有 topic 级匹配、订阅人级去重和邮件发送流程不变，只调整订阅人级匹配函数 `_record_matches_keywords()` 的空列表语义。通过 `tests/test_main.py` 新增一条主流程测试锁定该行为，避免影响已有非空关键词过滤逻辑。

**Tech Stack:** Python 3.11, pytest

---

### Task 1: 为空关键词语义补失败测试

**Files:**
- Modify: `tests/test_main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: 写失败测试，验证空关键词订阅人收到全部命中论文**

```python
def test_run_application_treats_empty_subscriber_keywords_as_all_topic_matches(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)
    sender = DummySender()
    subscriptions = build_lab_subscriptions(
        subscriptions=[
            SubscriptionConfig(
                name="订阅人",
                email="user@example.com",
                topic_id="optoelectronics",
                keywords=[],
            )
        ]
    )

    summary = run_application(
        tmp_path,
        settings_loader=lambda _: build_settings_for_main(db_path),
        pipeline_runner=lambda settings: build_pipeline_result(),
        email_renderer=lambda records: f"Matched papers: {len(records)}",
        email_sender=sender,
        subscriptions_loader=lambda _: subscriptions,
        smtp_password_getter=lambda: "secret",
    )

    assert "to_push=2" in summary
    assert len(sender.calls) == 1
```

- [ ] **Step 2: 运行定向测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_main.py::test_run_application_treats_empty_subscriber_keywords_as_all_topic_matches -q`
Expected: FAIL，当前 `_record_matches_keywords()` 对 `[]` 返回 `False`

- [ ] **Step 3: 提交测试骨架**

```bash
git add tests/test_main.py
git commit -m "test(main): cover empty subscriber keywords"
```

### Task 2: 实现空关键词回退行为

**Files:**
- Modify: `src/paper_crawler/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: 在 `_record_matches_keywords()` 中实现空关键词直接放行**

```python
def _record_matches_keywords(record: PaperRecord, keywords: list[str]) -> bool:
    if not keywords:
        return True

    haystack = " ".join(
        [
            record.title.lower(),
            record.abstract.lower(),
            " ".join(record.matched_keywords).lower(),
        ]
    )
    return any(keyword.lower() in haystack for keyword in keywords)
```

- [ ] **Step 2: 运行定向测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_main.py::test_run_application_treats_empty_subscriber_keywords_as_all_topic_matches -q`
Expected: PASS

- [ ] **Step 3: 跑主流程回归测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_main.py -q`
Expected: PASS

- [ ] **Step 4: 检查最近修改文件诊断**

Run: 使用编辑器诊断检查 `src/paper_crawler/main.py` 与 `tests/test_main.py`
Expected: 无新增 diagnostics

- [ ] **Step 5: 提交实现**

```bash
git add src/paper_crawler/main.py tests/test_main.py
git commit -m "feat(main): treat empty subscriber keywords as topic-wide subscription"
```
