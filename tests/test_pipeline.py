import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from paper_crawler.fetchers.base import FetchResult
from paper_crawler.models import PaperRecord
from paper_crawler.processing.pipeline import run_pipeline
from paper_crawler.settings import SMTPSettings, Settings


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


class DummyOpenAlexFetcher:
    def __init__(self, result: FetchResult):
        self.result = result
        self.called = False

    def fetch(self) -> FetchResult:
        self.called = True
        return self.result


class DummyUnpaywallClient:
    def __init__(self, response: dict[str, object]):
        self.response = response
        self.calls: list[str] = []

    def lookup(self, doi: str) -> dict[str, object]:
        self.calls.append(doi)
        return self.response


class FailingUnpaywallClient:
    def lookup(self, doi: str) -> dict[str, object]:
        raise RuntimeError("temporary upstream failure")


def build_settings() -> Settings:
    return Settings(
        contact_email="team@example.com",
        database_url="sqlite:///data/papers.db",
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


def test_run_pipeline_uses_openalex_fetcher_and_counts_records() -> None:
    record = build_record()
    record.paper_id = "paper-openalex"
    record.source = "openalex"
    record.doi = "10.1000/openalex"
    record.landing_url = "https://openalex.org/W123"
    record.pdf_url = None
    openalex_fetcher = DummyOpenAlexFetcher(
        FetchResult(source="openalex", records=[record])
    )

    result = run_pipeline(
        build_settings(),
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(FetchResult(source="arxiv")),
        crossref_fetcher_factory=lambda _: DummyCrossrefFetcher(
            FetchResult(source="crossref")
        ),
        openalex_fetcher_factory=lambda _: openalex_fetcher,
    )

    assert openalex_fetcher.called is True
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


def test_run_pipeline_persists_openalex_records(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    settings = build_settings()
    settings.database_url = f"sqlite:///{db_path}"
    record = build_record()
    record.paper_id = "paper-openalex"
    record.source = "openalex"
    record.doi = "10.1000/openalex"
    record.landing_url = "https://openalex.org/W123"
    record.pdf_url = None
    record.access = "open"

    run_pipeline(
        settings,
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(FetchResult(source="arxiv")),
        crossref_fetcher_factory=lambda _: DummyCrossrefFetcher(
            FetchResult(source="crossref")
        ),
        openalex_fetcher_factory=lambda _: DummyOpenAlexFetcher(
            FetchResult(source="openalex", records=[record])
        ),
    )

    with sqlite3.connect(db_path) as connection:
        stored = connection.execute(
            "SELECT source, doi, access FROM papers WHERE paper_id = ?",
            (record.paper_id,),
        ).fetchone()

    assert stored == ("openalex", "10.1000/openalex", "open")


def test_run_pipeline_populates_matched_keywords_and_counts_only_matches(
    tmp_path: Path,
) -> None:
    settings = build_settings()
    settings.database_url = f"sqlite:///{tmp_path / 'papers.db'}"

    matched_record = build_record()
    matched_record.paper_id = "paper-match"
    matched_record.title = "Silicon photonics coherent link packaging"
    matched_record.abstract = "Photonics integration for datacenter optics."

    unmatched_record = build_record()
    unmatched_record.paper_id = "paper-unmatched"
    unmatched_record.title = "Battery chemistry advances"
    unmatched_record.abstract = "Electrochemistry only."

    result = run_pipeline(
        settings,
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(
            FetchResult(source="arxiv", records=[matched_record, unmatched_record])
        ),
        crossref_fetcher_factory=lambda _: DummyCrossrefFetcher(
            FetchResult(source="crossref")
        ),
        openalex_fetcher_factory=lambda _: DummyOpenAlexFetcher(
            FetchResult(source="openalex")
        ),
    )

    assert matched_record.matched_keywords == ["硅光"]
    assert unmatched_record.matched_keywords == []
    assert result.fetched_count == 2
    assert result.matched_count == 1


def test_run_pipeline_returns_matched_records(tmp_path: Path) -> None:
    settings = build_settings()
    settings.database_url = f"sqlite:///{tmp_path / 'papers.db'}"

    matched_record = build_record()
    matched_record.paper_id = "paper-match"
    matched_record.title = "Silicon photonics coherent link packaging"
    matched_record.abstract = "Photonics integration for datacenter optics."

    unmatched_record = build_record()
    unmatched_record.paper_id = "paper-unmatched"
    unmatched_record.title = "Battery chemistry advances"
    unmatched_record.abstract = "Electrochemistry only."

    result = run_pipeline(
        settings,
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(
            FetchResult(source="arxiv", records=[matched_record, unmatched_record])
        ),
        crossref_fetcher_factory=lambda _: DummyCrossrefFetcher(
            FetchResult(source="crossref")
        ),
        openalex_fetcher_factory=lambda _: DummyOpenAlexFetcher(
            FetchResult(source="openalex")
        ),
        unpaywall_client_factory=lambda _: DummyUnpaywallClient(
            {"is_oa": False, "pdf_url": None, "landing_url": None}
        ),
    )

    assert [record.paper_id for record in result.matched_records] == ["paper-match"]


def test_run_pipeline_persists_matched_keyword_group_names_json(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "papers.db"
    settings = build_settings()
    settings.database_url = f"sqlite:///{db_path}"
    record = build_record()
    record.paper_id = "paper-match-json"
    record.title = "Silicon photonics coherent link packaging"
    record.abstract = "Photonics integration for datacenter optics."

    run_pipeline(
        settings,
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(
            FetchResult(source="arxiv", records=[record])
        ),
        crossref_fetcher_factory=lambda _: DummyCrossrefFetcher(
            FetchResult(source="crossref")
        ),
        openalex_fetcher_factory=lambda _: DummyOpenAlexFetcher(
            FetchResult(source="openalex")
        ),
    )

    with sqlite3.connect(db_path) as connection:
        stored = connection.execute(
            "SELECT matched_keywords_json FROM papers WHERE paper_id = ?",
            (record.paper_id,),
        ).fetchone()

    assert stored is not None
    assert json.loads(stored[0]) == ["硅光"]


def test_run_pipeline_enriches_only_matched_non_arxiv_records_with_doi(
    tmp_path: Path,
) -> None:
    settings = build_settings()
    settings.database_url = f"sqlite:///{tmp_path / 'papers.db'}"

    matched_record = build_record()
    matched_record.paper_id = "paper-oa"
    matched_record.source = "crossref"
    matched_record.title = "Silicon photonics coherent link packaging"
    matched_record.abstract = "Photonics integration for datacenter optics."
    matched_record.doi = "10.1000/example"
    matched_record.landing_url = "https://doi.org/10.1000/example"
    matched_record.pdf_url = None
    matched_record.access = "subscription"

    unmatched_record = build_record()
    unmatched_record.paper_id = "paper-no-match"
    unmatched_record.source = "crossref"
    unmatched_record.title = "Battery chemistry advances"
    unmatched_record.abstract = "Electrochemistry only."
    unmatched_record.doi = "10.1000/ignored"
    unmatched_record.landing_url = "https://doi.org/10.1000/ignored"
    unmatched_record.pdf_url = None
    unmatched_record.access = "subscription"

    no_doi_record = build_record()
    no_doi_record.paper_id = "paper-no-doi"
    no_doi_record.source = "crossref"
    no_doi_record.title = "Silicon photonics integration"
    no_doi_record.abstract = "Datacenter optics."
    no_doi_record.doi = None
    no_doi_record.landing_url = "https://example.com/no-doi"
    no_doi_record.pdf_url = None
    no_doi_record.access = "subscription"

    arxiv_record = build_record()
    arxiv_record.paper_id = "paper-arxiv-skip"
    arxiv_record.title = "Silicon photonics link design"
    arxiv_record.abstract = "Datacenter optics packaging."
    arxiv_record.doi = "10.1000/arxiv-skip"
    arxiv_record.landing_url = "https://arxiv.org/abs/2506.00002"
    arxiv_record.pdf_url = "https://arxiv.org/pdf/2506.00002"
    arxiv_record.access = "open"

    client = DummyUnpaywallClient(
        {
            "is_oa": True,
            "pdf_url": "https://repository.example.com/paper.pdf",
            "landing_url": "https://repository.example.com/landing",
        }
    )

    run_pipeline(
        settings,
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(
            FetchResult(source="arxiv", records=[arxiv_record])
        ),
        crossref_fetcher_factory=lambda _: DummyCrossrefFetcher(
            FetchResult(
                source="crossref",
                records=[matched_record, unmatched_record, no_doi_record],
            )
        ),
        openalex_fetcher_factory=lambda _: DummyOpenAlexFetcher(
            FetchResult(source="openalex")
        ),
        unpaywall_client_factory=lambda _: client,
    )

    assert client.calls == ["10.1000/example"]
    assert matched_record.access == "open"
    assert matched_record.pdf_url == "https://repository.example.com/paper.pdf"
    assert matched_record.landing_url == "https://repository.example.com/landing"
    assert unmatched_record.access == "subscription"
    assert unmatched_record.pdf_url is None
    assert unmatched_record.landing_url == "https://doi.org/10.1000/ignored"
    assert no_doi_record.access == "subscription"
    assert no_doi_record.pdf_url is None
    assert no_doi_record.landing_url == "https://example.com/no-doi"
    assert arxiv_record.access == "open"
    assert arxiv_record.pdf_url == "https://arxiv.org/pdf/2506.00002"
    assert arxiv_record.landing_url == "https://arxiv.org/abs/2506.00002"


def test_run_pipeline_continues_when_unpaywall_lookup_fails(tmp_path: Path) -> None:
    settings = build_settings()
    db_path = tmp_path / "papers.db"
    settings.database_url = f"sqlite:///{db_path}"

    record = build_record()
    record.paper_id = "paper-failing-unpaywall"
    record.source = "crossref"
    record.title = "Silicon photonics coherent link packaging"
    record.abstract = "Photonics integration for datacenter optics."
    record.doi = "10.1000/example"
    record.landing_url = "https://doi.org/10.1000/example"
    record.pdf_url = None
    record.access = "subscription"

    result = run_pipeline(
        settings,
        arxiv_fetcher_factory=lambda _: DummyArxivFetcher(FetchResult(source="arxiv")),
        crossref_fetcher_factory=lambda _: DummyCrossrefFetcher(
            FetchResult(source="crossref", records=[record])
        ),
        openalex_fetcher_factory=lambda _: DummyOpenAlexFetcher(
            FetchResult(source="openalex")
        ),
        unpaywall_client_factory=lambda _: FailingUnpaywallClient(),
    )

    with sqlite3.connect(db_path) as connection:
        stored = connection.execute(
            "SELECT access, pdf_url, landing_url FROM papers WHERE paper_id = ?",
            (record.paper_id,),
        ).fetchone()

    assert result.fetched_count == 1
    assert result.matched_count == 1
    assert record.access == "subscription"
    assert record.pdf_url is None
    assert record.landing_url == "https://doi.org/10.1000/example"
    assert stored == ("subscription", None, "https://doi.org/10.1000/example")


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
