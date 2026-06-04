# 光电子文献自动抓取系统

一个基于 Python 的论文追踪与邮件分发工具，面向课题组或个人研究者，按 `topic -> subscriber` 的方式抓取近 24 小时新增论文、筛选命中结果、补充开放获取信息，并通过 SMTP 发送摘要邮件。

## 当前已实现的能力

- 支持多 topic 配置，每个 topic 可独立定义：
  - arXiv 分类
  - OpenAlex 检索过滤词
  - 关键词组
  - 同义词
  - Crossref 期刊白名单
- 支持多订阅人配置，不同订阅人可以订阅不同 topic。
- 支持三源抓取：
  - arXiv
  - Crossref
  - OpenAlex
- 支持基于关键词组和同义词的命中筛选。
- 当三大主数据源本次都没有返回任何记录时，可启用 Tavily 作为“空跑兜底”补充抓取。
- 对命中的非 arXiv 且带 DOI 的记录，调用 Unpaywall 补充开放获取状态、合法落地页和 PDF 链接。
- 使用 SQLite 持久化论文和推送日志，避免同一篇论文对同一 topic / 同一订阅人重复推送。
- 使用 SMTP 发送每位订阅人的独立邮件摘要。
- 可选接入 DeepSeek 生成中文摘要后写入邮件内容。

## 当前流程

```text
加载 config/ 与 .env
  -> 按 topic 运行抓取流水线
  -> arXiv / Crossref / OpenAlex 抓取
  -> 若三源均为空且已启用，则触发 Tavily 兜底
  -> 关键词 + 同义词匹配
  -> Unpaywall 增强开放获取信息
  -> SQLite 入库
  -> 按订阅人过滤未推送结果
  -> SMTP 发送邮件
  -> 写入 push_log
```

## 目录说明

```text
config/   配置文件
docs/     设计文档与实现记录
sql/      SQLite 初始化 schema
src/      主程序代码
tests/    自动化测试
```

## 安装

推荐使用 Python 3.11。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 运行命令

根目录下的 `.env` 会被自动加载，然后读取 `config/` 目录中的 YAML 配置：

```bash
PYTHONPATH=src .venv/bin/python -m paper_crawler.cli run --config config
```

成功运行后会输出类似摘要：

```text
Pipeline finished: fetched=12, matched=4, to_push=3, email_sent=yes
```

## 配置说明

### 1. `config/config.yaml`

主运行配置，当前包含：

- `contact_email`：请求 Crossref / OpenAlex / Unpaywall 时使用的联系邮箱。
- `database_url`：SQLite 连接串，格式必须是 `sqlite:///...`。
- `smtp`：SMTP 服务器信息。
- `llm`：DeepSeek 中文摘要配置。
- `runtime.lookback_hours`：抓取时间窗口，默认按最近若干小时。
- `runtime.enable_tavily_fallback`：是否启用 Tavily 空跑兜底。
- `runtime.tavily_max_results`：Tavily 最多返回结果数。
- `sources.arxiv_categories`、`sources.openalex_filters`：默认抓取源配置。

说明：

- 实际按 topic 运行时，`topics.yaml` 中的 topic 配置会覆盖同类源配置。
- `smtp.to_address` 目前会被订阅人邮箱覆盖，真实收件人来自 `subscriptions.yaml`。

### 2. `config/topics.yaml`

定义多个 topic。每个 topic 当前支持：

- `topic_id`
- `name`
- `arxiv_categories`
- `openalex_filters`
- `keyword_groups`
- `synonyms`
- `issn_whitelist`

这是“共享主题层”配置，决定某个 topic 的抓取范围和匹配规则。

### 3. `config/subscriptions.yaml`

定义订阅人列表。每个订阅人当前支持：

- `name`
- `email`
- `topic_id`
- `keywords`

说明：

- `topic_id` 必须能在 `topics.yaml` 中找到，否则程序会报错。
- `keywords` 为空时，表示订阅该 topic 下的全部命中结果。
- `keywords` 不为空时，会在 topic 命中结果里再次按订阅人关键词做一层过滤。

### 4. `config/keywords.yaml`

定义默认关键词组。结构为：

```yaml
硅光:
  - silicon photonics
光通信:
  - optical communication
```

### 5. `config/synonyms.yaml`

定义关键词扩展词或缩写映射，例如：

```yaml
silicon photonics:
  - SiPh
  - 硅光
```

### 6. `config/issn_whitelist.yaml`

定义 Crossref 期刊白名单，例如：

```yaml
Optics Express:
  issn: "1094-4087"
  oa: true
```

其中 `oa` 会作为该期刊默认开放获取状态的初始值，后续仍可能被 Unpaywall 结果更新。

### 7. `.env`

根目录 `.env` 会自动加载，当前至少可能用到：

```env
SMTP_PASSWORD=...
DEEPSEEK_API_KEY=...
TAVILY_API_KEY=...
```

可参考 `.env.example`。

## 数据源与增强逻辑

### 三源抓取

- arXiv：按分类抓取近时段预印本。
- Crossref：按 ISSN 白名单抓取近时段新索引记录。
- OpenAlex：按过滤词抓取近时段新增 works。

### Tavily 空跑兜底

- 只有当 arXiv、Crossref、OpenAlex 本次都没有返回任何记录时才会触发。
- 只有 `runtime.enable_tavily_fallback: true` 且环境变量中存在 `TAVILY_API_KEY` 时才会真正执行。
- Tavily 结果主要用于避免完全空跑，不替代主数据源。

### Unpaywall 增强

- 只处理“已命中关键词”的记录。
- 只处理“非 arXiv 且带 DOI”的记录。
- 用于补充：
  - `access`
  - `landing_url`
  - `pdf_url`

## 邮件与去重

- 程序会为每个订阅人单独生成邮件。
- 同一篇论文可以发送给不同订阅人。
- 但对相同 `paper_id + topic_id + subscriber_email`，只会推送一次。
- 如果某订阅人本次没有可推送结果，则不会发送空邮件。

## 注意事项

- `database_url` 目前只支持 SQLite，不支持 PostgreSQL。
- `database_url: sqlite:///相对路径` 会相对当前工作目录创建数据库文件。
- `.env` 只负责补充密钥和密码，YAML 仍是主配置来源。
- 若启用了 LLM 中文摘要但未提供 `DEEPSEEK_API_KEY`，程序会跳过中文摘要生成，不会阻断主流程。
- 若启用了 Tavily 兜底但未提供 `TAVILY_API_KEY`，程序会记录警告并跳过 Tavily。
- 当前实际生效的是“关键词 + 同义词匹配”；`semantic_matcher` 代码仍是占位实现，不应视为已上线能力。
- SMTP 端口为 `465` 时走 `SMTP_SSL`；其他端口在 `use_tls: true` 时走 `STARTTLS`。
- 程序会把论文元数据和推送日志写入 SQLite，但不会下载和保存论文 PDF 文件本体。

## 验证建议

- 先检查 `topics.yaml` 和 `subscriptions.yaml` 中的 `topic_id` 是否一一对应。
- 先用测试 SMTP 账号和测试收件箱跑一遍，确认邮件链路正常。
- 首次运行后检查数据库中是否生成了 `papers` 与 `push_log` 数据。
- 连续运行两次，确认相同订阅人不会收到重复推送。
- 临时关闭主数据源返回值或使用测试桩，验证 Tavily 空跑兜底只在三源都为空时触发。

## 相关文档

- 执行方案：`optoelectronics_paper_crawler_execution_plan.md`
- 设计文档：`docs/superpowers/specs/2026-06-03-optoelectronics-paper-crawler-design.md`
