import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from paper_crawler.models import PaperRecord


@dataclass(slots=True)
class RunSummary:
    fetched_count: int = 0
    matched_count: int = 0
    status: str = "success"


class PaperRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert_or_ignore(self, record: PaperRecord) -> bool:
        cursor = self._connection.execute(
            """
            INSERT OR IGNORE INTO papers (
                paper_id,
                title,
                authors_json,
                abstract,
                doi,
                source,
                published_at,
                landing_url,
                pdf_url,
                access,
                matched_keywords_json,
                semantic_score,
                zh_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.paper_id,
                record.title,
                json.dumps(record.authors, ensure_ascii=False),
                record.abstract,
                record.doi,
                record.source,
                record.published_at.isoformat(),
                record.landing_url,
                record.pdf_url,
                record.access,
                json.dumps(record.matched_keywords, ensure_ascii=False),
                record.semantic_score,
                record.zh_summary,
            ),
        )
        return cursor.rowcount == 1

    def update_zh_summary(self, paper_id: str, zh_summary: str) -> None:
        self._connection.execute(
            "UPDATE papers SET zh_summary = ? WHERE paper_id = ?",
            (zh_summary, paper_id),
        )


class PushLogRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def has_been_pushed(self, paper_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM push_log WHERE paper_id = ? LIMIT 1",
            (paper_id,),
        ).fetchone()
        return row is not None

    def mark_pushed(
        self,
        paper_id: str,
        pushed_at: datetime,
        channel: str,
    ) -> None:
        self._connection.execute(
            "INSERT INTO push_log (paper_id, pushed_at, channel) VALUES (?, ?, ?)",
            (paper_id, pushed_at.isoformat(), channel),
        )
