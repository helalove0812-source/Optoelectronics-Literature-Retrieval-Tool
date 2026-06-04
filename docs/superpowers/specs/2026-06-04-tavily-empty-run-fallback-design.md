# Tavily 空跑兜底设计文档

## 1. 目标

本设计用于在现有 `arXiv + Crossref + OpenAlex` 三源抓取链路基础上，增加一个“仅在方向池空跑时触发”的 Tavily 搜索兜底能力。

本轮目标仅包含：

- 每个 `topic` 继续固定运行 `arXiv + Crossref + OpenAlex`
- 若某个 `topic` 在三源执行后 `fetched=0`，则额外触发一次 Tavily 搜索
- Tavily 每个 `topic` 每轮最多只调用一次
- Tavily 查询词基于 `topic` 公共关键词构造，而不是按订阅人逐个搜索
- Tavily 结果进入现有匹配、去重、入库和邮件推送链路
- Tavily API Key 通过项目根目录 `.env` 注入

本轮不包含：

- 每个订阅人独立调用 Tavily
- Tavily 作为常规第四源每轮固定执行
- 网页正文抓取或全文抽取
- 复杂 DOI 清洗流水线
- 通过多个身份或多个出口去规避第三方免费配额

## 2. 设计选择

本轮采用“空跑才触发 Tavily”的节省额度方案，而不是把 Tavily 当成常规源。

原因如下：

- 你当前最关心的是“整轮 `fetched=0` 时还能不能补救”
- Tavily 按调用计费/限额，比学术源更适合作为稀疏兜底
- 当前系统已经具备三源主链路，只需要在“完全没抓到结果”的时刻补一个低频搜索入口
- 课题组共享版会随着 `topic` 数增加，如果 Tavily 每轮都跑，额度消耗会很快

因此本轮保持如下边界：

- 三源主链路不变
- Tavily 只在 `topic` 级空跑时调用
- Tavily 只返回最小字段，后续仍依赖现有关键词匹配和邮件链路

## 3. 触发条件

每个 `topic` 的执行顺序保持为：

1. `arXiv`
2. `Crossref`
3. `OpenAlex`
4. 合并结果
5. 若合并后 `records` 数量大于 `0`：
   - 不触发 Tavily
6. 若合并后 `records` 数量等于 `0`：
   - 触发一次 Tavily 搜索兜底

这意味着：

- Tavily 不参与常规成功路径
- Tavily 只在“该方向池本轮完全空跑”时出手
- 多个 `topic` 可分别独立判断是否需要兜底

## 4. 查询词策略

为了节省额度，Tavily 查询词不按订阅人逐个构造，而是按 `topic` 公共关键词构造。

建议策略：

- 从该 `topic` 的公共 `keyword_groups` 中提取前若干个核心关键词
- 只选较短、较通用、偏英文的词
- 追加学术搜索限定词：
  - `paper`
  - `preprint`
  - `doi`
  - `arxiv`

示例：

- 光方向：
  - `integrated photonics optical sensing optical computing paper arxiv doi`
- 机器人方向：
  - `motion planning embodied ai vla paper arxiv doi`

MVP 阶段建议：

- 每个 `topic` 最多取 `3~4` 个核心词
- 查询词长度保持紧凑，避免无关网页结果过多

## 5. Tavily 结果模型

新增一个 `TavilyFetcher`，建议路径：

- `src/paper_crawler/fetchers/tavily.py`

它的职责仅包含：

- 接收 `topic` 查询词
- 调用 Tavily 搜索 API
- 把结果映射为现有 `PaperRecord`

MVP 阶段只抽取最小字段：

- `title`
- `landing_url`
- `abstract` 或 snippet
- `doi`（若能从结果中识别）
- `paper_id`
- `source="tavily"`

字段处理约定：

- 若能识别 DOI，则优先使用 DOI 作为 `paper_id`
- 若不能识别 DOI，则使用标题生成指纹
- `pdf_url` 默认置空
- `access` 默认标记为 `subscription`
- `published_at` 若 Tavily 返回可解析日期则使用，否则使用当前时间或结果时间字段的保守映射

## 6. 数据流

本轮新增的数据流如下：

1. 主流程按 `topic` 运行现有三源
2. 合并三源结果
3. 若三源结果为空：
   - 调用 `TavilyFetcher.fetch()`
4. 将 Tavily 结果与现有结果集合并
5. 进入当前关键词匹配逻辑
6. 入库 `papers`
7. 再按订阅人进行第二层过滤、去重和邮件发送

这样做的效果是：

- Tavily 只补“发现能力”
- 后续链路仍然复用当前系统
- 不需要为 Tavily 单独再造一套邮件逻辑

## 7. 配置与密钥

Tavily 的开关与 API Key 推荐这样处理：

### 7.1 `.env`

项目根目录 `.env` 中新增：

- `TAVILY_API_KEY`

示例：

```dotenv
SMTP_PASSWORD=your-smtp-password
DEEPSEEK_API_KEY=your-deepseek-api-key
TAVILY_API_KEY=your-tavily-api-key
```

由于当前 CLI 已自动加载项目根目录 `.env`，因此：

- 不需要手动 `source .env`
- 不需要把 Key 写进 `config.yaml`

### 7.2 运行配置

MVP 阶段可以只加最小配置，例如：

- `runtime.enable_tavily_fallback: true`
- `runtime.tavily_max_results: 5`

若未配置 `TAVILY_API_KEY` 或显式关闭 Tavily：

- 不报错
- 仅跳过 Tavily 兜底

## 8. 容错策略

本轮 Tavily 兜底需遵守以下原则：

- 只有空跑时才尝试 Tavily
- Tavily 单次失败不影响整轮流程
- Tavily 无结果时仍允许该 `topic` 本轮为空
- Tavily 不应阻断其他 `topic` 的抓取与邮件发送

具体表现为：

- 若 Tavily 调用异常：
  - 记录 warning
  - 继续执行后续 `topic`
- 若 Tavily 返回 0 结果：
  - 记录 info 或 warning
  - 不发送空邮件

## 9. 模块边界

建议保持如下职责拆分：

- `settings.py`
  - 增加 Tavily 兜底相关运行配置
- `fetchers/tavily.py`
  - 只负责调用 Tavily 并映射结果
- `processing/pipeline.py`
  - 负责在三源空跑时触发 Tavily
- `main.py`
  - 不需要感知 Tavily 细节，只消费 `PipelineResult`
- `.env.example`
  - 增加 `TAVILY_API_KEY`

## 10. 测试策略

至少补以下测试：

### 10.1 Tavily 抓取器测试

覆盖以下行为：

- 正确构造查询词
- 正确映射 Tavily 结果为 `PaperRecord`
- 无 DOI 时使用标题指纹

### 10.2 Pipeline 触发测试

覆盖以下行为：

- 三源抓到结果时不触发 Tavily
- 三源结果为空时触发 Tavily
- Tavily 结果进入匹配链路

### 10.3 容错测试

覆盖以下行为：

- Tavily Key 缺失时跳过兜底
- Tavily 请求失败不影响整个 pipeline 返回
- Tavily 返回空结果时系统仍正常结束

## 11. 实施范围控制

本轮明确延后：

- Tavily 作为常规第四源
- 按订阅人级别调用 Tavily
- 网页正文抓取
- PDF 抽取
- DOI 高级清洗与 Crossref 二次校正
- Tavily 结果二次回源验证

本设计的交付标准是：当某个 `topic` 在 `arXiv + Crossref + OpenAlex` 全部执行后仍然 `fetched=0` 时，系统可使用 Tavily 发起一次低频搜索兜底，并将结果送入现有匹配、入库、去重和邮件链路，同时通过项目根目录 `.env` 中的 `TAVILY_API_KEY` 完成安全配置。
