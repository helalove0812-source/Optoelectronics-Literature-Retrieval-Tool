from paper_crawler.fetchers.unpaywall import UnpaywallClient


class DummyResponse:
    def __init__(self, payload: dict[str, object]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class DummySession:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload
        self.calls: list[tuple[str, dict[str, object], int]] = []

    def get(self, url: str, params: dict[str, object], timeout: int) -> DummyResponse:
        self.calls.append((url, params, timeout))
        return DummyResponse(self.payload)


def test_unpaywall_lookup_returns_oa_fields() -> None:
    session = DummySession(
        {
            "is_oa": True,
            "best_oa_location": {
                "url": "https://repository.example.com/landing",
                "url_for_pdf": "https://repository.example.com/paper.pdf",
            },
        }
    )
    client = UnpaywallClient(contact_email="team@example.com", session=session)

    result = client.lookup("10.1000/example")

    assert result == {
        "is_oa": True,
        "pdf_url": "https://repository.example.com/paper.pdf",
        "landing_url": "https://repository.example.com/landing",
    }
    assert session.calls[0][0] == "https://api.unpaywall.org/v2/10.1000/example"
    assert session.calls[0][1] == {"email": "team@example.com"}
    assert session.calls[0][2] == 30


def test_unpaywall_lookup_returns_subscription_fields() -> None:
    client = UnpaywallClient(
        contact_email="team@example.com",
        session=DummySession({"is_oa": False, "best_oa_location": None}),
    )

    result = client.lookup("10.1000/subscription")

    assert result == {
        "is_oa": False,
        "pdf_url": None,
        "landing_url": None,
    }
