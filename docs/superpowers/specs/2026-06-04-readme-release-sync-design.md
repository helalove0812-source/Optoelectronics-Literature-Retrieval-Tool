# README 与当前发布状态对齐设计

## 1. 目标

把仓库根目录 `README.md` 从“项目规划/未完成”状态更新为“当前真实可运行状态”，并与当前本地待提交的一批功能改动一起发布到 GitHub。

本次目标包括：

- README 反映当前已实现能力
- README 补充实际配置方式与运行命令
- README 明确多 topic / 多订阅人 / 邮件推送 / Tavily 空跑兜底
- README 明确当前运行注意事项
- README 与当前本地代码改动一起提交并推送

本次不包括：

- 重构 README 以外的产品文档体系
- 新增 Web UI、截图、演示视频
- 改动核心业务逻辑以“适配 README”

## 2. 现状问题

当前 `README.md` 仍停留在早期规划阶段，存在以下不一致：

- 仍写着“项目代码骨架尚未完成”
- 仍写着“抓取实现、推送层实现未完成”
- 未体现当前已经支持的课题组共享订阅模型
- 未体现 `Tavily` 空跑兜底
- 未体现当前真实运行命令和 `.env` 配置方式

这会导致 GitHub 读者对仓库成熟度产生明显误判。

## 3. 更新策略

本次采用“README 与当前代码状态同步更新”的方式，而不是只做最小修补。

README 将按以下结构更新：

1. 项目简介
2. 当前能力
3. 系统流程
4. 配置文件说明
5. 环境变量说明
6. 运行命令
7. 关键行为说明
8. 当前注意事项
9. 项目目录与测试状态

## 4. README 应体现的当前能力

README 需要明确以下已经可用的能力：

- `arXiv + Crossref + OpenAlex` 三源抓取
- `Unpaywall` 开放获取增强
- `Tavily` 空跑兜底
- 多 topic 配置
- 多订阅人配置
- topic 公共池 + 订阅人二次过滤
- SQLite 落库
- `push_log` 去重推送
- SMTP 邮件发送
- 可选中文总结

## 5. 关键配置说明

README 需要明确区分以下配置来源：

- `config/config.yaml`
  - 运行时参数
  - SMTP
  - LLM
  - Tavily 兜底开关
- `config/topics.yaml`
  - topic 公共抓取范围
  - topic 公共关键词
- `config/subscriptions.yaml`
  - 订阅人邮箱
  - 所属 topic
  - 个人关键词
- 根目录 `.env`
  - `SMTP_PASSWORD`
  - `DEEPSEEK_API_KEY`
  - `TAVILY_API_KEY`

## 6. 关键行为说明

README 需要明确写清以下行为：

- `Tavily` 只在某个 topic 三源空跑时触发
- 订阅人 `keywords` 为空时，视为订阅该 topic 的全部命中文献
- 最终发信数量看的是 `to_push`，而不是 `matched`
- `push_log` 以 `paper_id + topic_id + subscriber_email` 去重

## 7. 验证与发布

在更新 README 后，需要：

- 运行当前相关测试，确保 README 所描述行为与代码一致
- 检查工作区状态，确认 README 与本地功能改动一起纳入提交
- 生成一条能概括本轮功能的提交信息
- 推送到 `origin/main`

## 8. 交付标准

本次交付完成时，应满足：

- GitHub 上的 README 与当前代码真实能力一致
- 用户能按照 README 中的说明完成配置与运行
- README 不再把仓库描述为“仅有骨架、尚未实现”
- 本地这批功能改动与 README 一起完成提交和推送
