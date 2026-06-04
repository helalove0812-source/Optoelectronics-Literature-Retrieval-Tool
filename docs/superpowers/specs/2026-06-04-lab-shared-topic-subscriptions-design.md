# 课题组共享版方向池订阅设计文档

## 1. 目标

本设计用于将当前“个人可用的文献抓取与邮件推送工具”升级为“课题组内部共享使用”的版本。

本轮目标是支持：

- 一套系统供课题组多人共用
- 按研究方向划分多个公共抓取池
- 每个成员只订阅自己所属方向池
- 每个成员配置自己的邮箱和个人关键词
- 系统抓一次方向池公共论文，再按成员二次过滤并分别发送邮件

本轮实现目标仅包含：

- 引入方向池配置
- 引入订阅人配置
- 支持“方向池 -> 个人订阅”两层过滤
- 将推送去重从“论文级”升级为“方向池 + 订阅人 + 论文级”
- 继续保留中文总结、邮件发送和数据库持久化能力

本轮不包含：

- Web 管理后台
- Excel/CSV 导入订阅配置
- 一个订阅人订阅多个方向池
- 不同订阅人自定义发送频率
- 多通道推送（如企业微信/钉钉/Slack）

## 2. 设计选择

本轮采用“按研究方向分池 + YAML 配置订阅人”的方案。

原因如下：

- 当前代码已基于 YAML 配置组织，最容易平滑扩展
- 课题组成员主题方向未必一致，不能再共用单一的光电子公共池
- 按方向池划分后，可以在一个方向池内共享抓取成本，同时避免不同研究方向互相干扰
- 使用 YAML 管理成员订阅配置，适合课题组内部先落地，维护成本低

因此本轮保持如下边界：

- `topics.yaml` 定义方向池
- `subscriptions.yaml` 定义订阅人
- 现有抓取器仍按当前接口工作
- 主流程负责按方向池运行，再按订阅人分别发送

## 3. 核心概念

### 3.1 方向池（Topic）

方向池表示一个课题方向对应的一套公共抓取范围和第一层筛选规则。

每个方向池至少包含：

- `topic_id`
- `name`
- `arxiv_categories`
- `openalex_filters`
- `keyword_groups`
- `synonyms`
- 可选 `issn_whitelist`

方向池的职责是：

- 定义该方向抓哪些来源
- 定义该方向第一层主题匹配规则
- 产出该方向的公共候选论文池

### 3.2 订阅人（Subscription）

订阅人表示课题组中的一个实际接收成员。

每个订阅项至少包含：

- `name`
- `email`
- `topic_id`
- `keywords`

订阅人的职责是：

- 指定自己属于哪个方向池
- 在方向池公共结果上按个人关键词做第二层过滤
- 接收属于自己的个性化日报

## 4. 配置文件设计

### 4.1 `config/topics.yaml`

新增方向池配置文件：

- `config/topics.yaml`

示例：

```yaml
topics:
  - topic_id: optoelectronics
    name: 光电子
    arxiv_categories:
      - physics.optics
      - physics.app-ph
    openalex_filters:
      - photonics
    keyword_groups:
      silicon_photonics:
        - silicon photonics
        - optical interconnect
      emitter_detector:
        - vcsel
        - photodetector
    synonyms:
      vcsel:
        - vertical-cavity surface-emitting laser

  - topic_id: microelectronics
    name: 微电子
    arxiv_categories:
      - physics.app-ph
      - cond-mat.mtrl-sci
    openalex_filters:
      - semiconductor
    keyword_groups:
      chip_design:
        - cmos
        - eda
        - chiplet
      memory:
        - sram
        - dram
```

### 4.2 `config/subscriptions.yaml`

新增订阅人配置文件：

- `config/subscriptions.yaml`

示例：

```yaml
subscriptions:
  - name: 张三
    email: zhangsan@example.com
    topic_id: optoelectronics
    keywords:
      - optical interconnect
      - silicon photonics

  - name: 李四
    email: lisi@example.com
    topic_id: microelectronics
    keywords:
      - sram
      - low-power design
```

MVP 约束：

- 一个订阅人只能属于一个 `topic_id`
- 一个方向池可挂多个订阅人
- 订阅配置用 YAML 维护，不做动态管理接口

## 5. 运行流程

本轮主流程不再是“抓一次全局结果 -> 发一封全局邮件”，而是：

1. 读取 `topics.yaml`
2. 读取 `subscriptions.yaml`
3. 按 `topic_id` 分组订阅人
4. 对每个方向池单独执行：
   - 使用该方向池配置抓取公共候选论文
   - 使用该方向池规则做第一层匹配
5. 对该方向池下每个订阅人：
   - 使用个人 `keywords` 做第二层过滤
   - 查询该订阅人的推送历史
   - 若存在待推送论文，则渲染并发送专属邮件
   - 若为空，则不发空邮件

这样实现的是：

- 一个方向抓一次
- 多个成员复用同一方向池结果
- 每个人只收到属于自己的邮件

## 6. 匹配规则分层

本轮匹配拆成两层：

### 6.1 第一层：方向池匹配

由方向池自己的 `keyword_groups`、`synonyms` 和来源约束完成。

其目标是：

- 从该方向的数据源中得到一个“公共相关论文池”
- 去掉明显不属于该方向的结果

### 6.2 第二层：订阅人匹配

由订阅人的个人 `keywords` 完成。

其目标是：

- 从方向池的公共相关论文中再做个性化筛选
- 保证每个人只收到自己真正关心的子方向内容

这样做的好处是：

- 不会让每个成员都重复抓取数据
- 不会让一个方向池内所有成员收到完全相同的内容
- 与当前系统“关键词匹配”的能力兼容

## 7. 推送去重规则

现有去重是“论文级”或“论文 + channel”级，不足以支持多人共享。

本轮改为：

- `paper_id + topic_id + subscriber_email + channel`

推荐 `push_log` 至少记录：

- `paper_id`
- `topic_id`
- `subscriber_email`
- `channel`
- `pushed_at`

语义如下：

- 同一篇论文给甲发过，不代表给乙也发过
- 同一篇论文在光电子池发过，不代表在微电子池也算发过
- 同一成员对同一方向池中的同一论文只发一次

这样才能支持课题组内部多成员共享使用。

## 8. 邮件行为

邮件发送策略如下：

- 一个订阅人一次运行最多收到一封属于自己方向池的日报
- 邮件正文只包含该成员个人关键词命中的论文
- 若当次无命中，则不发空邮件
- 邮件标题建议包含订阅人名字和方向池名称，例如：
  - `Daily paper digest for 张三 - 光电子 (5)`

中文总结仍沿用当前策略：

- 仅对最终待发送的论文生成/复用中文总结
- 邮件优先展示中文总结
- 失败时回退英文摘要

## 9. 数据库与迁移

本轮至少需要调整 `push_log` 相关结构与仓储逻辑。

推荐演进方式：

- 保留现有 `papers` 表
- 迁移 `push_log`，新增：
  - `topic_id TEXT`
  - `subscriber_email TEXT`

若采用轻量迁移，初始化逻辑可：

- 检查列是否存在
- 缺失则执行 `ALTER TABLE ... ADD COLUMN ...`

仓储层需要提供新的判重接口，例如：

- `has_been_pushed(paper_id, topic_id, subscriber_email) -> bool`
- `mark_pushed(paper_id, topic_id, subscriber_email, pushed_at, channel) -> None`

## 10. 模块边界

推荐保持如下职责拆分：

- `settings.py`
  - 继续读取全局基础配置
  - 新增方向池与订阅人配置读取入口
- `processing/pipeline.py`
  - 接收某个方向池配置并产出该方向池公共结果
- `matchers/`
  - 保持方向池级匹配能力
  - 新增或复用订阅人级关键词过滤能力
- `notify/email_renderer.py`
  - 继续负责单个订阅人的邮件渲染
- `main.py`
  - 负责按方向池循环、按订阅人循环、分别发送
- `storage/repositories.py`
  - 负责方向池 + 订阅人级去重

## 11. 测试策略

至少补充以下测试：

### 11.1 配置读取测试

覆盖以下行为：

- 成功读取 `topics.yaml`
- 成功读取 `subscriptions.yaml`
- 订阅人引用不存在的 `topic_id` 时给出明确错误

### 11.2 方向池流程测试

覆盖以下行为：

- 不同方向池抓取互不影响
- 每个方向池使用自己的抓取与匹配配置

### 11.3 订阅人过滤测试

覆盖以下行为：

- 同一方向池多个成员得到不同过滤结果
- 无命中时不发空邮件

### 11.4 推送去重测试

覆盖以下行为：

- 同一篇论文对不同成员可分别发送
- 同一篇论文对同一成员不会重复发送
- 同一篇论文在不同方向池中可独立记录发送历史

### 11.5 容错测试

覆盖以下行为：

- 单个订阅人发送失败不影响其他订阅人
- 单个方向池抓取失败不影响其他方向池继续运行

## 12. 实施范围控制

本轮明确延后：

- Web 后台
- 数据库化订阅配置
- 一个订阅人挂多个方向池
- 每人不同发送频率
- 每人不同总结风格
- 前端历史论文检索页面

本设计的交付标准是：系统可按研究方向分池抓取公共论文，并按课题组成员的邮箱和个人关键词分别过滤、分别去重、分别发送邮件，使整个课题组可共享同一套系统而不互相干扰。
