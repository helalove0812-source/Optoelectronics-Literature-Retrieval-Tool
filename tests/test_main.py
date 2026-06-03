from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from paper_crawler.main import run_application
from paper_crawler.models import PaperRecord
from paper_crawler.processing.pipeline import PipelineResult
from paper_crawler.settings import SMTPSettings, Settings
from paper_crawler.storage.database import initialize_database


class DummySender:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str, str]] = []

    def __call__(self, config: object, subject: str, body: str) -> None:
        self.calls.append((config, subject, body))


def build_settings_for_main(db_path: Path) -> Settings:
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
        arxiv_categories=["physics.optics"],
        openalex_filters=["concepts.id:C123"],
        lookback_hours=24,
        keyword_groups={"硅光": ["silicon photonics"]},
        issn_whitelist={},
        synonyms={},
        semantic_threshold=0.5,
        enable_semantic_matching=True,
    )


def build_pipeline_result() -> PipelineResult:
    return PipelineResult(
        fetched_count=3,
        matched_count=2,
        matched_records=[
            PaperRecord(
                paper_id="paper-1",
                title="Silicon photonics coherent transceiver",
                authors=["Alice Smith"],
                abstract="A compact coherent transceiver.",
                doi="10.1000/example",
                source="crossref",
                published_at=datetime(2026, 6, 3, 10, 0, tzinfo=UTC),
                landing_url="https://doi.org/10.1000/example",
                pdf_url="https://example.com/paper.pdf",
                access="open",
                matched_keywords=["硅光"],
            ),
            PaperRecord(
                paper_id="paper-2",
                title="Metasurface packaging",
                authors=["Bob Chen"],
                abstract="A metasurface packaging method.",
                doi="10.1000/example2",
                source="openalex",
                published_at=datetime(2026, 6, 3, 11, 0, tzinfo=UTC),
                landing_url="https://doi.org/10.1000/example2",
                pdf_url=None,
                access="subscription",
                matched_keywords=["超表面"],
            ),
        ],
    )


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
