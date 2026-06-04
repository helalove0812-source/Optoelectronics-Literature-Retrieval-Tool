from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Protocol

import requests

from paper_crawler.fetchers.base import BaseFetcher, FetchResult
from paper_crawler.models import PaperRecord
from paper_crawler.utils.fingerprint import build_paper_fingerprint
from paper_crawler.utils.time_utils import parse_utc_datetime, utc_now

TAVILY_API_URL = "https://api.tavily.com/search"
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


class SupportsPost(Protocol):
    def post(self, url: str, json: dict[str, object], timeout: int): ...


@dataclass(slots=True)
class TavilyFetcher(BaseFetcher):
    api_key: str
    keyword_groups: dict[str, list[str]]
    max_results: int = 5
    request_timeout: int = 30
    session: SupportsPost | requests.Session | None = None
    now_func: Callable[[], datetime] = utc_now
    source_name: str = "tavily"

    def fetch(self) -> FetchResult:
        session = self.session or requests.Session()
        response = session.post(
            TAVILY_API_URL,
            json={
                "api_key": self.api_key,
                "query": self._build_query(),
                "max_results": self.max_results,
            },
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])
        if not isinstance(results, list):
            results = []
        return FetchResult(
            source=self.source_name,
            records=self._parse_results(results),
        )

    def _build_query(self) -> str:
        core_terms: list[str] = []
        for terms in self.keyword_groups.values():
            for term in terms:
                normalized = " ".join(str(term).split()).strip()
                if normalized and normalized not in core_terms:
                    core_terms.append(normalized)
                if len(core_terms) >= 3:
                    break
            if len(core_terms) >= 3:
                break
        return " ".join([*core_terms, "paper", "arxiv", "doi"])

    def _parse_results(self, results: list[object]) -> list[PaperRecord]:
        records: list[PaperRecord] = []

        for item in results:
            if not isinstance(item, dict):
                continue

            title = " ".join(str(item.get("title", "")).split())
            landing_url = str(item.get("url", "")).strip()
            abstract = " ".join(str(item.get("content", "")).split())
            doi = self._extract_doi(f"{landing_url}\n{abstract}")
            published_at = self._parse_published_at(item.get("published_date"))

            records.append(
                PaperRecord(
                    paper_id=doi or build_paper_fingerprint(title=title, authors=[]),
                    title=title,
                    authors=[],
                    abstract=abstract,
                    doi=doi,
                    source=self.source_name,
                    published_at=published_at,
                    landing_url=landing_url,
                    pdf_url=None,
                    access="subscription",
                )
            )

        return records

    def _parse_published_at(self, value: object) -> datetime:
        if isinstance(value, str) and value.strip():
            try:
                return parse_utc_datetime(value)
            except ValueError:
                pass
        return self.now_func()

    @staticmethod
    def _extract_doi(value: str) -> str | None:
        match = DOI_PATTERN.search(value)
        if match is None:
            return None
        return match.group(0).rstrip(".,;)")
