# Unpaywall 增强设计文档

## 1. 目标

本设计为现有文献抓取主流程补上 `Unpaywall` 开放获取增强能力，使系统能够在完成抓取与关键词匹配后，对需要的论文查询合法开放获取状态，并回写 `pdf_url` 与 `access`。

本轮实现目标仅包含：

- 对“关键词命中且存在 DOI”的论文调用 `Unpaywall`
- 跳过 `arXiv` 与已知全 OA 期刊，减少不必要调用
- 将 `Unpaywall` 返回的开放获取状态回写到 `PaperRecord`
- 保持查询失败不阻断主流程

本轮不包含：

- 批量回填历史数据库中的旧记录
- 邮件模板中的 OA 展示优化
- 更复杂的出版商来源识别
- 与语义匹配的联动优化

## 2. 设计选择

采用“仅增强命中论文”的最小增量方案，而不是对所有 DOI 论文统一查询。

具体规则如下：

- 只有 `matched_keywords` 非空的论文，才进入 `Unpaywall` 增强步骤
- 只有 `doi` 非空的论文，才允许发起查询
- `source == "arxiv"` 的记录直接跳过
- 已知全 OA 期刊的记录直接跳过

选择该方案的原因：

- 与后续“筛选后推送相关论文”的目标一致
- 可以显著减少 API 调用量
- 更容易保持主流程稳定，不会为当前不准备展示的论文增加额外查询成本

## 3. 主流程位置

`Unpaywall` 增强位于当前 `pipeline` 中关键词匹配之后、数据库入库之前。

执行顺序为：

1. 多源抓取得到 `PaperRecord`
2. 关键词匹配并填充 `matched_keywords`
3. 筛出需要做 OA 增强的论文
4. 使用 `Unpaywall` 查询 DOI
5. 回写 `pdf_url` 与 `access`
6. 再统一写入数据库

这样做的理由是：

- 先做关键词匹配，可以只查询真正相关的论文
- 在入库前完成回写，数据库落地即为增强后的最终状态
- 不需要额外增加二次更新 SQL

## 4. 模块边界

### 4.1 `fetchers/unpaywall.py`

负责纯查询和响应解析，不做主流程判断。

建议提供：

- `lookup(doi: str) -> dict[str, object]`
  - 调用 `https://api.unpaywall.org/v2/<DOI>?email=<联系邮箱>`
  - 返回标准化后的查询结果

返回结果最少需要包含：

- `is_oa`
- `pdf_url`
- `landing_url`

查询失败时：

- 抛出异常，由 `pipeline` 负责降级处理

### 4.2 `processing/pipeline.py`

负责：

- 判断是否需要对某条论文调用 `Unpaywall`
- 在查询成功后回写 `PaperRecord`
- 在查询失败时记录 warning 并继续

`pipeline` 不负责解析原始 JSON，只使用 `UnpaywallClient.lookup()` 的标准化返回。

### 4.3 `models.py`

保持现有字段不变：

- `pdf_url`
- `access`
- `landing_url`

本轮不新增 `oa_source` 或 `oa_checked_at` 之类字段，避免超出 MVP 范围。

## 5. 查询与回写规则

### 5.1 调用条件

只有同时满足以下条件的论文才会查询：

- `matched_keywords` 非空
- `doi` 非空
- `source != "arxiv"`
- 不是已知全 OA 期刊

### 5.2 跳过规则

MVP 阶段采用保守跳过规则：

- `arXiv` 论文跳过，因为本身已经有合法 PDF
- 如果记录来自已知全 OA 期刊，则跳过

当前“已知全 OA 期刊”判断可基于配置：

- `issn_whitelist.yaml` 中配置 `oa: true`

MVP 阶段允许用现有来源上下文进行最小判断，不要求构建完整“期刊名称 -> 论文记录”映射器。若某条记录无法可靠判断是否为全 OA 期刊，则允许继续查询 `Unpaywall`，优先保证正确性而不是极限省调用。

### 5.3 回写规则

当 `Unpaywall` 返回：

- `is_oa = true`
  - 若 `best_oa_location.url_for_pdf` 存在，则写入 `record.pdf_url`
  - `record.access = "open"`
  - 若有更合适的 `landing_url`，可用 `Unpaywall` 返回值回写
- `is_oa = false`
  - `record.access = "subscription"`
  - 保留已有 `landing_url`
  - `record.pdf_url` 保持为空

查询失败时：

- 记录 warning
- 不中断主流程
- 论文保持原始 `pdf_url` / `access` 值

## 6. 标准化返回结构

`UnpaywallClient.lookup()` 建议输出如下结构：

```python
{
    "is_oa": True,
    "pdf_url": "https://example.com/paper.pdf",
    "landing_url": "https://doi.org/10.xxxx/abcd",
}
```

说明：

- `pdf_url` 对应 `best_oa_location.url_for_pdf`
- `landing_url` 优先取 `best_oa_location.url`，没有则取论文原有 `landing_url`
- 只返回主流程实际需要的最小字段，不把整份原始响应透传到 `pipeline`

## 7. 失败与容错

`Unpaywall` 增强必须满足以下容错原则：

- 单条 DOI 查询失败，不影响其他论文
- `Unpaywall` 整体不可用，不影响抓取与入库
- 任何查询异常都不应让 `pipeline` 返回失败

这与当前 `arXiv`、`Crossref`、`OpenAlex` 的“单源失败不阻断整体流程”原则保持一致。

## 8. 测试策略

测试分两层：

### 8.1 `UnpaywallClient` 单元测试

覆盖以下行为：

- 解析 `is_oa = true` 且包含 `url_for_pdf`
- 解析 `is_oa = false`
- 请求参数正确带上 `email`

### 8.2 `pipeline` 集成测试

覆盖以下行为：

- 仅对“命中 + 有 DOI”的论文调用 `Unpaywall`
- `arXiv` 记录不会调用
- 无 DOI 记录不会调用
- 未命中关键词的记录不会调用
- 查询成功时会回写 `access` 与 `pdf_url`
- 查询失败时流程仍返回成功统计并完成入库

## 9. 实施范围控制

本轮明确延后以下内容：

- 对所有论文统一补全 OA 状态
- 批量更新历史入库数据
- 识别混合 OA 期刊的更精细规则
- 将 `Unpaywall` 响应做详细缓存
- 发送邮件时按 OA / 订阅做不同展示模板

本设计的交付标准是：系统在抓取并筛选出相关论文后，能够为需要的 DOI 合法补充 OA 链接，并正确写回 `pdf_url` 与 `access`，同时不破坏现有主流程稳定性。
