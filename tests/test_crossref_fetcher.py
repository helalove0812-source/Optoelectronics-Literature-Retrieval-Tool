from datetime import UTC, datetime

from paper_crawler.fetchers.crossref import CrossrefFetcher


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


def test_crossref_fetcher_parses_recent_items_and_builds_query_params() -> None:
    session = DummySession(
        [
            {
                "message": {
                    "items": [
                        {
                            "title": [" Integrated photonics for coherent links "],
                            "author": [
                                {"given": "Alice", "family": "Smith"},
                                {"given": "Bob", "family": "Chen"},
                            ],
                            "DOI": "10.1000/example",
                            "URL": "https://doi.org/10.1000/example",
                            "abstract": "<jats:p>Recent progress.</jats:p>",
                            "indexed": {"date-time": "2026-06-03T10:00:00Z"},
                        },
                        {
                            "title": ["Old paper"],
                            "author": [{"given": "Old", "family": "Author"}],
                            "DOI": "10.1000/old",
                            "URL": "https://doi.org/10.1000/old",
                            "indexed": {"date-time": "2026-06-01T10:00:00Z"},
                        },
                    ]
                }
            }
        ]
    )
    fetcher = CrossrefFetcher(
        issn_whitelist={"Optics Express": {"issn": "1094-4087", "oa": True}},
        contact_email="team@example.com",
        lookback_hours=24,
        session=session,
        sleep_func=lambda _: None,
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    result = fetcher.fetch()

    assert result.source == "crossref"
    assert len(result.records) == 1
    paper = result.records[0]
    assert paper.doi == "10.1000/example"
    assert paper.title == "Integrated photonics for coherent links"
    assert paper.authors == ["Alice Smith", "Bob Chen"]
    assert paper.abstract == "Recent progress."
    assert paper.landing_url == "https://doi.org/10.1000/example"
    assert paper.access == "open"
    assert paper.published_at == datetime(2026, 6, 3, 10, 0, tzinfo=UTC)
    assert session.calls[0][0] == "https://api.crossref.org/works"
    assert session.calls[0][1]["mailto"] == "team@example.com"
    assert session.calls[0][1]["rows"] == 100
    assert session.calls[0][1]["filter"] == "issn:1094-4087,from-index-date:2026-06-02"


def test_crossref_fetcher_sleeps_between_issn_requests() -> None:
    sleeps: list[int] = []
    session = DummySession(
        [
            {"message": {"items": []}},
            {"message": {"items": []}},
        ]
    )
    fetcher = CrossrefFetcher(
        issn_whitelist={
            "Optics Express": {"issn": "1094-4087", "oa": True},
            "Photonics Research": {"issn": "2327-9125", "oa": True},
        },
        contact_email="team@example.com",
        session=session,
        sleep_func=lambda seconds: sleeps.append(seconds),
        now_func=lambda: datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    fetcher.fetch()

    assert len(session.calls) == 2
    assert sleeps == [1]
