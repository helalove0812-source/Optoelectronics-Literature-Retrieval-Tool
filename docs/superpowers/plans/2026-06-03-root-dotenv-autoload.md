# Root Dotenv Autoload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 CLI 在启动时自动加载项目根目录 `.env`，并让 `SMTP_PASSWORD`、`DEEPSEEK_API_KEY` 可直接供现有流程读取。

**Architecture:** 在 `cli.py` 启动最早阶段接入 `python-dotenv` 的 `load_dotenv()`，固定读取仓库根目录 `.env`，并使用 `override=False` 保持 shell 中已存在的环境变量优先。测试新增到独立的 `tests/test_cli.py`，覆盖“存在 .env 加载成功”“已有环境变量不被覆盖”“缺失 .env 兼容运行”三条核心路径，同时更新 `.env.example` 与依赖声明。

**Tech Stack:** Python 3.11、pytest、python-dotenv、argparse、pathlibs、monkeypatch

---

## File Map

- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `src/paper_crawler/cli.py`
- Create: `tests/test_cli.py`

### Task 1: 增加 .env 自动加载的测试与示例约束

**Files:**
- Modify: `.env.example`
- Create: `tests/test_cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: 先补 `.env.example`，把实际需要的变量列全**

把 [.env.example](file:///Users/helap/Documents/Project/文献抓取/.env.example) 改成：

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USERNAME=research-alert@example.com
SMTP_PASSWORD=change-me
SMTP_FROM=research-alert@example.com
CONTACT_EMAIL=team@example.com
DATABASE_URL=sqlite:///data/papers.db
DEEPSEEK_API_KEY=change-me
```

- [ ] **Step 2: 新建 CLI 测试文件，覆盖三条核心行为**

创建 `tests/test_cli.py`：

```python
from pathlib import Path

from paper_crawler import cli


def test_main_loads_root_dotenv_without_overriding_existing_env(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    dotenv_path = project_root / ".env"
    dotenv_path.write_text(
        "SMTP_PASSWORD=from-dotenv\nDEEPSEEK_API_KEY=dotenv-key\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "PROJECT_ROOT", project_root)
    monkeypatch.setenv("SMTP_PASSWORD", "from-shell")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(cli, "configure_logging", lambda: None)
    monkeypatch.setattr(cli, "run_application", lambda path: "ok")
    monkeypatch.setattr(
        cli.argparse.ArgumentParser,
        "parse_args",
        lambda self: type("Args", (), {"command": "run", "config": "config"})(),
    )

    assert cli.main() == 0
    assert cli.os.getenv("SMTP_PASSWORD") == "from-shell"
    assert cli.os.getenv("DEEPSEEK_API_KEY") == "dotenv-key"


def test_main_skips_missing_root_dotenv(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    called: list[Path] = []
    monkeypatch.setattr(cli, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(cli, "configure_logging", lambda: None)
    monkeypatch.setattr(cli, "run_application", lambda path: called.append(path) or "ok")
    monkeypatch.setattr(
        cli.argparse.ArgumentParser,
        "parse_args",
        lambda self: type("Args", (), {"command": "run", "config": "config"})(),
    )

    assert cli.main() == 0
    assert called == [Path("config")]


def test_env_example_contains_deepseek_api_key() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "SMTP_PASSWORD=" in env_example
    assert "DEEPSEEK_API_KEY=" in env_example
```

- [ ] **Step 3: 运行测试，确认先红灯**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_cli.py -q`

Expected:

```text
E   ModuleNotFoundError: No module named 'dotenv'
```

如果测试环境先报 `AttributeError: module 'paper_crawler.cli' has no attribute 'PROJECT_ROOT'`，也算符合预期，因为实现尚未写入。

- [ ] **Step 4: 检查红灯范围只落在本任务缺口**

Run: `git diff -- .env.example tests/test_cli.py`

Expected:

```text
只看到 .env.example 更新和 tests/test_cli.py 新增
```

### Task 2: 在 CLI 启动阶段接入根目录 `.env` 自动加载

**Files:**
- Modify: `requirements.txt`
- Modify: `src/paper_crawler/cli.py`
- Create: `tests/test_cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: 增加依赖声明**

把 [requirements.txt](file:///Users/helap/Documents/Project/文献抓取/requirements.txt) 改成：

```text
requests==2.32.3
feedparser==6.0.11
PyYAML==6.0.2
pytest==8.3.2
python-dateutil==2.9.0.post0
sentence-transformers==3.0.1
python-dotenv==1.0.1
```

- [ ] **Step 2: 在 CLI 中增加固定根目录 `.env` 加载函数**

把 [cli.py](file:///Users/helap/Documents/Project/文献抓取/src/paper_crawler/cli.py) 改成：

```python
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from paper_crawler.logging_utils import configure_logging
from paper_crawler.main import run_application

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper-crawler")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--config", default="config")
    return parser


def load_root_dotenv() -> None:
    dotenv_path = PROJECT_ROOT / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    load_root_dotenv()
    configure_logging()

    if args.command == "run":
        print(run_application(Path(args.config)))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 安装新增依赖**

Run: `.venv/bin/python -m pip install -r requirements.txt`

Expected:

```text
Successfully installed python-dotenv-1.0.1
```

- [ ] **Step 4: 运行 CLI 测试，确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_cli.py -q`

Expected:

```text
3 passed
```

- [ ] **Step 5: 运行相关回归，确认主流程不受影响**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_cli.py tests/test_main.py tests/test_smtp_sender.py -q`

Expected:

```text
11 passed
```

- [ ] **Step 6: 提交本任务**

```bash
git add requirements.txt .env.example src/paper_crawler/cli.py tests/test_cli.py
git commit -m "feat(cli): autoload root dotenv file"
```

## Self-Review

- **Spec coverage:** Task 1 覆盖 `.env.example` 更新与 CLI 行为测试；Task 2 覆盖依赖、根目录 `.env` 自动加载、`override=False` 不覆盖既有环境变量、缺失 `.env` 兼容运行。
- **Placeholder scan:** 无 `TODO`、`TBD` 或模糊语句；所有代码、命令和预期输出都已写明。
- **Type consistency:** 统一使用 `PROJECT_ROOT`、`load_root_dotenv()`、`load_dotenv(..., override=False)`，并与规格中的固定根目录 `.env` 设计保持一致。
