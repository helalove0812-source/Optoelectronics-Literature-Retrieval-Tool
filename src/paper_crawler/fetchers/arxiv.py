from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Callable, Protocol
from xml.etree import ElementTree

import requests

from paper_crawler.fetchers.base import BaseFetcher, FetchResult
from paper_crawler.models import PaperRecord
from paper_crawler.utils.fingerprint import build_paper_fingerprint
from paper_crawler.utils.time_utils import parse_utc_datetime, utc_now, within_lookback_window

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ATOM_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}


class SupportsGet(Protocol):
    def get(self, url: str, params: dict[str, object], timeout: int): ...


@dataclass(slots=True)
class ArxivFetcher(BaseFetcher):
    categories: list[str]
    max_results: int = 100
    lookback_hours: int = 24
    request_timeout: int = 30
    request_interval_seconds: int = 3
    max_429_retries: int = 3
    session: SupportsGet | requests.Session | None = None
    sleep_func: Callable[[int], None] = sleep
    now_func: Callable[[], object] = utc_now
    source_name: str = "arxiv"

    def fetch(self) -> FetchResult:
        session = self.session or requests.Session()
        now = self.now_func()
        records: list[PaperRecord] = []

        for index, category in enumerate(self.categories):
            if index > 0:
                self.sleep_func(self.request_interval_seconds)

            response = self._get_with_429_retry(
                session=session,
                params={
                    "search_query": f"cat:{category}",
                    "start": 0,
                    "max_results": min(self.max_results, 100),
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                },
            )
            records.extend(
                self._parse_records(xml_text=response.text, now=now),
            )

        return FetchResult(source=self.source_name, records=records)

    def _get_with_429_retry(
        self, session: SupportsGet | requests.Session, params: dict[str, object]
    ):
        for retry_count in range(self.max_429_retries + 1):
            response = session.get(
                ARXIV_API_URL,
                params=params,
                timeout=self.request_timeout,
            )
            try:
                response.raise_for_status()
                return response
            except requests.HTTPError as exc:
                status_code = getattr(exc.response, "status_code", None)
                if status_code != 429 or retry_count >= self.max_429_retries:
                    raise
                backoff_seconds = self.request_interval_seconds * (2**retry_count)
                self.sleep_func(backoff_seconds)

        raise RuntimeError("unreachable")

    def _parse_records(self, xml_text: str, now: object) -> list[PaperRecord]:
        root = ElementTree.fromstring(xml_text)
        records: list[PaperRecord] = []

        for entry in root.findall("atom:entry", ATOM_NAMESPACE):
            published_at = parse_utc_datetime(
                self._read_text(entry, "atom:published"),
            )
            if not within_lookback_window(published_at, self.lookback_hours, now=now):
                continue

            title = " ".join(self._read_text(entry, "atom:title").split())
            abstract = " ".join(self._read_text(entry, "atom:summary").split())
            authors = [
                " ".join(author_name.split())
                for author_name in self._read_author_names(entry)
            ]
            landing_url = self._read_link(entry, rel="alternate") or self._read_text(
                entry, "atom:id"
            )
            pdf_url = self._read_link(entry, title="pdf")

            records.append(
                PaperRecord(
                    paper_id=build_paper_fingerprint(title=title, authors=authors),
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    doi=None,
                    source=self.source_name,
                    published_at=published_at,
                    landing_url=landing_url,
                    pdf_url=pdf_url,
                    access="open",
                )
            )

        return records

    @staticmethod
    def _read_text(entry: ElementTree.Element, path: str) -> str:
        node = entry.find(path, ATOM_NAMESPACE)
        return (node.text or "") if node is not None else ""

    @staticmethod
    def _read_author_names(entry: ElementTree.Element) -> list[str]:
        return [
            (node.text or "")
            for node in entry.findall("atom:author/atom:name", ATOM_NAMESPACE)
        ]

    @staticmethod
    def _read_link(
        entry: ElementTree.Element, rel: str | None = None, title: str | None = None
    ) -> str | None:
        for link in entry.findall("atom:link", ATOM_NAMESPACE):
            if rel is not None and link.attrib.get("rel") != rel:
                continue
            if title is not None and link.attrib.get("title") != title:
                continue
            href = link.attrib.get("href")
            if href:
                return href
        return None
