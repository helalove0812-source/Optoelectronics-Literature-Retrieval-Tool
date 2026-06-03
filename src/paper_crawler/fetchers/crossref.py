from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import sleep
from typing import Any, Callable, Protocol

import requests

from paper_crawler.fetchers.base import BaseFetcher, FetchResult
from paper_crawler.models import PaperRecord
from paper_crawler.utils.fingerprint import build_paper_fingerprint
from paper_crawler.utils.time_utils import parse_utc_datetime, utc_now, within_lookback_window

CROSSREF_API_URL = "https://api.crossref.org/works"


class SupportsGet(Protocol):
    def get(self, url: str, params: dict[str, object], timeout: int): ...


@dataclass(slots=True)
class CrossrefFetcher(BaseFetcher):
    issn_whitelist: dict[str, dict[str, Any]]
    contact_email: str
    lookback_hours: int = 24
    rows: int = 100
    request_timeout: int = 30
    request_interval_seconds: int = 1
    session: SupportsGet | requests.Session | None = None
    sleep_func: Callable[[int], None] = sleep
    now_func: Callable[[], datetime] = utc_now
    source_name: str = "crossref"

    def fetch(self) -> FetchResult:
        session = self.session or requests.Session()
        now = self.now_func()
        from_index_date = (now - timedelta(hours=self.lookback_hours)).date().isoformat()
        records: list[PaperRecord] = []

        for index, journal in enumerate(self.issn_whitelist.values()):
            if index > 0:
                self.sleep_func(self.request_interval_seconds)

            response = session.get(
                CROSSREF_API_URL,
                params={
                    "filter": (
                        f"issn:{journal['issn']},from-index-date:{from_index_date}"
                    ),
                    "rows": min(self.rows, 100),
                    "mailto": self.contact_email,
                },
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            payload = response.json()
            items = payload.get("message", {}).get("items", [])
            records.extend(self._parse_items(items=items, now=now, is_open_access=bool(journal.get("oa"))))

        return FetchResult(source=self.source_name, records=records)

    def _parse_items(
        self, items: list[dict[str, Any]], now: datetime, is_open_access: bool
    ) -> list[PaperRecord]:
        records: list[PaperRecord] = []

        for item in items:
            indexed_at = parse_utc_datetime(item["indexed"]["date-time"])
            if not within_lookback_window(indexed_at, self.lookback_hours, now=now):
                continue

            title = " ".join(str((item.get("title") or [""])[0]).split())
            authors = [
                " ".join(part for part in [author.get("given", ""), author.get("family", "")] if part)
                for author in item.get("author", [])
            ]
            abstract = self._strip_jats(item.get("abstract", "") or "")
            doi = item.get("DOI")
            landing_url = str(item.get("URL", ""))

            records.append(
                PaperRecord(
                    paper_id=str(doi or build_paper_fingerprint(title=title, authors=authors)),
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    doi=str(doi) if doi is not None else None,
                    source=self.source_name,
                    published_at=indexed_at,
                    landing_url=landing_url,
                    pdf_url=None,
                    access="open" if is_open_access else "subscription",
                )
            )

        return records

    @staticmethod
    def _strip_jats(value: str) -> str:
        return " ".join(re.sub(r"<[^>]+>", " ", value).split())
