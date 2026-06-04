from datetime import UTC, datetime

import pytest
import requests

from paper_crawler.fetchers.openalex import OpenAlexFetcher


class DummyResponse:
    def __init__(
        self,
        payload: dict[str, object],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            response.headers.update(self.headers)
            raise requests.HTTPError(f"{self.status_code} error", response=response)
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class DummySession:
    def __init__(self, responses: list[DummyResponse]):
        self._responses = responses
        self.calls: list[tuple[str, dict[str, object], int]] = []

    def get(self, url: str, params: dict[str, object], timeout: int) -> DummyResponse:
        self.calls.append((url, params, timeout))
        return self._responses[len(self.calls) - 1]


def test_openalex_fetcher_parses_recent_results_and_builds_query_params() -> None:
    session = DummySession(
        [
            DummyResponse(
                {
                    "results": [
                        {
                            "id": "https://openalex.org/W123",
                            "title": " Integrated photonics for coherent links ",
                            "doi": "https://doi.org/10.1000/example",
                            "created_date": "2026-06-03T10:00:00Z",
                            "abstract_inverted_index": {
                                "Recent": [0],
                                "progress": [1],
                                "in": [2],
                                "coherent": [3],
                                "links.": [4],
                            },
                            "authorships": [
                                {"author": {"display_name": "Alice Smith"}},
                                {"author": {"display_name": "Bob Chen"}},
                            ],
                            "primary_location": {
                                "landing_page_url": "https://example.com/paper"
                            },
                            "open_access": {"is_oa": True},
                        },
                        {
                            "id": "https://openalex.org/W456",
                            "title": "Old paper",
                            "created_date": "2026-06-01T10:00:00Z",
                            "abstract_inverted_index": {"Too": [0], "old.": [1]},
                            "authorships": [
                                {"author": {"display_name": "Older Author"}},
                            ],
                            "open_access": {"is_oa": False},
                        },
                    ]
                }
            )
        ]
    )
    fetcher = OpenAlexFetcher(
        filters=["concepts.id:C123"],
        contact_email="team@example.com",
        lookback_hours=24,
        session=session,
        sleep_func=lambda _: None,
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    result = fetcher.fetch()

    assert result.source == "openalex"
    assert len(result.records) == 1
    paper = result.records[0]
    assert paper.paper_id == "10.1000/example"
    assert paper.doi == "10.1000/example"
    assert paper.title == "Integrated photonics for coherent links"
    assert paper.authors == ["Alice Smith", "Bob Chen"]
    assert paper.abstract == "Recent progress in coherent links."
    assert paper.landing_url == "https://example.com/paper"
    assert paper.access == "open"
    assert paper.pdf_url is None
    assert paper.published_at == datetime(2026, 6, 3, 10, 0, tzinfo=UTC)
    assert session.calls[0][0] == "https://api.openalex.org/works"
    assert session.calls[0][1]["mailto"] == "team@example.com"
    assert session.calls[0][1]["per-page"] == 100
    assert session.calls[0][1]["filter"] == "concepts.id:C123,from_created_date:2026-06-02"


def test_openalex_fetcher_rebuilds_abstract_and_filters_plain_date_by_lookback() -> None:
    session = DummySession(
        [
            DummyResponse(
                {
                    "results": [
                        {
                            "id": "https://openalex.org/W123",
                            "title": "Within window",
                            "created_date": "2026-06-03",
                            "abstract_inverted_index": {
                                "Photonics": [0],
                                "advances": [1, 3],
                                "need": [2],
                            },
                            "authorships": [],
                            "open_access": {"is_oa": False},
                        },
                        {
                            "id": "https://openalex.org/W999",
                            "title": "Outside window",
                            "created_date": "2026-06-02",
                            "abstract_inverted_index": {"Old": [0]},
                            "authorships": [],
                            "open_access": {"is_oa": False},
                        },
                    ]
                }
            )
        ]
    )
    fetcher = OpenAlexFetcher(
        filters=["institutions.id:I123"],
        contact_email="team@example.com",
        lookback_hours=24,
        session=session,
        sleep_func=lambda _: None,
        now_func=lambda: datetime(2026, 6, 3, 20, 0, tzinfo=UTC),
    )

    result = fetcher.fetch()

    assert [record.title for record in result.records] == ["Within window"]
    assert result.records[0].abstract == "Photonics advances need advances"


def test_openalex_fetcher_retries_429_with_retry_after_header() -> None:
    sleep_calls: list[int] = []
    session = DummySession(
        [
            DummyResponse(
                payload={},
                status_code=429,
                headers={
                    "Retry-After": "7",
                    "X-RateLimit-Limit": "100000",
                    "X-RateLimit-Remaining": "0",
                },
            ),
            DummyResponse({"results": []}),
        ]
    )
    fetcher = OpenAlexFetcher(
        filters=["concepts.id:C123"],
        contact_email="team@example.com",
        session=session,
        sleep_func=sleep_calls.append,
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    result = fetcher.fetch()

    assert result.records == []
    assert len(session.calls) == 2
    assert sleep_calls == [7]


def test_openalex_fetcher_retries_429_with_exponential_backoff() -> None:
    sleep_calls: list[int] = []
    session = DummySession(
        [
            DummyResponse(payload={}, status_code=429),
            DummyResponse(payload={}, status_code=429),
            DummyResponse(payload={}, status_code=429),
            DummyResponse({"results": []}),
        ]
    )
    fetcher = OpenAlexFetcher(
        filters=["concepts.id:C123"],
        contact_email="team@example.com",
        session=session,
        sleep_func=sleep_calls.append,
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    result = fetcher.fetch()

    assert result.records == []
    assert len(session.calls) == 4
    assert sleep_calls == [5, 10, 20]


def test_openalex_fetcher_raises_after_exhausting_429_retries() -> None:
    sleep_calls: list[int] = []
    session = DummySession(
        [
            DummyResponse(payload={}, status_code=429),
            DummyResponse(payload={}, status_code=429),
            DummyResponse(payload={}, status_code=429),
            DummyResponse(payload={}, status_code=429),
        ]
    )
    fetcher = OpenAlexFetcher(
        filters=["concepts.id:C123"],
        contact_email="team@example.com",
        session=session,
        sleep_func=sleep_calls.append,
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(requests.HTTPError):
        fetcher.fetch()

    assert len(session.calls) == 4
    assert sleep_calls == [5, 10, 20]


def test_openalex_fetcher_does_not_retry_non_429_http_error() -> None:
    sleep_calls: list[int] = []
    session = DummySession([DummyResponse(payload={}, status_code=500)])
    fetcher = OpenAlexFetcher(
        filters=["concepts.id:C123"],
        contact_email="team@example.com",
        session=session,
        sleep_func=sleep_calls.append,
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(requests.HTTPError):
        fetcher.fetch()

    assert len(session.calls) == 1
    assert sleep_calls == []
