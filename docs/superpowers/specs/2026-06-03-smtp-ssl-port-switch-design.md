# SMTP SSL/STARTTLS 自动切换设计文档

## 1. 目标

本设计用于解决当前 QQ 邮箱 SMTP 发送时在 `smtp.qq.com:587` 路径上可能出现的连接中断问题。

目标是在不改动主流程调用方式的前提下，让发送器根据端口自动选择合适的连接模式：

- `465` 走 SSL 直连
- 其他端口继续走普通 SMTP
- 若 `use_tls = true`，则在非 465 端口上执行 `starttls()`

本轮实现目标仅包含：

- 保持 `send_email()` 的现有函数签名不变
- 在 `465` 端口上自动切换到 `SMTP_SSL`
- 在 `587` 等非 465 端口上继续支持 `STARTTLS`
- 补充测试覆盖两种路径

本轮不包含：

- 新增 `use_ssl` 配置项
- 自动重试 SMTP 连接
- 多服务器回退
- HTML 邮件或附件能力

## 2. 设计选择

本轮采用“按端口自动分流”的方案，而不是新增一个显式的 `use_ssl` 配置字段。

原因如下：

- 对现有调用方最小侵入，不需要改 `main.py`、`settings.py` 和配置结构
- 对 QQ 邮箱场景更直接：`465` 本身就是 SSL 直连的惯例端口
- 避免出现 `port/use_tls/use_ssl` 三个开关互相矛盾的配置状态

因此本轮保持如下边界：

- `smtp_sender.py` 内部决定连接模式
- `SMTPConfig` 结构保持不变
- `config.yaml` 只需要通过端口和 `use_tls` 表达意图

## 3. 连接行为规则

发送逻辑按以下规则执行：

1. 若 `config.port == 465`
   - 使用 `smtplib.SMTP_SSL(config.host, config.port)` 建连
   - 不调用 `starttls()`
2. 若 `config.port != 465`
   - 使用 `smtplib.SMTP(config.host, config.port)` 建连
   - 若 `config.use_tls` 为 `true`，调用 `starttls()`
3. 两种路径都继续执行：
   - `login(username, password)`
   - `send_message(message)`

这样可同时兼容：

- QQ 邮箱推荐的 `465 + SSL`
- 通用服务器常见的 `587 + STARTTLS`

## 4. 配置语义

本轮不新增字段，继续沿用现有配置：

- `host`
- `port`
- `username`
- `from_address`
- `to_address`
- `use_tls`

推荐用法：

- QQ/foxmail：
  - `host: smtp.qq.com`
  - `port: 465`
  - `use_tls: true`
- 通用 STARTTLS 服务器：
  - `port: 587`
  - `use_tls: true`

在本轮语义下，`use_tls` 表示“是否在非 SSL 直连路径上尝试 TLS 升级”，而 `465` 端口会优先触发 SSL 直连。

## 5. 测试策略

至少补充两条单元测试：

### 5.1 STARTTLS 路径

覆盖以下行为：

- `587` 端口使用普通 SMTP 工厂
- 调用了 `starttls()`
- 正常 `login()` 和 `send_message()`

### 5.2 SSL 路径

覆盖以下行为：

- `465` 端口使用 SSL 工厂
- 不调用 `starttls()`
- 正常 `login()` 和 `send_message()`

## 6. 风险与范围控制

本设计只解决“连接模式与端口不匹配”的问题，不保证消除所有 SMTP 失败原因。

本轮仍不处理：

- 授权码错误
- 服务器限流
- 网络抖动重试
- 邮件内容过大导致的服务端拒绝

本设计的交付标准是：发送器在 `465` 端口下自动使用 SSL 直连，在 `587` 等端口下继续支持 STARTTLS，且现有主流程无需改动。
