from __future__ import annotations

from paper_crawler.models import PaperRecord


def render_email_summary(records: list[PaperRecord]) -> str:
    lines = [
        "# 今日光电子相关论文摘要",
        "",
        f"共 {len(records)} 篇新论文。",
        "",
    ]

    for index, record in enumerate(records, start=1):
        lines.extend(
            [
                f"## {index}. {record.title}",
                f"Authors: {', '.join(record.authors)}",
                f"Source: {record.source}",
                f"Published At: {record.published_at.isoformat()}",
                f"DOI: {record.doi or 'N/A'}",
                f"Matched Keywords: {', '.join(record.matched_keywords) or 'N/A'}",
                f"Access: {record.access}",
                f"Landing URL: {record.landing_url}",
                f"PDF URL: {record.pdf_url or '需订阅'}",
                f"Abstract: {record.abstract or 'N/A'}",
                "",
            ]
        )

    return "\n".join(lines).strip()
