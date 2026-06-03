from dataclasses import dataclass
import logging
from typing import Callable

from paper_crawler.fetchers.arxiv import ArxivFetcher
from paper_crawler.fetchers.crossref import CrossrefFetcher
from paper_crawler.settings import Settings
from paper_crawler.storage import (
    PaperRepository,
    connect_sqlite,
    initialize_database,
    resolve_sqlite_path,
)


@dataclass(slots=True)
class PipelineResult:
    fetched_count: int
    matched_count: int


def build_arxiv_fetcher(settings: Settings) -> ArxivFetcher:
    return ArxivFetcher(
        categories=settings.arxiv_categories,
        lookback_hours=settings.lookback_hours,
    )


def build_crossref_fetcher(settings: Settings) -> CrossrefFetcher:
    return CrossrefFetcher(
        issn_whitelist=settings.issn_whitelist,
        contact_email=settings.contact_email,
        lookback_hours=settings.lookback_hours,
    )


def run_pipeline(
    settings: Settings,
    arxiv_fetcher_factory: Callable[[Settings], ArxivFetcher] = build_arxiv_fetcher,
    crossref_fetcher_factory: Callable[
        [Settings], CrossrefFetcher
    ] = build_crossref_fetcher,
) -> PipelineResult:
    records = []

    try:
        arxiv_result = arxiv_fetcher_factory(settings).fetch()
        records.extend(arxiv_result.records)
    except Exception as exc:
        logging.getLogger(__name__).warning("arXiv fetch failed: %s", exc)

    try:
        crossref_result = crossref_fetcher_factory(settings).fetch()
        records.extend(crossref_result.records)
    except Exception as exc:
        logging.getLogger(__name__).warning("Crossref fetch failed: %s", exc)

    if not records:
        return PipelineResult(fetched_count=0, matched_count=0)

    db_path = resolve_sqlite_path(settings.database_url)
    initialize_database(db_path)

    with connect_sqlite(db_path) as connection:
        repository = PaperRepository(connection)
        for record in records:
            repository.insert_or_ignore(record)
        connection.commit()

    fetched_count = len(records)
    return PipelineResult(fetched_count=fetched_count, matched_count=fetched_count)
