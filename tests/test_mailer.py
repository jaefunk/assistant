from assistant.mailer import MailConfig, build_message

ENV = {
    "SMTP_USER": "me@example.com",
    "SMTP_PASSWORD": "secret",
    "MAIL_TO": "a@example.com, b@example.com",
}


def test_from_env_parses_recipients() -> None:
    config = MailConfig.from_env(ENV)
    assert config is not None
    assert config.to == ("a@example.com", "b@example.com")
    assert config.sender == "me@example.com"
    assert (config.host, config.port) == ("smtp.gmail.com", 587)


def test_from_env_missing_returns_none() -> None:
    assert MailConfig.from_env({"SMTP_USER": "x"}) is None


def test_build_message_has_text_and_html() -> None:
    config = MailConfig.from_env(ENV)
    assert config is not None
    msg = build_message("제목", "# 리포트\n\n- [A](https://x/a)\n", config)
    assert msg["Subject"] == "제목"
    assert msg["To"] == "a@example.com, b@example.com"
    parts = {part.get_content_type(): part.get_content() for part in msg.iter_parts()}
    assert "# 리포트" in parts["text/plain"]
    assert '<a href="https://x/a">A</a>' in parts["text/html"]


def test_from_env_blank_values_use_defaults() -> None:
    config = MailConfig.from_env({**ENV, "SMTP_HOST": "", "SMTP_PORT": "", "MAIL_FROM": ""})
    assert config is not None
    assert (config.host, config.port, config.sender) == ("smtp.gmail.com", 587, "me@example.com")


class _FakeSMTP:
    calls: list[str] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.calls.append(f"connect {host}:{port}")

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.calls.append("quit")

    def starttls(self) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login {user}")

    def send_message(self, msg) -> None:
        self.calls.append(f"send {msg['Subject']} -> {msg['To']}")


def test_send_uses_starttls_on_587(monkeypatch) -> None:
    import smtplib

    from assistant.mailer import send

    _FakeSMTP.calls = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    config = MailConfig.from_env(ENV)
    assert config is not None
    send("제목", "본문", config)
    assert _FakeSMTP.calls == [
        "connect smtp.gmail.com:587",
        "starttls",
        "login me@example.com",
        "send 제목 -> a@example.com, b@example.com",
        "quit",
    ]
