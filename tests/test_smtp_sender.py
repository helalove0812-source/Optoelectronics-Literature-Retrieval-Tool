from paper_crawler.notify.smtp_sender import SMTPConfig, send_email


class DummySMTP:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.started_tls = False
        self.logged_in = None
        self.sent_messages = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.logged_in = (username, password)

    def send_message(self, message) -> None:
        self.sent_messages.append(message)


def test_send_email_uses_starttls_for_non_465_port() -> None:
    dummy_smtp = DummySMTP("smtp.example.com", 587)
    config = SMTPConfig(
        host="smtp.example.com",
        port=587,
        username="research-alert@example.com",
        password="secret",
        from_address="research-alert@example.com",
        to_address="user@example.com",
        use_tls=True,
    )

    send_email(
        config=config,
        subject="Daily paper digest",
        body="Matched papers: 1",
        smtp_factory=lambda host, port: dummy_smtp,
    )

    assert dummy_smtp.started_tls is True
    assert dummy_smtp.logged_in == ("research-alert@example.com", "secret")
    assert len(dummy_smtp.sent_messages) == 1
    assert dummy_smtp.sent_messages[0]["Subject"] == "Daily paper digest"


def test_send_email_uses_ssl_for_port_465() -> None:
    plain_smtp_calls: list[tuple[str, int]] = []
    ssl_smtp = DummySMTP("smtp.qq.com", 465)

    config = SMTPConfig(
        host="smtp.qq.com",
        port=465,
        username="sender@qq.com",
        password="secret",
        from_address="sender@qq.com",
        to_address="receiver@example.com",
        use_tls=True,
    )

    send_email(
        config=config,
        subject="SSL mail",
        body="body",
        smtp_factory=lambda host, port: plain_smtp_calls.append((host, port)),
        smtp_ssl_factory=lambda host, port: ssl_smtp,
    )

    assert plain_smtp_calls == []
    assert ssl_smtp.started_tls is False
    assert ssl_smtp.logged_in == ("sender@qq.com", "secret")
    assert len(ssl_smtp.sent_messages) == 1
    assert ssl_smtp.sent_messages[0]["Subject"] == "SSL mail"
