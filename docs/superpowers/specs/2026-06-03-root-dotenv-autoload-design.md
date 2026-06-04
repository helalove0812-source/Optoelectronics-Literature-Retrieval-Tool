# 项目根目录 .env 自动加载设计文档

## 1. 目标

本设计用于让程序在启动时自动加载项目根目录下的 `.env` 文件，使本地运行时可以直接从 `.env` 读取敏感环境变量，而无需每次手动执行 `source .env`。

本轮目标仅包含：

- 在 CLI 启动早期自动加载项目根目录 `.env`
- 支持从 `.env` 中读取 `SMTP_PASSWORD`
- 支持从 `.env` 中读取 `DEEPSEEK_API_KEY`
- 保持 `.env` 不上传到 GitHub
- 更新 `.env.example`，补充当前实际需要的变量

本轮不包含：

- 自定义 `.env` 路径参数
- 多层 `.env` 文件加载
- 覆盖 `config.yaml` 配置结构
- 运行时热重载环境变量

## 2. 设计选择

本轮采用“固定加载项目根目录 `.env`”的方案，而不是新增 `--env-file` 或复杂的多路径搜索。

原因如下：

- 当前需求明确，只需要本地开发和真实试跑时方便读取密钥
- 固定加载根目录 `.env` 的认知成本最低，使用方式最简单
- 不增加 CLI 参数，避免扩大改动范围

实现方式上，优先采用成熟库 `python-dotenv` 来完成加载，而不是自写解析器。

原因如下：

- 能正确处理常见 `.env` 格式
- 改动小，维护成本低
- 比手写 `KEY=VALUE` 解析更稳妥

## 3. 加载时机与位置

`.env` 的加载位置固定为仓库根目录：

- `/Users/helap/Documents/Project/文献抓取/.env`

加载时机应放在 CLI 启动最早阶段，即在 [cli.py](file:///Users/helap/Documents/Project/文献抓取/src/paper_crawler/cli.py#L16-L23) 中解析参数并进入主流程之前完成。

推荐顺序：

1. 启动 CLI
2. 加载项目根目录 `.env`
3. 配置日志
4. 调用 `run_application(...)`

这样可以确保：

- `SMTP_PASSWORD` 在邮件发送前可用
- `DEEPSEEK_API_KEY` 在构建 DeepSeek 客户端前可用
- 现有 `main.py` 中基于 `os.getenv(...)` 的逻辑无需改动

如果项目根目录不存在 `.env` 文件：

- 不报错
- 程序继续运行
- 保持现有行为不变

## 4. 变量覆盖规则

本轮采用“不覆盖已存在系统环境变量”的规则。

具体语义：

- 若 shell 中已经存在某个环境变量，则保留原值
- 若 shell 中不存在，则从 `.env` 中补充加载

例如：

- 终端已执行 `export SMTP_PASSWORD=abc`
- `.env` 中也存在 `SMTP_PASSWORD=xyz`

则最终程序使用 `abc`。

这样做的好处是：

- 符合常见开发习惯
- 允许临时在 shell 中覆盖本地 `.env`
- 避免误把旧 `.env` 值覆盖掉当前会话中的显式设置

## 5. 依赖与文件变更

本轮预计涉及以下文件：

- [requirements.txt](file:///Users/helap/Documents/Project/文献抓取/requirements.txt)
  - 增加 `python-dotenv`
- [cli.py](file:///Users/helap/Documents/Project/文献抓取/src/paper_crawler/cli.py)
  - 增加启动时自动加载根目录 `.env` 的逻辑
- [.env.example](file:///Users/helap/Documents/Project/文献抓取/.env.example)
  - 补充 `DEEPSEEK_API_KEY`
  - 与当前 SMTP/LLM 实际使用变量保持一致

现有 [.gitignore](file:///Users/helap/Documents/Project/文献抓取/.gitignore#L11) 已包含 `.env`，因此本轮无需新增忽略规则。

## 6. 错误处理与边界

本轮容错策略保持简单：

- `.env` 文件不存在：静默跳过
- `.env` 存在但缺少某些键：不报错，由后续业务逻辑自行处理
- 若 `SMTP_PASSWORD` 缺失：
  - 发送邮件时沿用当前失败行为
- 若 `DEEPSEEK_API_KEY` 缺失：
  - 沿用当前告警并跳过中文总结客户端初始化

也就是说，本轮只负责“自动把 `.env` 读进来”，不改变业务层对缺失变量的处理语义。

## 7. 测试策略

至少补充以下测试：

### 7.1 CLI 自动加载测试

覆盖以下行为：

- 项目根目录存在 `.env` 时，会在启动早期加载
- 已存在的系统环境变量不会被覆盖

### 7.2 缺失 `.env` 的兼容测试

覆盖以下行为：

- 根目录没有 `.env` 时，CLI 仍可正常进入主流程

### 7.3 示例文件检查

覆盖以下行为：

- `.env.example` 包含 `DEEPSEEK_API_KEY`
- 示例字段名与当前代码实际读取的环境变量一致

## 8. 交付后的使用方式

交付后，用户的本地使用流程变为：

1. 在项目根目录创建 `.env`
2. 写入例如：
   - `SMTP_PASSWORD=...`
   - `DEEPSEEK_API_KEY=...`
3. 直接运行：
   - `PYTHONPATH=src .venv/bin/python -m paper_crawler.cli run --config config`

不再需要手动执行：

- `source .env`
- `export SMTP_PASSWORD=...`
- `export DEEPSEEK_API_KEY=...`

## 9. 实施范围控制

本轮明确延后：

- `--env-file <path>` 参数
- `.env.local` / `.env.prod` 之类的分层环境文件
- 将 YAML 配置项也映射到环境变量
- 更复杂的环境变量校验器

本设计的交付标准是：程序启动时会自动尝试加载项目根目录 `.env`，且不会覆盖已存在的系统环境变量；`SMTP_PASSWORD` 和 `DEEPSEEK_API_KEY` 可直接通过 `.env` 提供，无需手动 `source`。
