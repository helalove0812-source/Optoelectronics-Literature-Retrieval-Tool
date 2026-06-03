import pytest

from paper_crawler.llm.deepseek_client import DeepSeekClient, DeepSeekConfig


class DummyResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class EmptyResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"choices": [{"message": {"content": "   "}}]}


def test_deepseek_client_returns_summary_and_sends_openai_payload() -> None:
    captured: dict[str, object] = {}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: int,
    ) -> DummyResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return DummyResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "这篇论文面向相干互连场景，提出了紧凑型硅光收发方案。"
                                "研究重点放在器件集成与链路实现上。"
                            )
                        }
                    }
                ]
            }
        )

    client = DeepSeekClient(
        DeepSeekConfig(
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            api_key="secret",
            timeout_seconds=30,
        ),
        http_post=fake_post,
    )

    summary = client.summarize_paper(
        title="Silicon photonics coherent transceiver",
        abstract="A compact coherent transceiver for datacenter optics.",
        matched_keywords=["硅光", "相干光通信"],
    )

    assert "紧凑型硅光收发方案" in summary
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"] == {
        "Authorization": "Bearer secret",
        "Content-Type": "application/json",
    }
    assert captured["timeout"] == 30
    assert captured["json"]["model"] == "deepseek-chat"


def test_deepseek_client_rejects_empty_summary() -> None:
    client = DeepSeekClient(
        DeepSeekConfig(
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            api_key="secret",
            timeout_seconds=30,
        ),
        http_post=lambda url, **kwargs: EmptyResponse(),
    )

    with pytest.raises(ValueError, match="empty summary"):
        client.summarize_paper(
            title="Silicon photonics coherent transceiver",
            abstract="A compact coherent transceiver for datacenter optics.",
            matched_keywords=["硅光"],
        )
