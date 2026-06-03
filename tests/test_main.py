from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from paper_crawler.main import run_application
from paper_crawler.models import PaperRecord
from paper_crawler.processing.pipeline import PipelineResult
from paper_crawler.settings import LLMSettings, SMTPSettings, Settings
from paper_crawler.storage.database import connect_sqlite, initialize_database
from paper_crawler.storage.repositories import PaperRepository


class DummySender:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str, str]] = []

    def __call__(self, config: object, subject: str, body: str) -> None:
        self.calls.append((config, subject, body))


class DummySummaryClient:
    def __init__(
        self,
        responses: dict[str, str] | None = None,
        failures: set[str] | None = None,
    ) -> None:
        self._responses = responses or {}
        self._failures = failures or set()
        self.calls: list[str] = []

    def summarize_paper(
        self,
        *,
        title: str,
        abstract: str,
        matched_keywords: list[str],
    ) -> str:
        del abstract, matched_keywords
        paper_id = title.removeprefix("Title for ")
        self.calls.append(paper_id)
        if paper_id in self._failures:
            raise RuntimeError(f"summary failed for {paper_id}")
        return self._responses[paper_id]


def build_settings_for_main(db_path: Path, *, llm_enabled: bool = False) -> Settings:
    return Settings(
        contact_email="team@example.com",
        database_url=f"sqlite:///{db_path}",
        smtp=SMTPSettings(
            host="smtp.example.com",
            port=587,
            username="research-alert@example.com",
            from_address="research-alert@example.com",
            to_address="user@example.com",
            use_tls=True,
        ),
        llm=LLMSettings(
            enabled=llm_enabled,
            provider="deepseek",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            timeout_seconds=30,
        ),
        arxiv_categories=["physics.optics"],
        openalex_filters=["concepts.id:C123"],
        lookback_hours=24,
        keyword_groups={"硅光": ["silicon photonics"]},
        issn_whitelist={},
        synonyms={},
        semantic_threshold=0.5,
        enable_semantic_matching=True,
    )


def build_pipeline_result(*records: PaperRecord) -> PipelineResult:
    matched_records = list(records) if records else [build_record("paper-1"), build_record("paper-2")]
    return PipelineResult(
        fetched_count=3,
        matched_count=len(matched_records),
        matched_records=matched_records,
    )


def build_record(
    paper_id: str,
    *,
    title: str | None = None,
    abstract: str | None = None,
    matched_keywords: list[str] | None = None,
    zh_summary: str | None = None,
) -> PaperRecord:
    return PaperRecord(
        paper_id=paper_id,
        title=title or f"Title for {paper_id}",
        authors=["Alice Smith"],
        abstract=abstract or f"Abstract for {paper_id}.",
        doi=f"10.1000/{paper_id}",
        source="crossref",
        published_at=datetime(2026, 6, 3, 10, 0, tzinfo=UTC),
        landing_url=f"https://doi.org/10.1000/{paper_id}",
        pdf_url=None,
        access="open",
        matched_keywords=matched_keywords or ["硅光"],
        zh_summary=zh_summary,
    )


def seed_records(db_path: Path, *records: PaperRecord) -> None:
    with connect_sqlite(db_path) as connection:
        repository = PaperRepository(connection)
        for record in records:
            repository.insert_or_ignore(record)
        connection.commit()


def test_run_application_sends_unpushed_records_and_marks_them(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)
    sender = DummySender()
    rendered: dict[str, list[str]] = {}
    pushed_at = datetime(2026, 6, 3, 12, 0, tzinfo=UTC)

    def renderer(records: list[PaperRecord]) -> str:
        rendered["paper_ids"] = [record.paper_id for record in records]
        return f"Matched papers: {len(records)}"

    summary = run_application(
        tmp_path,
        settings_loader=lambda _: build_settings_for_main(db_path),
        pipeline_runner=lambda settings: build_pipeline_result(),
        email_renderer=renderer,
        email_sender=sender,
        smtp_password_getter=lambda: "secret",
        now_func=lambda: pushed_at,
    )

    assert "fetched=3" in summary
    assert "matched=2" in summary
    assert "to_push=2" in summary
    assert "email_sent=yes" in summary
    assert rendered["paper_ids"] == ["paper-1", "paper-2"]
    assert len(sender.calls) == 1
    config, subject, body = sender.calls[0]
    assert subject == "Daily paper digest (2)"
    assert body == "Matched papers: 2"
    assert config.password == "secret"

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT paper_id, pushed_at, channel FROM push_log ORDER BY paper_id"
        ).fetchall()

    assert rows == [
        ("paper-1", pushed_at.isoformat(), "email"),
        ("paper-2", pushed_at.isoformat(), "email"),
    ]


def test_run_application_skips_already_pushed_records(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO push_log (paper_id, pushed_at, channel) VALUES (?, ?, ?)",
            ("paper-1", datetime(2026, 6, 3, 8, 0, tzinfo=UTC).isoformat(), "email"),
        )
        connection.commit()

    sender = DummySender()
    rendered: dict[str, list[str]] = {}

    def renderer(records: list[PaperRecord]) -> str:
        rendered["paper_ids"] = [record.paper_id for record in records]
        return f"Matched papers: {len(records)}"

    summary = run_application(
        tmp_path,
        settings_loader=lambda _: build_settings_for_main(db_path),
        pipeline_runner=lambda settings: build_pipeline_result(),
        email_renderer=renderer,
        email_sender=sender,
        smtp_password_getter=lambda: "secret",
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    assert "to_push=1" in summary
    assert "email_sent=yes" in summary
    assert rendered["paper_ids"] == ["paper-2"]
    assert len(sender.calls) == 1
    assert sender.calls[0][1] == "Daily paper digest (1)"
    assert sender.calls[0][2] == "Matched papers: 1"

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT paper_id FROM push_log ORDER BY id"
        ).fetchall()

    assert rows == [("paper-1",), ("paper-2",)]


def test_run_application_does_not_send_empty_email_when_no_records_to_push(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)
    pushed_at = datetime(2026, 6, 3, 8, 0, tzinfo=UTC).isoformat()
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            "INSERT INTO push_log (paper_id, pushed_at, channel) VALUES (?, ?, ?)",
            [
                ("paper-1", pushed_at, "email"),
                ("paper-2", pushed_at, "email"),
            ],
        )
        connection.commit()

    def renderer(records: list[PaperRecord]) -> str:
        raise AssertionError(f"renderer should not be called: {records!r}")

    def sender(config: object, subject: str, body: str) -> None:
        raise AssertionError(
            f"sender should not be called: {(config, subject, body)!r}"
        )

    summary = run_application(
        tmp_path,
        settings_loader=lambda _: build_settings_for_main(db_path),
        pipeline_runner=lambda settings: build_pipeline_result(),
        email_renderer=renderer,
        email_sender=sender,
        smtp_password_getter=lambda: "secret",
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    assert "to_push=0" in summary
    assert "email_sent=no" in summary

    with sqlite3.connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM push_log").fetchone()[0]

    assert count == 2


def test_run_application_summarizes_only_to_push_records_without_existing_summary(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)
    paper_1 = build_record("paper-1")
    paper_2 = build_record("paper-2", zh_summary="已有中文总结")
    paper_3 = build_record("paper-3")
    seed_records(db_path, paper_1, paper_2, paper_3)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO push_log (paper_id, pushed_at, channel) VALUES (?, ?, ?)",
            ("paper-1", datetime(2026, 6, 3, 8, 0, tzinfo=UTC).isoformat(), "email"),
        )
        connection.commit()

    sender = DummySender()
    rendered: dict[str, list[tuple[str, str | None]]] = {}
    summary_client = DummySummaryClient(
        responses={"paper-3": "这是 paper-3 的中文总结。"}
    )

    def renderer(records: list[PaperRecord]) -> str:
        rendered["records"] = [
            (record.paper_id, record.zh_summary) for record in records
        ]
        return f"Matched papers: {len(records)}"

    summary = run_application(
        tmp_path,
        settings_loader=lambda _: build_settings_for_main(db_path, llm_enabled=True),
        pipeline_runner=lambda settings: build_pipeline_result(paper_1, paper_2, paper_3),
        email_renderer=renderer,
        email_sender=sender,
        summary_client_builder=lambda settings: summary_client,
        smtp_password_getter=lambda: "secret",
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    assert "to_push=2" in summary
    assert summary_client.calls == ["paper-3"]
    assert rendered["records"] == [
        ("paper-2", "已有中文总结"),
        ("paper-3", "这是 paper-3 的中文总结。"),
    ]

    with sqlite3.connect(db_path) as connection:
        stored = connection.execute(
            "SELECT paper_id, zh_summary FROM papers ORDER BY paper_id"
        ).fetchall()

    assert stored == [
        ("paper-1", None),
        ("paper-2", "已有中文总结"),
        ("paper-3", "这是 paper-3 的中文总结。"),
    ]


def test_run_application_continues_when_single_summary_generation_fails(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)
    paper_1 = build_record("paper-1")
    paper_2 = build_record("paper-2")
    seed_records(db_path, paper_1, paper_2)

    sender = DummySender()
    rendered: dict[str, list[tuple[str, str | None]]] = {}
    summary_client = DummySummaryClient(
        responses={"paper-2": "这是 paper-2 的中文总结。"},
        failures={"paper-1"},
    )

    def renderer(records: list[PaperRecord]) -> str:
        rendered["records"] = [
            (record.paper_id, record.zh_summary) for record in records
        ]
        return f"Matched papers: {len(records)}"

    with caplog.at_level(logging.WARNING):
        summary = run_application(
            tmp_path,
            settings_loader=lambda _: build_settings_for_main(db_path, llm_enabled=True),
            pipeline_runner=lambda settings: build_pipeline_result(paper_1, paper_2),
            email_renderer=renderer,
            email_sender=sender,
            summary_client_builder=lambda settings: summary_client,
            smtp_password_getter=lambda: "secret",
            now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
        )

    assert "to_push=2" in summary
    assert "email_sent=yes" in summary
    assert summary_client.calls == ["paper-1", "paper-2"]
    assert rendered["records"] == [
        ("paper-1", None),
        ("paper-2", "这是 paper-2 的中文总结。"),
    ]
    assert "paper-1" in caplog.text

    with sqlite3.connect(db_path) as connection:
        stored = connection.execute(
            "SELECT paper_id, zh_summary FROM papers ORDER BY paper_id"
        ).fetchall()
        push_log_count = connection.execute(
            "SELECT COUNT(*) FROM push_log"
        ).fetchone()[0]

    assert stored == [
        ("paper-1", None),
        ("paper-2", "这是 paper-2 的中文总结。"),
    ]
    assert push_log_count == 2


def test_run_application_does_not_write_push_log_when_email_fails_but_keeps_summaries(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "papers.db"
    initialize_database(db_path)
    paper_1 = build_record("paper-1")
    paper_2 = build_record("paper-2", zh_summary="已有中文总结")
    seed_records(db_path, paper_1, paper_2)
    summary_client = DummySummaryClient(
        responses={"paper-1": "这是 paper-1 的中文总结。"}
    )

    def sender(config: object, subject: str, body: str) -> None:
        del config, subject, body
        raise RuntimeError("SMTP unavailable")

    with pytest.raises(RuntimeError, match="SMTP unavailable"):
        run_application(
            tmp_path,
            settings_loader=lambda _: build_settings_for_main(db_path, llm_enabled=True),
            pipeline_runner=lambda settings: build_pipeline_result(paper_1, paper_2),
            email_sender=sender,
            summary_client_builder=lambda settings: summary_client,
            smtp_password_getter=lambda: "secret",
            now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
        )

    assert summary_client.calls == ["paper-1"]

    with sqlite3.connect(db_path) as connection:
        stored = connection.execute(
            "SELECT paper_id, zh_summary FROM papers ORDER BY paper_id"
        ).fetchall()
        push_log_count = connection.execute(
            "SELECT COUNT(*) FROM push_log"
        ).fetchone()[0]

    assert stored == [
        ("paper-1", "这是 paper-1 的中文总结。"),
        ("paper-2", "已有中文总结"),
    ]
    assert push_log_count == 0
