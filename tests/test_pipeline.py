import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from paper_crawler.fetchers.base import FetchResult
from paper_crawler.models import PaperRecord
from paper_crawler.processing.pipeline import run_pipeline
from paper_crawler.settings import Settings


class DummyArxivFetcher:
    def __init__(self, result: FetchResult):
        self.result = result
        self.called = False

    def fetch(self) -> FetchResult:
        self.called = True
        return self.result


class DummyCrossrefFetcher:
    def __init__(self, result: FetchResult):
        self.result = result
        self.called = False

    def fetch(self) -> FetchResult:
        self.called = True
        return self.result


def build_settings() -> Settings:
    return Settings(
        contact_email="team@example.com",
        database_url="sqlite:///data/papers.db",
        arxiv_categories=["physics.optics"],
        keyword_groups={"硅光": ["silicon photonics"]},
        issn_whitelist={},
        synonyms={},
        semantic_threshold=0.5,
        enable_semantic_matching=True,
        lookback_hours=24,
    )


def build_record() -> PaperRecord:
    return PaperRecord(
        paper_id="paper-1",
        title="Silicon Photonics for Coherent Links",
        authors=["Alice Smith"],
        abstract="Recent progress in coherent links.",
        doi=None,
        source="arxiv",
        published_at=datetime(2026, 6, 3, 10, 0, tzinfo=UTC),
        landing_url="http://arxiv.org/abs/2506.00001v1",
        pdf_url="http://arxiv.org/pdf/2506.00001v1",
        access="open",
    )


def test_run_pipeline_uses_arxiv_fetcher_and_counts_records() -> None:
    record = build_record()
    fetcher = DummyArxivFetcher(FetchResult(source="arxiv", records=[record]))
    captured: dict[str, Settings] = {}

    def factory(settings: Settings) -> DummyArxivFetcher:
        captured["settings"] = settings
        return fetcher

    result = run_pipeline(build_settings(), arxiv_fetcher_factory=factory)

    assert fetcher.called is True
    assert captured["settings"].lookback_hours == 24
    assert result.fetched_count == 1
    assert result.matched_count == 1


def test_run_pipeline_uses_crossref_fetcher_and_counts_records() -> None:
    record = build_record()
    record.paper_id = "paper-2"
    record.source = "crossref"
    record.doi = "10.1000/example"
    record.landing_url = "https://doi.org/10.1000/example"
    record.pdf_url = None
    record.access = "subscription"
    crossref_fetcher = DummyCrossrefFetcher(
        FetchResult(source="crossref", records=[record])
    )

    result = run_pipeline(
        build_settings(),
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(FetchResult(source="arxiv")),
        crossref_fetcher_factory=lambda _: crossref_fetcher,
    )

    assert crossref_fetcher.called is True
    assert result.fetched_count == 1
    assert result.matched_count == 1


def test_run_pipeline_persists_records_and_ignores_duplicates(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    settings = build_settings()
    settings.database_url = f"sqlite:///{db_path}"
    fetcher = DummyArxivFetcher(FetchResult(source="arxiv", records=[build_record()]))

    first_result = run_pipeline(settings, arxiv_fetcher_factory=lambda _: fetcher)
    second_result = run_pipeline(settings, arxiv_fetcher_factory=lambda _: fetcher)

    with sqlite3.connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0]

    assert first_result.fetched_count == 1
    assert second_result.fetched_count == 1
    assert count == 1


def test_run_pipeline_persists_crossref_records(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    settings = build_settings()
    settings.database_url = f"sqlite:///{db_path}"
    record = build_record()
    record.paper_id = "paper-crossref"
    record.source = "crossref"
    record.doi = "10.1000/example"
    record.landing_url = "https://doi.org/10.1000/example"
    record.pdf_url = None
    record.access = "subscription"

    run_pipeline(
        settings,
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(FetchResult(source="arxiv")),
        crossref_fetcher_factory=lambda _: DummyCrossrefFetcher(
            FetchResult(source="crossref", records=[record])
        ),
    )

    with sqlite3.connect(db_path) as connection:
        stored = connection.execute(
            "SELECT source, doi, access FROM papers WHERE paper_id = ?",
            (record.paper_id,),
        ).fetchone()

    assert stored == ("crossref", "10.1000/example", "subscription")


def test_run_pipeline_returns_empty_result_when_arxiv_fetch_fails() -> None:
    class FailingArxivFetcher:
        def fetch(self) -> FetchResult:
            raise RuntimeError("rate limited")

    result = run_pipeline(
        build_settings(),
        arxiv_fetcher_factory=lambda settings: FailingArxivFetcher(),
    )

    assert result.fetched_count == 0
    assert result.matched_count == 0
