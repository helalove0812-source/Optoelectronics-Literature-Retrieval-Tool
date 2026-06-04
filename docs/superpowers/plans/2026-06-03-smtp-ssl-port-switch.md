# SMTP SSL Port Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 SMTP 发送器在 `465` 端口下自动使用 SSL 直连，在其他端口继续使用普通 SMTP，并在 `use_tls=true` 时执行 STARTTLS。

**Architecture:** 保持 `send_email()` 对外签名不变，只在 `smtp_sender.py` 内部根据端口自动选择连接工厂。测试继续集中在 `tests/test_smtp_sender.py`，覆盖 `587 + STARTTLS` 和 `465 + SSL` 两条路径，确保主流程无需改动即可兼容 QQ 邮箱。

**Tech Stack:** Python 3.11、pytest、smtplib、email.message、dataclasses

---

## File Map

- Modify: `src/paper_crawler/notify/smtp_sender.py`
- Modify: `tests/test_smtp_sender.py`

### Task 1: 补充 SSL 与 STARTTLS 的发送器测试

**Files:**
- Modify: `tests/test_smtp_sender.py`
- Test: `tests/test_smtp_sender.py`

- [ ] **Step 1: 写 STARTTLS 路径测试，明确 587 端口行为**

把 `tests/test_smtp_sender.py` 改成：

```python
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
```

- [ ] **Step 2: 写 SSL 路径失败测试，明确 465 端口行为**

继续在 `tests/test_smtp_sender.py` 末尾追加：

```python
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
```

- [ ] **Step 3: 运行测试确认失败**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_smtp_sender.py -q`

Expected:

```text
.F
1 failed, 1 passed
```

- [ ] **Step 4: 提交测试红灯检查点**

```bash
git diff -- tests/test_smtp_sender.py
```

Expected:

```text
出现新增 465/SSL 测试，但实现尚未支持 smtp_ssl_factory
```

### Task 2: 在发送器内部按端口自动切换连接模式

**Files:**
- Modify: `src/paper_crawler/notify/smtp_sender.py`
- Modify: `tests/test_smtp_sender.py`
- Test: `tests/test_smtp_sender.py`

- [ ] **Step 1: 写最小实现**

把 `src/paper_crawler/notify/smtp_sender.py` 改成：

```python
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
    smtp_ssl_factory: Callable[[str, int], object] = smtplib.SMTP_SSL,
) -> None:
    message = EmailMessage()
    message["From"] = config.from_address
    message["To"] = config.to_address
    message["Subject"] = subject
    message.set_content(body)

    factory = smtp_ssl_factory if config.port == 465 else smtp_factory

    with factory(config.host, config.port) as smtp:
        if config.port != 465 and config.use_tls:
            smtp.starttls()
        smtp.login(config.username, config.password)
        smtp.send_message(message)
```

- [ ] **Step 2: 运行测试确认通过**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_smtp_sender.py -q`

Expected:

```text
2 passed
```

- [ ] **Step 3: 运行回归测试确认主流程不受影响**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_smtp_sender.py tests/test_main.py -q`

Expected:

```text
8 passed
```

- [ ] **Step 4: 提交本任务**

```bash
git add src/paper_crawler/notify/smtp_sender.py tests/test_smtp_sender.py
git commit -m "feat(notify): support ssl smtp on port 465"
```

## Self-Review

- **Spec coverage:** Task 1 覆盖 `587 + STARTTLS` 与 `465 + SSL` 两条测试路径；Task 2 覆盖 `smtp_sender.py` 内部自动按端口分流，保持现有调用签名不变。
- **Placeholder scan:** 无 `TODO`、`TBD` 或模糊步骤；每一步都有明确代码、命令和预期结果。
- **Type consistency:** 统一使用 `SMTPConfig`、`send_email()`、`smtp_factory`、`smtp_ssl_factory` 这些名称，与规格中的“内部按端口自动切换”设计保持一致。
