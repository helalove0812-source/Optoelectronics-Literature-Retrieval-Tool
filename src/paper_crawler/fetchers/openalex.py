from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import sleep
from typing import Any, Callable, Protocol

import requests

from paper_crawler.fetchers.base import BaseFetcher, FetchResult
from paper_crawler.models import PaperRecord
from paper_crawler.utils.fingerprint import build_paper_fingerprint
from paper_crawler.utils.time_utils import parse_utc_datetime, utc_now, within_lookback_window

OPENALEX_API_URL = "https://api.openalex.org/works"
logger = logging.getLogger(__name__)


class SupportsGet(Protocol):
    def get(self, url: str, params: dict[str, object], timeout: int): ...


@dataclass(slots=True)
class OpenAlexFetcher(BaseFetcher):
    filters: list[str]
    contact_email: str
    lookback_hours: int = 24
    per_page: int = 200
    request_timeout: int = 30
    request_interval_seconds: int = 1
    max_retry_attempts: int = 3
    session: SupportsGet | requests.Session | None = None
    sleep_func: Callable[[int], None] = sleep
    now_func: Callable[[], datetime] = utc_now
    source_name: str = "openalex"

    def fetch(self) -> FetchResult:
        session = self.session or requests.Session()
        now = self.now_func()
        from_created_date = (now - timedelta(hours=self.lookback_hours)).date().isoformat()
        records: list[PaperRecord] = []

        for index, filter_fragment in enumerate(self.filters):
            if index > 0:
                self.sleep_func(self.request_interval_seconds)

            response = self._request_with_retry(
                session=session,
                filter_fragment=filter_fragment,
                from_created_date=from_created_date,
            )
            payload = response.json()
            results = payload.get("results", [])
            records.extend(self._parse_results(results=results, now=now))

        return FetchResult(source=self.source_name, records=records)

    def _request_with_retry(
        self,
        session: SupportsGet | requests.Session,
        filter_fragment: str,
        from_created_date: str,
    ) -> requests.Response | Any:
        params = {
            "filter": f"{filter_fragment},from_created_date:{from_created_date}",
            "per-page": min(self.per_page, 100),
            "mailto": self.contact_email,
        }

        for attempt in range(self.max_retry_attempts + 1):
            response = session.get(
                OPENALEX_API_URL,
                params=params,
                timeout=self.request_timeout,
            )
            try:
                response.raise_for_status()
                return response
            except requests.HTTPError:
                if getattr(response, "status_code", None) != 429:
                    raise
                if attempt >= self.max_retry_attempts:
                    raise

                wait_seconds = self._resolve_retry_delay(response, attempt)
                logger.warning(
                    "OpenAlex rate limited for filter=%s, attempt=%s/%s, "
                    "retry_after=%s, remaining=%s, waiting=%ss",
                    filter_fragment,
                    attempt + 1,
                    self.max_retry_attempts,
                    getattr(response, "headers", {}).get("Retry-After"),
                    getattr(response, "headers", {}).get("X-RateLimit-Remaining"),
                    wait_seconds,
                )
                self.sleep_func(wait_seconds)

        raise RuntimeError("unreachable")

    @staticmethod
    def _resolve_retry_delay(response: requests.Response | Any, attempt: int) -> int:
        retry_after = getattr(response, "headers", {}).get("Retry-After")
        if retry_after:
            try:
                return max(int(retry_after), 1)
            except ValueError:
                pass
        return 5 * (2**attempt)

    def _parse_results(
        self, results: list[dict[str, Any]], now: datetime
    ) -> list[PaperRecord]:
        records: list[PaperRecord] = []

        for item in results:
            created_at = self._parse_created_date(str(item.get("created_date", "")))
            if created_at is None:
                continue
            if not within_lookback_window(created_at, self.lookback_hours, now=now):
                continue

            title = " ".join(str(item.get("title", "")).split())
            authors = [
                " ".join(str(authorship.get("author", {}).get("display_name", "")).split())
                for authorship in item.get("authorships", [])
                if str(authorship.get("author", {}).get("display_name", "")).strip()
            ]
            abstract = self._rebuild_abstract(item.get("abstract_inverted_index"))
            doi = self._normalize_doi(item.get("doi") or item.get("ids", {}).get("doi"))
            landing_url = (
                str(item.get("primary_location", {}).get("landing_page_url", "")).strip()
                or str(item.get("id", "")).strip()
            )
            is_open_access = bool(item.get("open_access", {}).get("is_oa"))

            records.append(
                PaperRecord(
                    paper_id=doi or build_paper_fingerprint(title=title, authors=authors),
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    doi=doi,
                    source=self.source_name,
                    published_at=created_at,
                    landing_url=landing_url,
                    pdf_url=None,
                    access="open" if is_open_access else "subscription",
                )
            )

        return records

    @staticmethod
    def _parse_created_date(value: str) -> datetime | None:
        if not value:
            return None
        if "T" in value:
            return parse_utc_datetime(value)
        return datetime.fromisoformat(value).replace(tzinfo=UTC)

    @staticmethod
    def _normalize_doi(value: object) -> str | None:
        if value is None:
            return None
        doi = str(value).strip()
        if not doi:
            return None
        return doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/")

    @staticmethod
    def _rebuild_abstract(inverted_index: object) -> str:
        if not isinstance(inverted_index, dict) or not inverted_index:
            return ""

        positions: dict[int, str] = {}
        for token, indexes in inverted_index.items():
            if not isinstance(indexes, list):
                continue
            for index in indexes:
                if isinstance(index, int):
                    positions[index] = str(token)

        if not positions:
            return ""

        return " ".join(positions[index] for index in sorted(positions))
