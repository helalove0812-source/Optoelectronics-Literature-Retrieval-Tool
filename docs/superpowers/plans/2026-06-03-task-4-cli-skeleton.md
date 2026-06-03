# Task 4 CLI Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `paper_crawler` 补齐最小可运行 CLI 闭环，使 `run --config config` 能加载配置、执行空管道并输出完成信息。

**Architecture:** 采用最小分层入口：`cli.py` 负责参数解析和退出码，`main.py` 负责装配配置与管道，`processing/pipeline.py` 提供空实现结果对象，`logging_utils.py` 负责统一日志初始化。测试通过子进程调用模块入口，验证真实命令行行为而不是直接调用内部函数。

**Tech Stack:** Python 3.11、argparse、logging、dataclasses、pytest、subprocess

---

### Task 1: 先写失败测试并确认不存在 CLI

**Files:**
- Create: `tests/test_cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: 写失败测试**

```python
import os
import subprocess
import sys
from pathlib import Path


def test_cli_run_command_succeeds():
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "paper_crawler.cli",
            "run",
            "--config",
            str(root / "config"),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
        env=env,
    )

    assert result.returncode == 0
    assert "Pipeline finished" in result.stdout
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src python -m pytest tests/test_cli.py -q`
Expected: FAIL because `paper_crawler.cli` does not exist

### Task 2: 写最小 CLI 闭环实现

**Files:**
- Create: `src/paper_crawler/logging_utils.py`
- Create: `src/paper_crawler/processing/__init__.py`
- Create: `src/paper_crawler/processing/pipeline.py`
- Create: `src/paper_crawler/main.py`
- Create: `src/paper_crawler/cli.py`

- [ ] **Step 1: 写日志初始化**

```python
import logging


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
```

- [ ] **Step 2: 写空管道与导出**

```python
from dataclasses import dataclass

from paper_crawler.settings import Settings


@dataclass(slots=True)
class PipelineResult:
    fetched_count: int
    matched_count: int


def run_pipeline(settings: Settings) -> PipelineResult:
    _ = settings
    return PipelineResult(fetched_count=0, matched_count=0)
```

```python
from paper_crawler.processing.pipeline import PipelineResult, run_pipeline

__all__ = ["PipelineResult", "run_pipeline"]
```

- [ ] **Step 3: 写应用编排**

```python
from pathlib import Path

from paper_crawler.processing import run_pipeline
from paper_crawler.settings import load_settings


def run_application(config_dir: Path) -> str:
    settings = load_settings(config_dir)
    result = run_pipeline(settings)
    return (
        f"Pipeline finished: fetched={result.fetched_count}, "
        f"matched={result.matched_count}"
    )
```

- [ ] **Step 4: 写命令行入口**

```python
import argparse
from pathlib import Path

from paper_crawler.logging_utils import configure_logging
from paper_crawler.main import run_application


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper-crawler")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--config", default="config")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging()

    if args.command == "run":
        print(run_application(Path(args.config)))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

### Task 3: 验证通过并手动运行

**Files:**
- Test: `tests/test_cli.py`

- [ ] **Step 1: 运行测试确认通过**

Run: `PYTHONPATH=src python -m pytest tests/test_cli.py -q`
Expected:

```text
1 passed
```

- [ ] **Step 2: 手动验证 CLI**

Run: `PYTHONPATH=src python -m paper_crawler.cli run --config config`
Expected:

```text
Pipeline finished: fetched=0, matched=0
```
