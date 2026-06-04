from datetime import UTC, datetime

from paper_crawler.fetchers.tavily import TavilyFetcher


class DummyResponse:
    def __init__(self, payload: dict[str, object]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class DummySession:
    def __init__(self, payload: dict[str, object]):
        self._payload = payload
        self.calls: list[tuple[str, dict[str, object], int]] = []

    def post(self, url: str, json: dict[str, object], timeout: int) -> DummyResponse:
        self.calls.append((url, json, timeout))
        return DummyResponse(self._payload)


def test_tavily_fetcher_builds_compact_topic_query_and_maps_result() -> None:
    session = DummySession(
        {
            "results": [
                {
                    "title": "Integrated photonics paper with DOI",
                    "url": "https://example.com/paper",
                    "content": "A recent paper about integrated photonics and sensing.",
                    "published_date": "2026-06-04T08:00:00Z",
                }
            ]
        }
    )
    fetcher = TavilyFetcher(
        api_key="test-key",
        keyword_groups={
            "光计算": ["integrated photonics", "optical sensing", "optical computing"]
        },
        max_results=5,
        session=session,
        now_func=lambda: datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
    )

    records = fetcher.fetch().records

    assert session.calls[0][0] == "https://api.tavily.com/search"
    assert session.calls[0][1]["query"] == (
        "integrated photonics optical sensing optical computing paper arxiv doi"
    )
    assert session.calls[0][1]["max_results"] == 5
    assert records[0].source == "tavily"
    assert records[0].title == "Integrated photonics paper with DOI"
    assert records[0].landing_url == "https://example.com/paper"
    assert records[0].abstract.startswith("A recent paper")
    assert records[0].access == "subscription"


def test_tavily_fetcher_uses_doi_as_paper_id_and_falls_back_to_fingerprint() -> None:
    session = DummySession(
        {
            "results": [
                {
                    "title": "First result",
                    "url": "https://doi.org/10.1000/example",
                    "content": "Snippet with DOI 10.1000/example inside.",
                },
                {
                    "title": "Second result without doi",
                    "url": "https://example.com/no-doi",
                    "content": "No DOI here.",
                },
            ]
        }
    )
    fetcher = TavilyFetcher(
        api_key="test-key",
        keyword_groups={"机器人": ["motion planning", "embodied ai", "vla"]},
        session=session,
        now_func=lambda: datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
    )

    records = fetcher.fetch().records

    assert records[0].doi == "10.1000/example"
    assert records[0].paper_id == "10.1000/example"
    assert records[1].doi is None
    assert "::unknown" in records[1].paper_id


def test_tavily_fetcher_uses_now_when_result_has_no_parseable_date() -> None:
    now = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
    session = DummySession(
        {
            "results": [
                {
                    "title": "Undated result",
                    "url": "https://example.com/undated",
                    "content": "Snippet only.",
                }
            ]
        }
    )
    fetcher = TavilyFetcher(
        api_key="test-key",
        keyword_groups={"光学": ["integrated photonics"]},
        session=session,
        now_func=lambda: now,
    )

    records = fetcher.fetch().records

    assert records[0].published_at == now


def test_tavily_fetcher_returns_empty_fetch_result_when_api_returns_no_results() -> None:
    session = DummySession({"results": []})
    fetcher = TavilyFetcher(
        api_key="test-key",
        keyword_groups={"光学": ["integrated photonics"]},
        session=session,
    )

    result = fetcher.fetch()

    assert result.source == "tavily"
    assert result.records == []
