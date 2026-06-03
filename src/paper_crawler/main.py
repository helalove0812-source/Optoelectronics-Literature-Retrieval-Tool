from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from paper_crawler.notify.email_renderer import render_email_summary
from paper_crawler.notify.smtp_sender import SMTPConfig, send_email
from paper_crawler.processing import PipelineResult, run_pipeline
from paper_crawler.settings import Settings, load_settings
from paper_crawler.storage import (
    PushLogRepository,
    connect_sqlite,
    initialize_database,
    resolve_sqlite_path,
)


def run_application(
    config_dir: Path,
    settings_loader: Callable[[Path], Settings] = load_settings,
    pipeline_runner: Callable[[Settings], PipelineResult] = run_pipeline,
    email_renderer: Callable[[list], str] = render_email_summary,
    email_sender: Callable[[SMTPConfig, str, str], None] = send_email,
    smtp_password_getter: Callable[[], str | None] = lambda: os.getenv("SMTP_PASSWORD"),
    now_func: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    settings = settings_loader(config_dir)
    result = pipeline_runner(settings)
    db_path = resolve_sqlite_path(settings.database_url)
    initialize_database(db_path)

    with connect_sqlite(db_path) as connection:
        push_log = PushLogRepository(connection)
        to_push = [
            record
            for record in result.matched_records
            if not push_log.has_been_pushed(record.paper_id)
        ]

        email_sent = "no"
        if to_push:
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
