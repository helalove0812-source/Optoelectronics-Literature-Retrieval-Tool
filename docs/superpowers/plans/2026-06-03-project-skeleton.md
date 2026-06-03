# Project Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建一个可运行、可测试、可扩展的光电子文献自动抓取系统代码骨架，为后续接入抓取器、匹配器、存储层和推送层提供稳定基础。

**Architecture:** 采用 `src` 布局的分层模块化单体架构，先完成配置层、数据模型、CLI 入口、数据库初始化和空管道的最小闭环。首轮不接真实 API 逻辑，只保证骨架可导入、可运行、可测试。

**Tech Stack:** Python 3.10+、requests、PyYAML、pytest、SQLite、pathlib、dataclasses

---

## File Map

- Create: `requirements.txt`
- Create: `.env.example`
- Create: `config/config.yaml`
- Create: `config/keywords.yaml`
- Create: `config/issn_whitelist.yaml`
- Create: `config/synonyms.yaml`
- Create: `sql/schema.sql`
- Create: `src/paper_crawler/__init__.py`
- Create: `src/paper_crawler/cli.py`
- Create: `src/paper_crawler/main.py`
- Create: `src/paper_crawler/settings.py`
- Create: `src/paper_crawler/logging_utils.py`
- Create: `src/paper_crawler/models.py`
- Create: `src/paper_crawler/utils/__init__.py`
- Create: `src/paper_crawler/utils/time_utils.py`
- Create: `src/paper_crawler/utils/text_utils.py`
- Create: `src/paper_crawler/utils/fingerprint.py`
- Create: `src/paper_crawler/fetchers/__init__.py`
- Create: `src/paper_crawler/fetchers/base.py`
- Create: `src/paper_crawler/fetchers/arxiv.py`
- Create: `src/paper_crawler/fetchers/crossref.py`
- Create: `src/paper_crawler/fetchers/openalex.py`
- Create: `src/paper_crawler/fetchers/unpaywall.py`
- Create: `src/paper_crawler/matchers/__init__.py`
- Create: `src/paper_crawler/matchers/keyword_matcher.py`
- Create: `src/paper_crawler/matchers/semantic_matcher.py`
- Create: `src/paper_crawler/processing/__init__.py`
- Create: `src/paper_crawler/processing/normalize.py`
- Create: `src/paper_crawler/processing/deduplicate.py`
- Create: `src/paper_crawler/processing/pipeline.py`
- Create: `src/paper_crawler/storage/__init__.py`
- Create: `src/paper_crawler/storage/database.py`
- Create: `src/paper_crawler/storage/repositories.py`
- Create: `src/paper_crawler/notify/__init__.py`
- Create: `src/paper_crawler/notify/email_renderer.py`
- Create: `src/paper_crawler/notify/smtp_sender.py`
- Create: `tests/conftest.py`
- Create: `tests/test_settings.py`
- Create: `tests/test_cli.py`
- Create: `tests/test_database.py`
- Create: `tests/test_fingerprint.py`

### Task 1: 建立目录和依赖骨架

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `src/paper_crawler/__init__.py`
- Test: `tests/conftest.py`

- [ ] **Step 1: 写出依赖文件和包版本**

```text
requests==2.32.3
feedparser==6.0.11
PyYAML==6.0.2
pytest==8.3.2
python-dateutil==2.9.0.post0
sentence-transformers==3.0.1
```

- [ ] **Step 2: 创建环境变量模板**

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=research-alert@example.com
SMTP_PASSWORD=change-me
SMTP_FROM=research-alert@example.com
CONTACT_EMAIL=team@example.com
DATABASE_URL=sqlite:///data/papers.db
```

- [ ] **Step 3: 创建包入口文件**

```python
"""Optoelectronics paper crawler package."""

__all__ = ["__version__"]
__version__ = "0.1.0"
```

- [ ] **Step 4: 运行最小导入检查**

Run: `PYTHONPATH=src python -c "import paper_crawler; print(paper_crawler.__version__)"`

Expected:

```text
0.1.0
```

- [ ] **Step 5: 提交**

```bash
git add requirements.txt .env.example src/paper_crawler/__init__.py
git commit -m "build: add project dependency skeleton"
```

### Task 2: 添加 YAML 配置模板和加载器测试

**Files:**
- Create: `config/config.yaml`
- Create: `config/keywords.yaml`
- Create: `config/issn_whitelist.yaml`
- Create: `config/synonyms.yaml`
- Create: `src/paper_crawler/settings.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: 先写失败测试，验证配置可加载**

```python
from pathlib import Path

from paper_crawler.settings import load_settings


def test_load_settings_reads_all_yaml_files():
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root / "config")
    assert settings.contact_email == "team@example.com"
    assert "physics.optics" in settings.arxiv_categories
    assert "silicon photonics" in settings.keyword_groups["硅光"]
    assert settings.issn_whitelist["Optics Express"]["issn"] == "1094-4087"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src pytest tests/test_settings.py -q`

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `paper_crawler.settings`

- [ ] **Step 3: 写配置模板文件**

`config/config.yaml`

```yaml
contact_email: team@example.com
database_url: sqlite:///data/papers.db
smtp:
  host: smtp.example.com
  port: 587
  username: research-alert@example.com
  from_address: research-alert@example.com
runtime:
  lookback_hours: 24
  semantic_threshold: 0.5
  enable_semantic_matching: true
sources:
  arxiv_categories:
    - physics.optics
    - physics.app-ph
  openalex_topics:
    - photonics
```

`config/keywords.yaml`

```yaml
硅光:
  - silicon photonics
  - SiPh
光通信:
  - optical communication
  - coherent optics
超表面:
  - metasurface
  - metalens
```

`config/issn_whitelist.yaml`

```yaml
Optics Express:
  issn: "1094-4087"
  oa: true
Photonics Research:
  issn: "2327-9125"
  oa: true
```

`config/synonyms.yaml`

```yaml
photodetector:
  - PD
  - 光电探测器
VCSEL:
  - 垂直腔面发射激光器
metasurface:
  - 超表面
silicon photonics:
  - SiPh
  - 硅光
```

- [ ] **Step 4: 写最小配置加载器实现**

```python
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(slots=True)
class Settings:
    contact_email: str
    database_url: str
    arxiv_categories: list[str]
    keyword_groups: dict[str, list[str]]
    issn_whitelist: dict[str, dict[str, object]]
    synonyms: dict[str, list[str]]
    semantic_threshold: float
    enable_semantic_matching: bool


def _read_yaml(file_path: Path) -> dict:
    with file_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_settings(config_dir: Path) -> Settings:
    config = _read_yaml(config_dir / "config.yaml")
    keywords = _read_yaml(config_dir / "keywords.yaml")
    issn_whitelist = _read_yaml(config_dir / "issn_whitelist.yaml")
    synonyms = _read_yaml(config_dir / "synonyms.yaml")
    runtime = config["runtime"]
    sources = config["sources"]
    return Settings(
        contact_email=config["contact_email"],
        database_url=config["database_url"],
        arxiv_categories=sources["arxiv_categories"],
        keyword_groups=keywords,
        issn_whitelist=issn_whitelist,
        synonyms=synonyms,
        semantic_threshold=float(runtime["semantic_threshold"]),
        enable_semantic_matching=bool(runtime["enable_semantic_matching"]),
    )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `PYTHONPATH=src pytest tests/test_settings.py -q`

Expected:

```text
1 passed
```

- [ ] **Step 6: 提交**

```bash
git add config/ src/paper_crawler/settings.py tests/test_settings.py
git commit -m "feat: add configuration templates and loader"
```

### Task 3: 建立数据模型与工具函数骨架

**Files:**
- Create: `src/paper_crawler/models.py`
- Create: `src/paper_crawler/utils/time_utils.py`
- Create: `src/paper_crawler/utils/text_utils.py`
- Create: `src/paper_crawler/utils/fingerprint.py`
- Test: `tests/test_fingerprint.py`

- [ ] **Step 1: 先写失败测试，验证指纹逻辑稳定**

```python
from paper_crawler.utils.fingerprint import build_paper_fingerprint


def test_build_paper_fingerprint_is_stable():
    value = build_paper_fingerprint(
        title=" Silicon Photonics for Coherent Links ",
        authors=["Alice Smith", "Bob Chen"],
    )
    assert value == "silicon-photonics-for-coherent-links::alice-smith"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src pytest tests/test_fingerprint.py -q`

Expected: FAIL with `ModuleNotFoundError` for `paper_crawler.utils.fingerprint`

- [ ] **Step 3: 写最小工具和模型代码**

`src/paper_crawler/models.py`

```python
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class PaperRecord:
    paper_id: str
    title: str
    authors: list[str]
    abstract: str
    doi: str | None
    source: str
    published_at: datetime
    landing_url: str
    pdf_url: str | None = None
    access: str = "subscription"
    matched_keywords: list[str] = field(default_factory=list)
    semantic_score: float | None = None
```

`src/paper_crawler/utils/text_utils.py`

```python
import re


def normalize_text(value: str) -> str:
    compact = re.sub(r"\s+", " ", value.strip().lower())
    return compact


def slugify_text(value: str) -> str:
    normalized = normalize_text(value)
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
```

`src/paper_crawler/utils/fingerprint.py`

```python
from paper_crawler.utils.text_utils import slugify_text


def build_paper_fingerprint(title: str, authors: list[str]) -> str:
    first_author = authors[0] if authors else "unknown"
    return f"{slugify_text(title)}::{slugify_text(first_author)}"
```

`src/paper_crawler/utils/time_utils.py`

```python
from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    return datetime.now(UTC)


def within_lookback_window(value: datetime, hours: int) -> bool:
    return value >= utc_now() - timedelta(hours=hours)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=src pytest tests/test_fingerprint.py -q`

Expected:

```text
1 passed
```

- [ ] **Step 5: 提交**

```bash
git add src/paper_crawler/models.py src/paper_crawler/utils/ tests/test_fingerprint.py
git commit -m "feat: add core models and utility helpers"
```

### Task 4: 建立 CLI 入口与空管道闭环

**Files:**
- Create: `src/paper_crawler/logging_utils.py`
- Create: `src/paper_crawler/processing/pipeline.py`
- Create: `src/paper_crawler/main.py`
- Create: `src/paper_crawler/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: 先写失败测试，验证 CLI 能返回成功状态**

```python
import subprocess
import sys


def test_cli_run_command_succeeds():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "paper_crawler.cli",
            "run",
            "--config",
            "config",
        ],
        env={"PYTHONPATH": "src"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Pipeline finished" in result.stdout
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src pytest tests/test_cli.py -q`

Expected: FAIL because `paper_crawler.cli` does not exist

- [ ] **Step 3: 写最小 CLI 和空管道实现**

`src/paper_crawler/logging_utils.py`

```python
import logging


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
```

`src/paper_crawler/processing/pipeline.py`

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

`src/paper_crawler/main.py`

```python
from pathlib import Path

from paper_crawler.processing.pipeline import run_pipeline
from paper_crawler.settings import load_settings


def run_application(config_dir: Path) -> str:
    settings = load_settings(config_dir)
    result = run_pipeline(settings)
    return f"Pipeline finished: fetched={result.fetched_count}, matched={result.matched_count}"
```

`src/paper_crawler/cli.py`

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

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=src pytest tests/test_cli.py -q`

Expected:

```text
1 passed
```

- [ ] **Step 5: 手动运行命令行**

Run: `PYTHONPATH=src python -m paper_crawler.cli run --config config`

Expected:

```text
Pipeline finished: fetched=0, matched=0
```

- [ ] **Step 6: 提交**

```bash
git add src/paper_crawler/logging_utils.py src/paper_crawler/processing/pipeline.py src/paper_crawler/main.py src/paper_crawler/cli.py tests/test_cli.py
git commit -m "feat: add runnable CLI application skeleton"
```

### Task 5: 建立数据库初始化层

**Files:**
- Create: `sql/schema.sql`
- Create: `src/paper_crawler/storage/database.py`
- Create: `src/paper_crawler/storage/repositories.py`
- Test: `tests/test_database.py`

- [ ] **Step 1: 先写失败测试，验证 schema 能初始化数据库**

```python
from pathlib import Path

from paper_crawler.storage.database import initialize_database


def test_initialize_database_creates_tables(tmp_path: Path):
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)
    assert db_path.exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src pytest tests/test_database.py -q`

Expected: FAIL with `ModuleNotFoundError` for `paper_crawler.storage.database`

- [ ] **Step 3: 写 schema 和数据库初始化代码**

`sql/schema.sql`

```sql
CREATE TABLE IF NOT EXISTS papers (
    paper_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors_json TEXT NOT NULL,
    abstract TEXT NOT NULL,
    doi TEXT,
    source TEXT NOT NULL,
    published_at TEXT NOT NULL,
    landing_url TEXT NOT NULL,
    pdf_url TEXT,
    access TEXT NOT NULL,
    matched_keywords_json TEXT NOT NULL,
    semantic_score REAL
);

CREATE TABLE IF NOT EXISTS push_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL,
    pushed_at TEXT NOT NULL,
    channel TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    fetched_count INTEGER NOT NULL DEFAULT 0,
    matched_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL
);
```

`src/paper_crawler/storage/database.py`

```python
import sqlite3
from pathlib import Path


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path = Path(__file__).resolve().parents[3] / "sql" / "schema.sql"
    schema = schema_path.read_text(encoding="utf-8")
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(schema)
        connection.commit()
    finally:
        connection.close()
```

`src/paper_crawler/storage/repositories.py`

```python
from dataclasses import dataclass


@dataclass(slots=True)
class RunSummary:
    fetched_count: int = 0
    matched_count: int = 0
    status: str = "success"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=src pytest tests/test_database.py -q`

Expected:

```text
1 passed
```

- [ ] **Step 5: 提交**

```bash
git add sql/schema.sql src/paper_crawler/storage/ tests/test_database.py
git commit -m "feat: add database initialization skeleton"
```

### Task 6: 建立占位模块并跑通骨架测试套件

**Files:**
- Create: `src/paper_crawler/fetchers/base.py`
- Create: `src/paper_crawler/fetchers/arxiv.py`
- Create: `src/paper_crawler/fetchers/crossref.py`
- Create: `src/paper_crawler/fetchers/openalex.py`
- Create: `src/paper_crawler/fetchers/unpaywall.py`
- Create: `src/paper_crawler/matchers/keyword_matcher.py`
- Create: `src/paper_crawler/matchers/semantic_matcher.py`
- Create: `src/paper_crawler/processing/normalize.py`
- Create: `src/paper_crawler/processing/deduplicate.py`
- Create: `src/paper_crawler/notify/email_renderer.py`
- Create: `src/paper_crawler/notify/smtp_sender.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: 写 smoke test，确保骨架模块均可导入**

```python
def test_import_skeleton_modules():
    import paper_crawler.fetchers.arxiv
    import paper_crawler.fetchers.crossref
    import paper_crawler.fetchers.openalex
    import paper_crawler.fetchers.unpaywall
    import paper_crawler.matchers.keyword_matcher
    import paper_crawler.matchers.semantic_matcher
    import paper_crawler.notify.email_renderer
    import paper_crawler.notify.smtp_sender
    import paper_crawler.processing.deduplicate
    import paper_crawler.processing.normalize
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=src pytest tests/conftest.py tests/test_settings.py tests/test_cli.py tests/test_database.py tests/test_fingerprint.py -q`

Expected: FAIL because the placeholder modules do not exist yet

- [ ] **Step 3: 写占位模块，显式声明后续接口**

`src/paper_crawler/fetchers/base.py`

```python
from dataclasses import dataclass


@dataclass(slots=True)
class FetchResult:
    records: list[dict]
```

`src/paper_crawler/fetchers/arxiv.py`

```python
class ArxivFetcher:
    def fetch(self) -> list[dict]:
        return []
```

`src/paper_crawler/fetchers/crossref.py`

```python
class CrossrefFetcher:
    def fetch(self) -> list[dict]:
        return []
```

`src/paper_crawler/fetchers/openalex.py`

```python
class OpenAlexFetcher:
    def fetch(self) -> list[dict]:
        return []
```

`src/paper_crawler/fetchers/unpaywall.py`

```python
class UnpaywallClient:
    def lookup(self, doi: str) -> dict:
        _ = doi
        return {}
```

`src/paper_crawler/matchers/keyword_matcher.py`

```python
def match_keywords(title: str, abstract: str, keyword_groups: dict[str, list[str]]) -> list[str]:
    _ = (title, abstract, keyword_groups)
    return []
```

`src/paper_crawler/matchers/semantic_matcher.py`

```python
def score_semantic_similarity(query: str, document: str) -> float:
    _ = (query, document)
    return 0.0
```

`src/paper_crawler/processing/normalize.py`

```python
def normalize_record(source: str, payload: dict) -> dict:
    return {"source": source, "payload": payload}
```

`src/paper_crawler/processing/deduplicate.py`

```python
def deduplicate_records(records: list[dict]) -> list[dict]:
    return records
```

`src/paper_crawler/notify/email_renderer.py`

```python
def render_email_summary(records: list[dict]) -> str:
    return f"Matched papers: {len(records)}"
```

`src/paper_crawler/notify/smtp_sender.py`

```python
def send_email(subject: str, body: str) -> None:
    _ = (subject, body)
```

- [ ] **Step 4: 把 smoke test 放到 `tests/test_skeleton_imports.py`**

```python
def test_import_skeleton_modules():
    import paper_crawler.fetchers.arxiv
    import paper_crawler.fetchers.crossref
    import paper_crawler.fetchers.openalex
    import paper_crawler.fetchers.unpaywall
    import paper_crawler.matchers.keyword_matcher
    import paper_crawler.matchers.semantic_matcher
    import paper_crawler.notify.email_renderer
    import paper_crawler.notify.smtp_sender
    import paper_crawler.processing.deduplicate
    import paper_crawler.processing.normalize
```

- [ ] **Step 5: 运行完整骨架测试**

Run: `PYTHONPATH=src pytest tests -q`

Expected:

```text
5 passed
```

- [ ] **Step 6: 提交**

```bash
git add src/paper_crawler/fetchers src/paper_crawler/matchers src/paper_crawler/processing src/paper_crawler/notify tests/test_skeleton_imports.py
git commit -m "feat: add importable application skeleton modules"
```

## Self-Review

- 覆盖范围：本计划覆盖代码骨架、配置、模型、CLI、数据库初始化、占位模块和基础测试，符合“先搭骨架再接真实抓取逻辑”的阶段目标。
- 占位检查：计划中未使用 `TODO`、`TBD` 或“类似前文”的模糊描述；每个任务都给出明确文件、代码片段和命令。
- 一致性检查：包名统一为 `paper_crawler`，配置入口统一为 `config/`，运行命令统一使用 `PYTHONPATH=src`。
