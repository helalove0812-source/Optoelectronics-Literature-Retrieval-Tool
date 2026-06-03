from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Protocol

from paper_crawler.llm import DeepSeekClient, DeepSeekConfig
from paper_crawler.notify.email_renderer import render_email_summary
from paper_crawler.notify.smtp_sender import SMTPConfig, send_email
from paper_crawler.processing import PipelineResult, run_pipeline
from paper_crawler.settings import Settings, load_settings
from paper_crawler.storage import (
    PaperRepository,
    PushLogRepository,
    connect_sqlite,
    initialize_database,
    resolve_sqlite_path,
)

logger = logging.getLogger(__name__)


class SummaryClient(Protocol):
    def summarize_paper(
        self,
        *,
        title: str,
        abstract: str,
        matched_keywords: list[str],
    ) -> str: ...


def build_summary_client(
    settings: Settings,
    api_key_getter: Callable[[], str | None] = lambda: os.getenv("DEEPSEEK_API_KEY"),
) -> SummaryClient | None:
    if not settings.llm.enabled or settings.llm.provider != "deepseek":
        return None

    api_key = api_key_getter()
    if not api_key:
        logger.warning("LLM summary is enabled but DEEPSEEK_API_KEY is missing")
        return None

    return DeepSeekClient(
        DeepSeekConfig(
            base_url=settings.llm.base_url,
            model=settings.llm.model,
            api_key=api_key,
            timeout_seconds=settings.llm.timeout_seconds,
        )
    )


def run_application(
    config_dir: Path,
    settings_loader: Callable[[Path], Settings] = load_settings,
    pipeline_runner: Callable[[Settings], PipelineResult] = run_pipeline,
    email_renderer: Callable[[list], str] = render_email_summary,
    email_sender: Callable[[SMTPConfig, str, str], None] = send_email,
    summary_client_builder: Callable[[Settings], SummaryClient | None] = build_summary_client,
    smtp_password_getter: Callable[[], str | None] = lambda: os.getenv("SMTP_PASSWORD"),
    now_func: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    settings = settings_loader(config_dir)
    result = pipeline_runner(settings)
    db_path = resolve_sqlite_path(settings.database_url)
    initialize_database(db_path)

    with connect_sqlite(db_path) as connection:
        paper_repository = PaperRepository(connection)
        push_log = PushLogRepository(connection)
        to_push = [
            record
            for record in result.matched_records
            if not push_log.has_been_pushed(record.paper_id)
        ]
        summary_client = summary_client_builder(settings) if to_push else None

        email_sent = "no"
        if to_push:
            if summary_client is not None:
                for record in to_push:
                    if record.zh_summary:
                        continue
                    try:
                        zh_summary = summary_client.summarize_paper(
                            title=record.title,
                            abstract=record.abstract,
                            matched_keywords=record.matched_keywords,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to generate zh_summary for %s: %s",
                            record.paper_id,
                            exc,
                        )
                        continue

                    record.zh_summary = zh_summary
                    paper_repository.update_zh_summary(record.paper_id, zh_summary)
                    connection.commit()

            body = email_renderer(to_push)
            email_sender(
                SMTPConfig(
                    host=settings.smtp.host,
                    port=settings.smtp.port,
                    username=settings.smtp.username,
                    password=smtp_password_getter() or "",
                    from_address=settings.smtp.from_address,
                    to_address=settings.smtp.to_address,
                    use_tls=settings.smtp.use_tls,
                ),
                f"Daily paper digest ({len(to_push)})",
                body,
            )
            pushed_at = now_func()
            for record in to_push:
                push_log.mark_pushed(record.paper_id, pushed_at=pushed_at, channel="email")
            connection.commit()
            email_sent = "yes"

    return (
        f"Pipeline finished: fetched={result.fetched_count}, "
        f"matched={result.matched_count}, "
        f"to_push={len(to_push)}, "
        f"email_sent={email_sent}"
    )
