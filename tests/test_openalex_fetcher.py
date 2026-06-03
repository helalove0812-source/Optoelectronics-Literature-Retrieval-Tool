from datetime import UTC, datetime

from paper_crawler.fetchers.openalex import OpenAlexFetcher


class DummyResponse:
    def __init__(self, payload: dict[str, object]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class DummySession:
    def __init__(self, payloads: list[dict[str, object]]):
        self._payloads = payloads
        self.calls: list[tuple[str, dict[str, object], int]] = []

    def get(self, url: str, params: dict[str, object], timeout: int) -> DummyResponse:
        self.calls.append((url, params, timeout))
        return DummyResponse(self._payloads[len(self.calls) - 1])


def test_openalex_fetcher_parses_recent_results_and_builds_query_params() -> None:
    session = DummySession(
        [
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
    assert session.calls[0][1]["per-page"] == 200
    assert session.calls[0][1]["filter"] == "concepts.id:C123,from_created_date:2026-06-02"


def test_openalex_fetcher_rebuilds_abstract_and_filters_plain_date_by_lookback() -> None:
    session = DummySession(
        [
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
