from datetime import UTC, datetime

from paper_crawler.models import PaperRecord
from paper_crawler.notify.email_renderer import render_email_summary


def test_render_email_summary_renders_single_record() -> None:
    record = PaperRecord(
        paper_id="paper-1",
        title="Silicon photonics coherent transceiver",
        authors=["Alice Smith", "Bob Chen"],
        abstract="A compact coherent transceiver for datacenter optics.",
        doi="10.1000/example",
        source="crossref",
        published_at=datetime(2026, 6, 3, 10, 0, tzinfo=UTC),
        landing_url="https://doi.org/10.1000/example",
        pdf_url="https://example.com/paper.pdf",
        access="open",
        matched_keywords=["硅光"],
    )

    body = render_email_summary([record])

    assert "# 今日光电子相关论文摘要" in body
    assert "共 1 篇新论文" in body
    assert "Silicon photonics coherent transceiver" in body
    assert "Alice Smith, Bob Chen" in body
    assert "Matched Keywords: 硅光" in body
    assert "PDF URL: https://example.com/paper.pdf" in body


def test_render_email_summary_renders_subscription_marker() -> None:
    record = PaperRecord(
        paper_id="paper-2",
        title="Battery chemistry advances",
        authors=["Carol Zhang"],
        abstract="Electrochemistry only.",
        doi=None,
        source="openalex",
        published_at=datetime(2026, 6, 3, 11, 0, tzinfo=UTC),
        landing_url="https://openalex.org/W123",
        pdf_url=None,
        access="subscription",
        matched_keywords=["其他"],
    )

    body = render_email_summary([record])

    assert "Access: subscription" in body
    assert "PDF URL: 需订阅" in body
