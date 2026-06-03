# 光电子文献自动抓取系统设计文档

## 1. 目标与范围

本设计基于 `optoelectronics_paper_crawler_execution_plan.md` 落地实现一个分层模块化单体系统，用于每日抓取过去 24 小时内新发表或新收录的光电子方向论文，并完成筛选、去重、存储与推送。

本轮实现范围包含：

- `arXiv`、`Crossref`、`OpenAlex` 三个数据源接入。
- `Unpaywall` 开放获取检测。
- SQLite 存储与去重推送控制。
- `SMTP` 邮件摘要推送。
- 关键词同义词匹配与语义匹配增强。
- cron 友好的命令行入口与运行日志。

不包含：

- 出版商 HTML 爬取。
- 付费墙绕过或 PDF 文件存储。
- Web 管理界面。

## 2. 架构选择

采用“分层模块化单体”架构，而非插件化重抽象或脚本式串联。

选择理由：

- 目录清晰，适合当前从零搭建。
- 各模块边界稳定，后续可平滑替换单个实现。
- 保持实现成本可控，同时为增强项预留接口。

## 3. 目录设计

```text
paper_crawler/
  README.md
  requirements.txt
  .env.example
  config/
    config.yaml
    keywords.yaml
    issn_whitelist.yaml
    synonyms.yaml
  sql/
    schema.sql
  samples/
    sample_run_report.md
  src/
    paper_crawler/
      __init__.py
      main.py
      cli.py
      settings.py
      logging_utils.py
      models.py
      utils/
        time_utils.py
        text_utils.py
        fingerprint.py
      fetchers/
        base.py
        arxiv.py
        crossref.py
        openalex.py
        unpaywall.py
      matchers/
        keyword_matcher.py
        semantic_matcher.py
      processing/
        normalize.py
        deduplicate.py
        pipeline.py
      storage/
        database.py
        repositories.py
      notify/
        email_renderer.py
        smtp_sender.py
      scheduler/
        cron_notes.md
  tests/
    test_time_utils.py
    test_fingerprint.py
    test_keyword_matcher.py
    test_deduplicate.py
    test_normalizers.py
```

## 4. 核心模块

### 4.1 配置层

`settings.py` 负责加载 YAML 配置与环境变量：

- `config.yaml`：联系邮箱、SMTP、速率限制、语义匹配阈值、运行窗口。
- `keywords.yaml`：用户按方向维护的关键词组。
- `issn_whitelist.yaml`：期刊名称、ISSN、OA 信息。
- `synonyms.yaml`：术语同义词与缩写词表。

敏感信息只从环境变量读取，例如 `SMTP_PASSWORD`，源码内不落密钥。

### 4.2 数据采集层

每个 fetcher 仅负责“请求 + 解析 + 产出源记录”，不处理跨源逻辑。

- `ArxivFetcher`：按分类串行抓取，强制每次请求间隔至少 3 秒。
- `CrossrefFetcher`：逐个 ISSN 查询，统一带 `mailto`，按 `from-index-date` 拉取。
- `OpenAlexFetcher`：按配置的 `concept/topic` 查询补充记录。
- `UnpaywallClient`：只对需要补充 OA 信息的 DOI 查询。

每个 fetcher 输出“源记录”后交给归一化模块，不直接写数据库。

### 4.3 归一化与处理层

处理链路固定为：

1. 拉取源记录。
2. 归一化为统一 `PaperRecord`。
3. 24 小时窗口过滤。
4. DOI / 指纹去重。
5. 关键词匹配。
6. 语义匹配重排序与阈值过滤。
7. OA 链接补全。
8. 存储与推送去重控制。

设计要点：

- 归一化层负责字段对齐与时间统一为 UTC。
- 去重优先用 DOI；缺失 DOI 时用“标题归一化 + 第一作者”生成稳定指纹。
- 匹配层先做快速关键词筛选，再按需启用语义相似度，避免全部文档跑 embedding。

### 4.4 匹配层

关键词匹配分两步：

- 同义词扩展：把用户词与同义词表展开为一组匹配词。
- 文本匹配：在标题与摘要上做大小写无关匹配，并记录命中的原始关键词。

语义匹配设计：

- 使用 `sentence-transformers` 的轻量模型作为可选增强能力。
- 为关键词组生成查询向量，为论文“标题 + 摘要”生成文档向量。
- 只对通过关键词初筛或命中弱相关规则的论文做语义打分。
- 使用配置阈值，默认 `0.5`。

这样可在增强召回的同时控制 CPU 消耗与依赖复杂度。

### 4.5 存储层

MVP 使用 SQLite，表结构如下：

- `papers`：保存标准化论文记录，`paper_id` 唯一。
- `push_log`：记录某次推送包含的 `paper_id`、推送时间、通道与运行批次。
- `runs`：记录一次运行的开始时间、结束时间、各源抓取数量、异常摘要。

仓储层提供：

- 插入或忽略论文。
- 查询未推送论文。
- 记录推送完成状态。
- 记录运行游标与统计信息。

### 4.6 输出与推送层

输出层同时生成两种结果：

- 终端 / 文件 Markdown 运行摘要。
- SMTP 邮件正文。

邮件内容按“关键词组 -> 论文列表”组织，每条包含：

- 标题
- 作者
- 来源
- 时间
- DOI
- 摘要节选
- 落地页链接
- PDF 链接或“需订阅”

### 4.7 调度与入口

系统主入口为 CLI，例如：

```bash
python -m paper_crawler.cli run --config config/config.yaml
```

入口负责：

- 初始化日志和数据库。
- 触发完整处理管道。
- 输出运行结果。
- 返回非零退出码以便 cron 监控失败。

首版默认使用系统 cron；项目文档中给出 crontab 示例。调度不内嵌复杂常驻服务。

## 5. 数据模型

统一数据模型 `PaperRecord` 字段如下：

- `paper_id`
- `title`
- `authors`
- `abstract`
- `doi`
- `source`
- `published_at`
- `landing_url`
- `pdf_url`
- `access`
- `matched_keywords`
- `semantic_score`

说明：

- `paper_id` 优先使用规范化 DOI，否则使用指纹。
- `published_at` 一律为带时区的 UTC 时间。
- `semantic_score` 可为空，仅增强阶段填充。

## 6. 关键流程

### 6.1 一次完整运行

```text
加载配置
  -> 拉取 arXiv / Crossref / OpenAlex
  -> 归一化
  -> 时间过滤
  -> 去重
  -> 关键词匹配
  -> 语义评分
  -> Unpaywall 增强
  -> 写入 papers
  -> 过滤未推送记录
  -> 生成 Markdown 与邮件
  -> 发送 SMTP
  -> 写入 push_log / runs
```

### 6.2 错误处理

- 单一数据源失败时记录错误并继续处理其他数据源。
- 网络请求采用有限重试和指数退避。
- SMTP 发送失败时保留结果文件，不写成功推送日志。
- 语义模型不可用时降级为纯关键词匹配，并在日志中显式标注。

## 7. 合规约束

必须在代码设计中固化以下约束：

- 只调用开放 API，不实现出版商页面抓取。
- 只返回合法落地页与 OA 链接，不下载 PDF。
- 所有相关请求必须附带 `mailto` 或 `email`。
- 对 `arXiv` 和 `Crossref` 按方案限制请求速率。

## 8. 测试策略

测试聚焦核心正确性，不覆盖外部 API 真请求：

- `time_utils`：24 小时窗口计算和 UTC 转换。
- `fingerprint`：无 DOI 情况下的稳定指纹。
- `keyword_matcher`：同义词扩展与命中结果。
- `deduplicate`：DOI 与指纹双重去重。
- `normalizers`：三源字段归一化。

外部 API 使用 fixture 或 mock 响应验证解析逻辑，避免测试依赖公网。

## 9. 分阶段实施

推荐实现顺序：

1. 项目骨架、配置加载、数据库脚本。
2. 统一模型与工具函数。
3. `arXiv` / `Crossref` / `OpenAlex` fetcher。
4. 归一化、时间过滤、去重。
5. 关键词匹配。
6. SQLite 存储与推送去重。
7. `Unpaywall` 增强。
8. `SMTP` 邮件输出。
9. 语义匹配增强。
10. CLI、样例输出与部署文档。

## 10. 已知取舍

- 首版用同步 `requests`，优先稳定与简单，不做异步化。
- 首版调度依赖 cron，不引入 APScheduler 常驻进程。
- 语义匹配做成可开关能力，确保资源不足时可退回纯关键词模式。
- SQLite 作为默认存储，后续通过仓储层切换 PostgreSQL。
