# DeepSeek 中文总结入库设计文档

## 1. 目标

本设计在现有“抓取 -> 匹配 -> OA 增强 -> 入库 -> 邮件推送”主链路上，增加一个面向邮件场景的中文总结能力。

目标是让系统在发送邮件前，仅对“本次最终要推送的命中文献”调用 DeepSeek，生成 2-3 句中文总结，并将该总结写回数据库，供邮件正文优先使用。

本轮实现目标仅包含：

- 只对最终待推送论文调用 DeepSeek
- 为每篇论文生成 2-3 句中文总结
- 将中文总结持久化到 `papers` 表
- 邮件正文使用中文总结替代英文摘要
- 当 DeepSeek 调用失败时，回退为原英文摘要发送邮件

本轮不包含：

- 中文标题翻译
- 批量摘要合并或全局日报总结
- 对所有抓取论文做中文总结
- 多模型路由或模型自动切换
- 将总结结果同步到 Web 页面

## 2. 设计选择

本轮采用“中文总结写回数据库”的方案，而不是只在邮件发送前临时生成。

具体原因：

- 已生成的总结可以复用，避免同一论文重复消耗模型调用
- 后续若增加结果导出、网页查看或人工复核，数据库中已有可直接使用的中文内容
- 邮件渲染层保持简单，只负责展示，不负责调用模型

因此本轮保持如下边界：

- `main.py` 负责编排待推送论文的总结增强
- `llm/deepseek_client.py` 只负责生成中文总结
- `models.py` 和 `repositories.py` 负责承载和持久化 `zh_summary`
- `email_renderer.py` 只负责优先渲染 `zh_summary`

## 3. 数据模型与数据库变更

### 3.1 `PaperRecord`

在 [PaperRecord](file:///Users/helap/Documents/Project/文献抓取/src/paper_crawler/models.py#L5-L18) 中新增字段：

- `zh_summary: str | None = None`

语义约定：

- 有值：该论文已经生成过中文总结
- 为空：尚未生成，或生成失败

### 3.2 `papers` 表

在 [schema.sql](file:///Users/helap/Documents/Project/文献抓取/sql/schema.sql#L1-L14) 的 `papers` 表中新增列：

- `zh_summary TEXT`

MVP 阶段采用最轻量方案：

- 新建数据库时直接带上该字段
- 已存在旧表时，初始化逻辑执行轻量迁移：
  - 若 `papers.zh_summary` 不存在，则执行 `ALTER TABLE papers ADD COLUMN zh_summary TEXT`

这样可以兼容现有本地 SQLite 数据库，而不要求用户删库重建。

## 4. 调用时机与数据流

本轮新增的数据流为：

1. `run_pipeline()` 完成抓取、匹配、OA 增强和入库
2. 主流程拿到 `matched_records`
3. 使用 `PushLogRepository` 过滤出 `to_push`
4. 对 `to_push` 中尚无 `zh_summary` 的论文调用 DeepSeek
5. 生成成功后，将 `zh_summary` 写回数据库
6. 邮件渲染优先显示 `zh_summary`
7. 邮件发送成功后写入 `push_log`

这样做的好处是：

- 只对真正要发送的论文做总结，成本最低
- 已写回数据库的总结可在后续复用
- 即使邮件发送失败，已生成的总结仍可保留，避免下一次重复总结

## 5. DeepSeek 客户端边界

新增模块建议为：

- `src/paper_crawler/llm/deepseek_client.py`

职责仅包含：

- 接收论文标题、摘要、命中关键词
- 构造固定提示词
- 调用 DeepSeek 接口
- 返回 2-3 句中文总结文本

不负责：

- 数据库存储
- 邮件渲染
- 推送去重
- 重试队列管理

建议使用 OpenAI 兼容接口风格，配置项至少包含：

- `enabled`
- `base_url`
- `model`
- `timeout`

API Key 必须通过环境变量注入，例如：

- `DEEPSEEK_API_KEY`

不得硬编码进源码或配置文件。

## 6. 提示词与输出约束

MVP 阶段提示词目标是生成稳定、简短、可读的中文内容。

输入内容建议包含：

- 论文标题
- 论文摘要
- 命中关键词组

输出要求：

- 使用简体中文
- 长度控制在 2-3 句
- 尽量说明研究对象、方法或核心结果
- 不杜撰原文未提及的实验指标
- 不输出 Markdown 列表、编号或额外说明

如果模型返回空字符串、明显无效内容或接口异常，视为生成失败。

## 7. 回退与容错策略

本轮采用“单篇失败、整体继续”的策略。

具体规则：

- 若某篇论文中文总结生成失败：
  - 记录 warning
  - 不影响其他论文继续总结
  - 不影响整封邮件继续发送
- 若某篇论文没有 `zh_summary`：
  - 邮件中回退显示英文摘要
- 若 DeepSeek 整体不可用：
  - 整体邮件仍照常发送
  - 仅失去中文总结增强

这满足你的偏好：**回退为原样发送**。

## 8. 邮件展示规则

在 [email_renderer.py](file:///Users/helap/Documents/Project/文献抓取/src/paper_crawler/notify/email_renderer.py) 中，将当前 `Abstract` 段落替换为更明确的摘要展示规则：

- 若 `record.zh_summary` 存在：
  - 显示 `中文总结: ...`
- 否则：
  - 显示 `Abstract: ...`

其他字段保留：

- 标题
- 作者
- 来源
- 发布时间
- DOI
- 命中关键词
- Access
- Landing URL
- PDF URL

这样邮件会明显比当前短，同时仍保留必要的原始元数据。

## 9. 仓储层变更

在 [repositories.py](file:///Users/helap/Documents/Project/文献抓取/src/paper_crawler/storage/repositories.py#L16-L53) 中需要扩展两类能力：

- 插入论文时写入 `zh_summary`
- 提供按 `paper_id` 更新 `zh_summary` 的方法

推荐增加类似接口：

- `update_zh_summary(paper_id: str, zh_summary: str) -> None`

MVP 阶段不要求复杂批量更新，只要逐条更新即可。

## 10. 配置需求

在现有 [settings.py](file:///Users/helap/Documents/Project/文献抓取/src/paper_crawler/settings.py#L8-L66) 基础上，新增一组 LLM 配置，例如：

- `llm.enabled`
- `llm.provider`
- `llm.base_url`
- `llm.model`
- `llm.timeout_seconds`

推荐默认行为：

- 默认关闭，只有显式启用时才调用 DeepSeek
- 若关闭，则邮件继续使用英文摘要

这保证即使未配置 API Key，系统也能正常运行。

## 11. 主流程编排

在 [main.py](file:///Users/helap/Documents/Project/文献抓取/src/paper_crawler/main.py#L20-L69) 中新增总结增强步骤。

建议顺序为：

1. 运行 `pipeline`
2. 过滤出 `to_push`
3. 若 `llm.enabled = true`：
   - 对 `to_push` 中 `zh_summary` 为空的论文逐条调用 DeepSeek
   - 成功后立即写回数据库
4. 调用 `email_renderer`
5. 发送邮件
6. 成功后写入 `push_log`

这样可确保：

- 邮件使用的是数据库中已保存的最新总结
- 失败不会影响已完成入库
- 下次再次发送同一论文时无需重复总结

## 12. 测试策略

测试分四层：

### 12.1 DeepSeek 客户端单元测试

覆盖以下行为：

- 成功返回中文总结
- 返回空内容视为失败
- HTTP 异常时抛出或返回失败信号

### 12.2 仓储层测试

覆盖以下行为：

- `papers` 表可写入 `zh_summary`
- `update_zh_summary()` 可正确更新既有论文
- 旧数据库执行迁移后具备 `zh_summary` 列

### 12.3 邮件渲染测试

覆盖以下行为：

- 有 `zh_summary` 时优先显示中文总结
- 无 `zh_summary` 时回退显示英文摘要
- 其他元数据字段保持存在

### 12.4 主流程集成测试

覆盖以下行为：

- 只对 `to_push` 论文调用总结客户端
- 已有 `zh_summary` 的论文不会重复调用
- 单篇总结失败不影响其他论文和邮件发送
- 总结成功后会持久化到数据库

## 13. 实施范围控制

本轮明确延后：

- 中文标题翻译
- 批量缓存和批量推理接口
- 邮件中按主题自动分组
- 多段式长摘要压缩
- 数据库历史论文补全总结任务

本设计的交付标准是：系统在邮件发送前，仅对最终待推送论文生成并持久化中文总结，邮件优先展示该中文总结；当模型调用失败时，系统仍能回退为原英文摘要并正常发送邮件。
