# 光电子方向文献自动抓取系统 —— 执行方案

> 本文档用于交付给开发执行人。目标是让执行人无需额外背景，即可按本方案完成系统的搭建、测试与上线。
> 文档约定：标记为 **【必须遵守】** 的条目为合规与稳定性红线，不得省略或变通。

---

## 1. 项目目标与范围

### 1.1 目标
搭建一个自动化系统，根据用户配置的光电子领域关键词，每日自动抓取**过去 24 小时内**新发表（或新收录）的相关论文，输出标题、作者、摘要、发表时间、DOI、合法下载链接，并以列表 + 邮件形式推送给用户。

### 1.2 范围
- **包含**：预印本（arXiv）+ 正式期刊论文（通过 Crossref / OpenAlex 元数据）+ 开放获取 PDF 链接检测（Unpaywall）。
- **不包含**：直接爬取出版商网页 HTML、破解付费墙、下载论文正文文件本身（系统只提供链接，不存储 PDF）。

### 1.3 核心原则 **【必须遵守】**
1. **API 优先**：一律使用官方 / 开放 API，禁止爬取出版商网站 HTML 页面。
2. **开放获取优先**：付费论文只提供 DOI 落地页链接，禁止接入任何破解下载源（如 Sci-Hub）。
3. **遵守速率限制**：每个数据源严格遵守其配额与频率限制，所有请求带上联系邮箱标识。

---

## 2. 最终交付物清单

执行人需交付以下内容：

| 编号 | 交付物 | 说明 |
|------|--------|------|
| D1 | 可运行源代码 | 含完整目录结构与依赖文件 |
| D2 | 配置文件模板 | 关键词、ISSN 白名单、API key、推送设置 |
| D3 | 数据库与建表脚本 | SQLite（MVP）或 PostgreSQL（生产） |
| D4 | 部署说明文档 | 环境依赖、启动方式、定时任务配置 |
| D5 | 一次完整运行的样例输出 | 证明端到端跑通 |

---

## 3. 系统架构

```
[配置层] keywords.yaml / issn_whitelist.yaml / config.yaml
            │
[调度层] 每日定时触发（cron / APScheduler）
            │
[采集层] 三路并行 Fetcher
   ├─ arXiv Fetcher（光电相关分类）
   ├─ Crossref Fetcher（ISSN 白名单）
   └─ OpenAlex Fetcher（主题补充）
            │
[处理层] 时间过滤(24h) → 去重 → 关键词/语义匹配 → 元数据归一化
            │
[增强层] Unpaywall 检测开放获取 PDF 链接
            │
[存储层] 数据库（papers / push_log）
            │
[输出层] 结果列表导出 + 邮件推送
```

---

## 4. 技术选型（已锁定，执行人请勿擅改）

| 类别 | 选型 |
|------|------|
| 语言 | Python 3.10+ |
| HTTP 请求 | `requests`（同步即可，MVP 无需异步） |
| Atom 解析 | `feedparser`（arXiv 返回 Atom 格式） |
| 数据库 | MVP 用 SQLite；生产用 PostgreSQL |
| 关键词匹配 | MVP 用同义词扩展 + 关键词匹配；增强阶段加 `sentence-transformers` 语义匹配 |
| 定时调度 | MVP 用系统 cron；生产可用 APScheduler |
| 邮件推送 | `smtplib` + SMTP，或第三方邮件 API |
| 配置格式 | YAML |

---

## 5. 数据源接入规范（核心，务必精确实现）

### 5.1 arXiv（预印本，免费无需 key）

- **接口**：`http://export.arxiv.org/api/query`
- **订阅分类**：`physics.optics`、`cond-mat.mes-hall`、`physics.app-ph`、`quant-ph`（按需）、`eess.SP`（按需）
- **查询示例**（按提交时间倒序，便于取最新）：
  ```
  http://export.arxiv.org/api/query?search_query=cat:physics.optics&start=0&max_results=100&sortBy=submittedDate&sortOrder=descending
  ```
- **返回格式**：Atom XML，用 `feedparser` 解析。
- **时间字段**：取条目的 `published`（提交时间），转 UTC 后做 24 小时过滤。
- **速率** **【必须遵守】**：请求间隔 ≥ 3 秒，单次 `max_results` ≤ 100，必要时翻页。

### 5.2 Crossref + ISSN 白名单（正式期刊，免费无需 key，本系统核心）

- **接口**：`https://api.crossref.org/works`
- **关键查询参数**：
  - `filter=issn:<期刊ISSN>,from-index-date:<YYYY-MM-DD>`（`from-index-date` 表示按收录时间过滤，最能反映"刚出现"）
  - `rows=100`
  - `mailto=<你的联系邮箱>` **【必须遵守】**（进入 Crossref 礼貌池，获得更高配额）
- **查询示例**：
  ```
  https://api.crossref.org/works?filter=issn:1094-4087,from-index-date:2026-06-01&rows=100&mailto=team@example.com
  ```
- **实现要求**：对白名单中每个 ISSN 逐一查询；提取 `title`、`author`、`DOI`、`published`/`indexed`、`abstract`（若有）、`URL`（落地页）。
- **速率** **【必须遵守】**：礼貌池下建议 ≤ 50 请求/秒，但本系统每日仅几十次查询，按每次间隔 1 秒处理即可。

#### ISSN 白名单（初始值，已核实部分，执行人需补全其余）

| 期刊 | ISSN | 开放获取 |
|------|------|----------|
| Optics Express | 1094-4087 | 全 OA |
| Optics Letters | 0146-9592 | 混合 |
| Photonics Research | 2327-9125 | 全 OA |
| Optical Materials Express | 2159-3930 | 全 OA |
| Current Optics and Photonics | 2508-7266 | 全 OA |

**待补全期刊**（执行人用官网或 Crossref 查准 ISSN 后填入 `issn_whitelist.yaml`）：Optica、Advanced Photonics、Light: Science & Applications、Nature Photonics、eLight、Laser & Photonics Reviews、ACS Photonics、APL Photonics、Applied Physics Letters、IEEE Photonics Technology Letters、Journal of Lightwave Technology、IEEE JSTQE、Opto-Electronic Advances、Opto-Electronic Science、PhotoniX。

### 5.3 OpenAlex（主题补充，免费无需 key）

- **接口**：`https://api.openalex.org/works`
- **关键参数**：
  - `filter=from_created_date:<YYYY-MM-DD>,concepts.id:<光电相关概念ID>` 或 `topics.id:<主题ID>`
  - `per-page=100`
  - `mailto=<联系邮箱>` **【必须遵守】**
- **作用**：兜底抓取不在 ISSN 白名单、但主题高度相关的论文。
- **实现要求**：执行人需先在 OpenAlex 查到 "Optoelectronics" / "Photonics" 对应的 concept/topic ID，写入配置。

### 5.4 Unpaywall（开放获取链接检测，免费，需邮箱）

- **接口**：`https://api.unpaywall.org/v2/<DOI>?email=<联系邮箱>` **【必须遵守】**（email 为必填）
- **逻辑**：
  - 若返回 `is_oa = true`，取 `best_oa_location.url_for_pdf` 作为免费下载链接。
  - 否则只输出 DOI 落地页链接，并标注 `需订阅`。
- **注意**：arXiv 与全 OA 期刊（Optics Express 等）已直接有免费 PDF，可跳过 Unpaywall 查询以节省调用。

---

## 6. 模块拆解与任务清单

每个任务给出验收标准，执行人按编号顺序完成。

| 任务 | 内容 | 验收标准 |
|------|------|----------|
| T1 | 搭建项目骨架与配置加载 | 能正确读取 `config.yaml`、`keywords.yaml`、`issn_whitelist.yaml` |
| T2 | 实现 arXiv Fetcher | 输入分类列表，输出标准化论文记录，含 24h 时间过滤 |
| T3 | 实现 Crossref Fetcher | 遍历 ISSN 白名单，输出标准化记录，正确使用 `from-index-date` 与 `mailto` |
| T4 | 实现 OpenAlex Fetcher | 按主题 + 日期拉取，输出标准化记录 |
| T5 | 实现元数据归一化 | 三源输出统一为同一数据结构（见 §7 字段） |
| T6 | 实现去重模块 | 以 DOI 为主键去重；无 DOI 时用「标题归一化 + 第一作者」指纹 |
| T7 | 实现关键词/同义词匹配 | 支持同义词与缩写扩展（见 §8），过滤出相关论文 |
| T8 | 实现 Unpaywall 增强 | 正确填充下载链接与「需订阅」标记 |
| T9 | 实现存储层 | 写入数据库，避免重复推送 |
| T10 | 实现输出层 | 导出结果列表 + 发送邮件摘要 |
| T11 | 接入定时调度 | 每日定时自动运行，记录运行日志 |
| T12 | 端到端联调 + 样例输出 | 跑通完整流程并产出 D5 |

---

## 7. 数据结构与数据库设计

### 7.1 论文标准化字段（三源统一）

| 字段 | 类型 | 说明 |
|------|------|------|
| `paper_id` | string | 主键，优先用 DOI，无则用指纹 |
| `title` | string | 标题 |
| `authors` | list | 作者列表 |
| `abstract` | text | 摘要（可能为空） |
| `doi` | string | DOI（可能为空） |
| `source` | string | 来源：arxiv / crossref / openalex |
| `published_at` | datetime | UTC 发表/收录时间 |
| `landing_url` | string | 出版商落地页 |
| `pdf_url` | string | 开放获取 PDF 链接（可能为空） |
| `access` | string | open / subscription |
| `matched_keywords` | list | 命中的关键词 |

### 7.2 数据表

- **`papers`**：存储上述字段，`paper_id` 唯一索引。
- **`push_log`**：记录已推送的 `paper_id` 与推送时间，避免重复推送。

---

## 8. 关键词与匹配规则（光电子专属）

### 8.1 关键词配置（`keywords.yaml`）
支持按子方向分组，每组可配多个关键词，例如：硅基光电子、光通信、量子光源、光伏、显示、超表面等。

### 8.2 同义词 / 缩写扩展 **【重要】**
光电子术语缩写多、中英混用，匹配时必须做同义词扩展。执行人需维护一份词表，示例：
- 光电探测器 / photodetector / PD
- 垂直腔面发射激光器 / VCSEL
- 超表面 / metasurface；超透镜 / metalens
- 硅光 / silicon photonics / SiPh
- 钙钛矿 / perovskite

### 8.3 匹配方式
- **MVP**：标题 + 摘要做同义词扩展后的关键词匹配。
- **增强阶段**：用句向量模型计算用户关键词与论文摘要的语义相似度，按余弦相似度排序并设阈值过滤：

\[ \text{sim}(\vec{q}, \vec{d}) = \frac{\vec{q}\cdot\vec{d}}{\lVert\vec{q}\rVert\,\lVert\vec{d}\rVert} \]

阈值建议初始设为 0.5，上线后根据召回/准确率实际调参。

---

## 9. 调度策略

- **频率**：每日定时运行一次（建议每天上午固定时间），抓取过去 24 小时。
- **增量游标**：每次运行记录时间游标，下次从游标之后增量拉取，防止重复与遗漏。
- **预印本可选加频**：arXiv 可独立设为每 6 小时一次。

---

## 10. 测试与验收标准

| 项 | 验收标准 |
|----|----------|
| 时间过滤 | 输出论文的 `published_at` 全部落在运行时刻前 24 小时内 |
| 去重 | 同一 DOI 在结果中只出现一次 |
| 链接有效性 | 抽查 10 条，`landing_url` 可正常打开；OA 论文 `pdf_url` 可下载 |
| 合规 | 代码中无任何出版商 HTML 爬取、无破解下载源；所有 API 请求带 `mailto`/`email` |
| 推送去重 | 同一论文不会在两天内被重复推送 |
| 端到端 | 完整运行一次并产出样例输出（D5） |

---

## 11. 部署与运维

- **运行环境**：Linux 主机 / Docker 容器 / 定时云函数均可。
- **依赖**：`requirements.txt` 锁定版本。
- **定时**：cron 表达式或 APScheduler，记录每次运行日志（开始时间、各源抓取数量、最终推送数量、异常）。
- **监控**：单源失败不应中断整体流程；连续失败需在日志中告警。
- **密钥管理**：API key、SMTP 密码通过环境变量或独立配置文件注入，**不得硬编码进源码**。

---

## 12. 风险与应对

| 风险 | 应对 |
|------|------|
| 各源时间字段语义不一致 | 统一转 UTC；arXiv 用提交时间，Crossref 用 `from-index-date` |
| 元数据缺失（无摘要 / 无 DOI） | 去重指纹兜底；摘要缺失时仅用标题匹配 |
| 关键词召回率偏低 | 维护同义词表；增强阶段引入语义匹配 |
| API 限流 / 临时不可用 | 加重试与退避；单源失败不阻断其他源 |
| 误接入违规下载源 | 代码评审时核对 §1.3 红线 |

---

## 13. 实施阶段建议

- **阶段一（MVP）**：T1–T12，仅接入 arXiv + Crossref（ISSN 白名单）+ OpenAlex + Unpaywall，关键词 + 同义词匹配，结果存 SQLite 并邮件推送。**全部免费、无需任何付费 key 即可上线。**
- **阶段二（增强）**：加入语义匹配、子方向分组推送、PostgreSQL、Web 查看界面。
- **阶段三（可选）**：如有机构订阅，接入 IEEE Xplore / SPIE / Springer / Elsevier 官方 API。

---

*执行人如对任一数据源接口细节有疑问，应以该数据源官方文档为准，并优先满足 §1.3 与所有【必须遵守】条目。*
