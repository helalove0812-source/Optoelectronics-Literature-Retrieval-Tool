import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from paper_crawler.models import PaperRecord
from paper_crawler.storage.database import connect_sqlite, initialize_database
from paper_crawler.storage.repositories import PaperRepository, PushLogRepository


def test_initialize_database_creates_expected_tables(tmp_path: Path):
    db_path = tmp_path / "papers.db"

    initialize_database(db_path)

    assert db_path.exists()

    with sqlite3.connect(db_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {"papers", "push_log", "runs"} <= table_names


def test_paper_repository_insert_or_ignore_deduplicates_by_paper_id(tmp_path: Path):
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)

    record = PaperRecord(
        paper_id="10.1000/example",
        title="Silicon Photonics for Coherent Links",
        authors=["Alice Smith", "Bob Chen"],
        abstract="A paper about coherent links.",
        doi="10.1000/example",
        source="crossref",
        published_at=datetime(2026, 6, 3, tzinfo=UTC),
        landing_url="https://doi.org/10.1000/example",
        pdf_url=None,
        access="subscription",
        matched_keywords=["silicon photonics"],
        semantic_score=0.72,
    )

    with connect_sqlite(db_path) as connection:
        repository = PaperRepository(connection)

        assert repository.insert_or_ignore(record) is True
        assert repository.insert_or_ignore(record) is False

        stored = connection.execute(
            "SELECT title, authors_json, matched_keywords_json FROM papers WHERE paper_id = ?",
            (record.paper_id,),
        ).fetchone()

    assert stored == (
        "Silicon Photonics for Coherent Links",
        '["Alice Smith", "Bob Chen"]',
        '["silicon photonics"]',
    )


def test_push_log_repository_marks_papers_as_pushed(tmp_path: Path):
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)

    with connect_sqlite(db_path) as connection:
        repository = PushLogRepository(connection)

        assert repository.has_been_pushed("paper-1") is False

        repository.mark_pushed(
            paper_id="paper-1",
            pushed_at=datetime(2026, 6, 3, 8, 30, tzinfo=UTC),
            channel="email",
        )

        assert repository.has_been_pushed("paper-1") is True


def test_paper_repository_persists_and_updates_zh_summary(tmp_path: Path):
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)

    record = PaperRecord(
        paper_id="10.1000/summary",
        title="Silicon Photonics for Coherent Links",
        authors=["Alice Smith", "Bob Chen"],
        abstract="A paper about coherent links.",
        doi="10.1000/summary",
        source="crossref",
        published_at=datetime(2026, 6, 3, tzinfo=UTC),
        landing_url="https://doi.org/10.1000/summary",
        pdf_url=None,
        access="subscription",
        matched_keywords=["silicon photonics"],
        semantic_score=0.72,
        zh_summary="这篇论文研究了相干链路中的硅光器件集成。",
    )

    with connect_sqlite(db_path) as connection:
        repository = PaperRepository(connection)
        assert repository.insert_or_ignore(record) is True
        repository.update_zh_summary(
            record.paper_id,
            "论文提出了面向数据中心互连的紧凑型硅光实现方案。",
        )
        connection.commit()

        stored = connection.execute(
            "SELECT zh_summary FROM papers WHERE paper_id = ?",
            (record.paper_id,),
        ).fetchone()

    assert stored == ("论文提出了面向数据中心互连的紧凑型硅光实现方案。",)


def test_initialize_database_adds_zh_summary_column_to_existing_papers_table(
    tmp_path: Path,
):
    db_path = tmp_path / "legacy.db"

    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE papers (
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
            """
        )

    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(papers)")
        }

    assert "zh_summary" in columns
