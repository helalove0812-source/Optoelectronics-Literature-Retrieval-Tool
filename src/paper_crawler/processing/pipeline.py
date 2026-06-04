from dataclasses import dataclass
import logging
import os
from typing import Callable

from paper_crawler.fetchers.arxiv import ArxivFetcher
from paper_crawler.fetchers.crossref import CrossrefFetcher
from paper_crawler.fetchers.openalex import OpenAlexFetcher
from paper_crawler.fetchers.tavily import TavilyFetcher
from paper_crawler.fetchers.unpaywall import UnpaywallClient
from paper_crawler.matchers.keyword_matcher import build_keyword_index, match_keywords
from paper_crawler.models import PaperRecord
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
    matched_records: list[PaperRecord]


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


def build_openalex_fetcher(settings: Settings) -> OpenAlexFetcher:
    return OpenAlexFetcher(
        filters=settings.openalex_filters,
        contact_email=settings.contact_email,
        lookback_hours=settings.lookback_hours,
    )


def build_unpaywall_client(settings: Settings) -> UnpaywallClient:
    return UnpaywallClient(contact_email=settings.contact_email)


def build_tavily_fetcher(
    settings: Settings,
    api_key_getter: Callable[[], str | None] = lambda: os.getenv("TAVILY_API_KEY"),
) -> TavilyFetcher | None:
    if not settings.enable_tavily_fallback:
        return None

    api_key = api_key_getter()
    if not api_key:
        logging.getLogger(__name__).warning(
            "Tavily fallback is enabled but TAVILY_API_KEY is missing"
        )
        return None

    return TavilyFetcher(
        api_key=api_key,
        keyword_groups=settings.keyword_groups,
        max_results=settings.tavily_max_results,
    )


def run_pipeline(
    settings: Settings,
    arxiv_fetcher_factory: Callable[[Settings], ArxivFetcher] = build_arxiv_fetcher,
    crossref_fetcher_factory: Callable[
        [Settings], CrossrefFetcher
    ] = build_crossref_fetcher,
    openalex_fetcher_factory: Callable[[Settings], OpenAlexFetcher] = build_openalex_fetcher,
    unpaywall_client_factory: Callable[
        [Settings], UnpaywallClient
    ] = build_unpaywall_client,
    tavily_fetcher_factory: Callable[[Settings], TavilyFetcher | None] = build_tavily_fetcher,
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

    try:
        openalex_result = openalex_fetcher_factory(settings).fetch()
        records.extend(openalex_result.records)
    except Exception as exc:
        logging.getLogger(__name__).warning("OpenAlex fetch failed: %s", exc)

    if not records and settings.enable_tavily_fallback:
        try:
            tavily_fetcher = tavily_fetcher_factory(settings)
            if tavily_fetcher is not None:
                tavily_result = tavily_fetcher.fetch()
                records.extend(tavily_result.records)
        except Exception as exc:
            logging.getLogger(__name__).warning("Tavily fallback failed: %s", exc)

    if not records:
        return PipelineResult(fetched_count=0, matched_count=0, matched_records=[])

    keyword_index = build_keyword_index(settings.keyword_groups, settings.synonyms)
    matched_count = 0
    matched_records: list[PaperRecord] = []
    unpaywall_client: UnpaywallClient | None = None
    for record in records:
        record.matched_keywords = match_keywords(
            title=record.title,
            abstract=record.abstract,
            keyword_index=keyword_index,
        )
        if record.matched_keywords:
            matched_count += 1
            matched_records.append(record)
        if not record.matched_keywords or not record.doi or record.source == "arxiv":
            continue

        if unpaywall_client is None:
            unpaywall_client = unpaywall_client_factory(settings)

        try:
            lookup = unpaywall_client.lookup(record.doi)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Unpaywall lookup failed for %s: %s", record.doi, exc
            )
            continue

        record.access = "open" if lookup.get("is_oa") else "subscription"
        record.pdf_url = lookup.get("pdf_url")
        landing_url = lookup.get("landing_url")
        if landing_url:
            record.landing_url = str(landing_url)

    db_path = resolve_sqlite_path(settings.database_url)
    initialize_database(db_path)

    with connect_sqlite(db_path) as connection:
        repository = PaperRepository(connection)
        for record in records:
            repository.insert_or_ignore(record)
        connection.commit()

    fetched_count = len(records)
    return PipelineResult(
        fetched_count=fetched_count,
        matched_count=matched_count,
        matched_records=matched_records,
    )
