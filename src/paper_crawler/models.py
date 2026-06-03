from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class PaperRecord:
    paper_id: str
    title: str
    authors: list[str]
    abstract: str
    doi: str | None
    source: str
    published_at: datetime
    landing_url: str
    pdf_url: str | None = None
    access: str = "subscription"
    matched_keywords: list[str] = field(default_factory=list)
    semantic_score: float | None = None
