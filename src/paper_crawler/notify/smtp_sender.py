from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Callable


@dataclass(slots=True)
class SMTPConfig:
    host: str
    port: int
    username: str
    password: str
    from_address: str
    to_address: str
    use_tls: bool = True


def send_email(
    config: SMTPConfig,
    subject: str,
    body: str,
    smtp_factory: Callable[[str, int], object] = smtplib.SMTP,
) -> None:
    message = EmailMessage()
    message["From"] = config.from_address
    message["To"] = config.to_address
    message["Subject"] = subject
    message.set_content(body)

    with smtp_factory(config.host, config.port) as smtp:
        if config.use_tls:
            smtp.starttls()
        smtp.login(config.username, config.password)
        smtp.send_message(message)
