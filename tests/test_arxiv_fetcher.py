from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import requests

from paper_crawler.fetchers.arxiv import ArxivFetcher
from paper_crawler.fetchers.base import FetchResult


class DummyResponse:
    def __init__(self, text: str, error: Exception | None = None):
        self.text = text
        self._error = error

    def raise_for_status(self) -> None:
        if self._error is not None:
            raise self._error
        return None


class DummySession:
    def __init__(self, payload: str):
        self.payload = payload
        self.calls: list[tuple[str, dict[str, object], int]] = []

    def get(self, url: str, params: dict[str, object], timeout: int) -> DummyResponse:
        self.calls.append((url, params, timeout))
        return DummyResponse(self.payload)


class SequenceSession:
    def __init__(self, responses: list[DummyResponse]):
        self._responses = responses
        self.calls: list[tuple[str, dict[str, object], int]] = []

    def get(self, url: str, params: dict[str, object], timeout: int) -> DummyResponse:
        self.calls.append((url, params, timeout))
        return self._responses[len(self.calls) - 1]


class TooManyRequestsError(requests.HTTPError):
    def __init__(self):
        super().__init__("429 Too Many Requests")
        self.response = SimpleNamespace(status_code=429)


def test_fetch_result_defaults_to_empty_records_and_source() -> None:
    result = FetchResult()

    assert result.records == []
    assert result.source == ""


def test_arxiv_fetcher_parses_recent_entries() -> None:
    feed = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2506.00001v1</id>
        <published>2026-06-03T10:00:00Z</published>
        <title> Silicon Photonics for Coherent Links </title>
        <summary>Recent progress in coherent links.</summary>
        <author><name>Alice Smith</name></author>
        <author><name>Bob Chen</name></author>
        <link rel="alternate" href="http://arxiv.org/abs/2506.00001v1" />
        <link title="pdf" href="http://arxiv.org/pdf/2506.00001v1" />
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2505.99999v1</id>
        <published>2026-05-31T10:00:00Z</published>
        <title>Old Paper</title>
        <summary>Too old.</summary>
        <author><name>Older Author</name></author>
        <link rel="alternate" href="http://arxiv.org/abs/2505.99999v1" />
      </entry>
    </feed>"""

    session = DummySession(feed)
    fetcher = ArxivFetcher(
        categories=["physics.optics"],
        session=session,
        sleep_func=lambda _: None,
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    result = fetcher.fetch()

    assert result.source == "arxiv"
    assert len(result.records) == 1
    paper = result.records[0]
    assert paper.source == "arxiv"
    assert paper.title == "Silicon Photonics for Coherent Links"
    assert paper.authors == ["Alice Smith", "Bob Chen"]
    assert paper.access == "open"
    assert paper.pdf_url == "http://arxiv.org/pdf/2506.00001v1"
    assert paper.landing_url == "http://arxiv.org/abs/2506.00001v1"
    assert session.calls[0][1]["search_query"] == "cat:physics.optics"


def test_arxiv_fetcher_sleeps_between_categories() -> None:
    feed = """<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>"""
    sleeps: list[int] = []

    fetcher = ArxivFetcher(
        categories=["physics.optics", "physics.app-ph"],
        session=DummySession(feed),
        sleep_func=lambda seconds: sleeps.append(seconds),
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    fetcher.fetch()

    assert sleeps == [3]


def test_arxiv_fetcher_retries_on_429_with_backoff_and_succeeds() -> None:
    feed = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2506.00001v1</id>
        <published>2026-06-03T10:00:00Z</published>
        <title> Retry Eventually Works </title>
        <summary>Recovered after rate limit.</summary>
        <author><name>Alice Smith</name></author>
        <link rel="alternate" href="http://arxiv.org/abs/2506.00001v1" />
      </entry>
    </feed>"""
    sleeps: list[int] = []
    session = SequenceSession(
        [
            DummyResponse("", error=TooManyRequestsError()),
            DummyResponse("", error=TooManyRequestsError()),
            DummyResponse(feed),
        ]
    )
    fetcher = ArxivFetcher(
        categories=["physics.optics"],
        session=session,
        sleep_func=lambda seconds: sleeps.append(seconds),
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    result = fetcher.fetch()

    assert len(result.records) == 1
    assert len(session.calls) == 3
    assert sleeps == [3, 6]


def test_arxiv_fetcher_raises_after_exceeding_429_retry_limit() -> None:
    sleeps: list[int] = []
    session = SequenceSession(
        [
            DummyResponse("", error=TooManyRequestsError()),
            DummyResponse("", error=TooManyRequestsError()),
            DummyResponse("", error=TooManyRequestsError()),
            DummyResponse("", error=TooManyRequestsError()),
        ]
    )
    fetcher = ArxivFetcher(
        categories=["physics.optics"],
        session=session,
        sleep_func=lambda seconds: sleeps.append(seconds),
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(requests.HTTPError, match="429"):
        fetcher.fetch()

    assert len(session.calls) == 4
    assert sleeps == [3, 6, 12]
