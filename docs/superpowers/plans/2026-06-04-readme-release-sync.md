# README 与当前发布状态对齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把仓库根目录 `README.md` 更新为当前真实可运行状态，并与当前这批本地功能改动一起验证、提交并推送到 GitHub。

**Architecture:** README 只描述已经存在于当前代码中的能力，不为了文档去补新功能。先更新文档内容，再用现有测试与实际运行命令验证文档所述能力，最后把 README 与当前本地改动打成一批提交并推送。

**Tech Stack:** Markdown, Git, Python 3.11, pytest

---

### Task 1: 重写 README 为当前真实状态

**Files:**
- Modify: `README.md`
- Reference: `config/config.yaml`
- Reference: `config/topics.yaml`
- Reference: `config/subscriptions.yaml`
- Reference: `src/paper_crawler/cli.py`

- [ ] **Step 1: 把 README 头部简介改为当前系统定位**

```markdown
# 课题组文献抓取与推送工具

一个面向课题组共享使用场景的论文抓取与邮件推送工具。系统按 topic 维护公共抓取池，再按订阅人做二次过滤、去重和邮件分发。

当前已支持：

- `arXiv + Crossref + OpenAlex` 三源抓取
- `Unpaywall` 开放获取增强
- `Tavily` 空跑兜底
- 多 topic / 多订阅人配置
- SQLite 落库与 `push_log` 去重
- SMTP 邮件发送
- 可选中文总结
```

- [ ] **Step 2: 重写“配置说明”章节，区分 YAML 与 `.env`**

```markdown
## 配置说明

### `config/config.yaml`
- 数据库地址
- SMTP 基础配置
- LLM 配置
- 运行时开关，例如 `enable_tavily_fallback`

### `config/topics.yaml`
- 每个 topic 的公共抓取范围
- topic 公共关键词与同义词

### `config/subscriptions.yaml`
- 订阅人邮箱
- 所属 topic
- 个人关键词

### 根目录 `.env`
- `SMTP_PASSWORD`
- `DEEPSEEK_API_KEY`
- `TAVILY_API_KEY`
```

- [ ] **Step 3: 写入真实运行命令、关键行为与注意事项**

```markdown
## 运行

```bash
PYTHONPATH=src .venv/bin/python -m paper_crawler.cli run --config config
```

## 关键行为

- `Tavily` 只在某个 topic 三源空跑时触发
- 订阅人 `keywords` 为空时，表示接收该 topic 的全部命中文献
- 最终是否发信看 `to_push`，不是 `matched`
- `push_log` 按 `paper_id + topic_id + subscriber_email` 去重

## 注意事项

- `OpenAlex` 免费配额下可能出现 `429`
- `arXiv` 偶发超时或上游错误时，会由其他源与 Tavily 兜底
- 测试与运行命令需要使用项目 `.venv`
```

- [ ] **Step 4: 自检 README，不要再保留“代码骨架未完成”等过时描述**

Run: 人工检查 `README.md`
Expected: README 不再出现“尚未完成抓取实现/推送层实现/项目骨架未完成”等过时表述

- [ ] **Step 5: 提交 README 改动**

```bash
git add README.md
git commit -m "docs: refresh readme for current release state"
```

### Task 2: 验证 README 所描述行为与代码一致

**Files:**
- Modify: `README.md`（仅在验证发现描述不准确时）
- Reference: `src/paper_crawler/main.py`
- Reference: `src/paper_crawler/processing/pipeline.py`
- Reference: `src/paper_crawler/fetchers/tavily.py`

- [ ] **Step 1: 跑当前相关测试**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_main.py tests/test_settings.py tests/test_pipeline.py tests/test_tavily_fetcher.py tests/test_openalex_fetcher.py -q`
Expected: PASS

- [ ] **Step 2: 跑一次真实程序入口，确认 README 的运行命令正确**

Run: `PYTHONPATH=src .venv/bin/python -m paper_crawler.cli run --config config`
Expected: 命令能正常执行并输出 `Pipeline finished: fetched=..., matched=..., to_push=..., email_sent=...`

- [ ] **Step 3: 如果运行结果与 README 文案有偏差，只修 README，不改业务代码**

```markdown
- 把“总会发邮件”改为“仅当 `to_push > 0` 时发邮件”
- 把“Tavily 固定执行”改为“仅空跑触发”
```

- [ ] **Step 4: 检查 README 诊断**

Run: 使用编辑器诊断检查 `README.md`
Expected: 无新增 diagnostics

- [ ] **Step 5: 如有 README 修订，提交文档修正**

```bash
git add README.md
git commit -m "docs: align readme wording with runtime behavior"
```

### Task 3: 与当前功能改动一起发布

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `config/config.yaml`
- Modify: `config/subscriptions.yaml`
- Modify: `config/topics.yaml`
- Modify: `src/paper_crawler/fetchers/openalex.py`
- Modify: `src/paper_crawler/main.py`
- Modify: `src/paper_crawler/processing/pipeline.py`
- Modify: `src/paper_crawler/settings.py`
- Modify: `tests/test_main.py`
- Modify: `tests/test_openalex_fetcher.py`
- Modify: `tests/test_pipeline.py`
- Modify: `tests/test_settings.py`
- Create: `src/paper_crawler/fetchers/tavily.py`
- Create: `tests/test_tavily_fetcher.py`
- Create: `docs/superpowers/plans/2026-06-04-empty-subscriber-keywords.md`
- Create: `docs/superpowers/plans/2026-06-04-openalex-rate-limit-hardening-v2.md`
- Create: `docs/superpowers/plans/2026-06-04-tavily-empty-run-fallback.md`
- Create: `docs/superpowers/specs/2026-06-04-readme-release-sync-design.md`

- [ ] **Step 1: 复核工作区，确认提交范围就是当前这批功能改动与 README**

Run: `git status --short`
Expected: 仅包含 README、本轮 Tavily/OpenAlex/空关键词语义/配置改动及对应计划文档

- [ ] **Step 2: 跑全量测试，作为发布前最终验证**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests -q`
Expected: PASS

- [ ] **Step 3: 生成一条覆盖本轮功能的提交**

```bash
git add README.md .env.example config/config.yaml config/subscriptions.yaml config/topics.yaml src/paper_crawler/fetchers/openalex.py src/paper_crawler/fetchers/tavily.py src/paper_crawler/main.py src/paper_crawler/processing/pipeline.py src/paper_crawler/settings.py tests/test_main.py tests/test_openalex_fetcher.py tests/test_pipeline.py tests/test_settings.py tests/test_tavily_fetcher.py docs/superpowers/plans/2026-06-04-empty-subscriber-keywords.md docs/superpowers/plans/2026-06-04-openalex-rate-limit-hardening-v2.md docs/superpowers/plans/2026-06-04-tavily-empty-run-fallback.md docs/superpowers/specs/2026-06-04-readme-release-sync-design.md docs/superpowers/plans/2026-06-04-readme-release-sync.md
git commit -m "feat: add tavily fallback and refresh project docs"
```

- [ ] **Step 4: 推送到 GitHub**

```bash
git push origin main
```

- [ ] **Step 5: 记录最终结果**

```text
- 提交哈希
- 推送分支
- 全量测试结果
- README 重点更新项
```
