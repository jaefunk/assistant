"""리포트를 이메일로 보낸다.

SMTP 접속 정보는 환경변수로 받는다 (GitHub Actions 에서는 Secrets 로 주입).
  SMTP_HOST      기본 smtp.gmail.com
  SMTP_PORT      기본 587 (STARTTLS). 465 면 SSL 로 접속
  SMTP_USER      로그인 계정 (Gmail 주소)
  SMTP_PASSWORD  앱 비밀번호
  MAIL_TO        받는 사람. 쉼표로 여러 명 가능
  MAIL_FROM      보내는 사람. 기본은 SMTP_USER
"""

from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import markdown

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MailConfig:
    host: str
    port: int
    user: str
    password: str
    to: tuple[str, ...]
    sender: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> MailConfig | None:
        env = os.environ if env is None else env
        user = env.get("SMTP_USER", "")
        password = env.get("SMTP_PASSWORD", "")
        to = tuple(addr.strip() for addr in env.get("MAIL_TO", "").split(",") if addr.strip())
        if not (user and password and to):
            return None
        return cls(
            host=env.get("SMTP_HOST") or "smtp.gmail.com",
            port=int(env.get("SMTP_PORT") or "587"),
            user=user,
            password=password,
            to=to,
            sender=env.get("MAIL_FROM") or user,
        )


def build_message(subject: str, markdown_body: str, config: MailConfig) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.sender
    msg["To"] = ", ".join(config.to)
    msg.set_content(markdown_body)
    msg.add_alternative(_wrap_html(markdown.markdown(markdown_body)), subtype="html")
    return msg


def send(subject: str, markdown_body: str, config: MailConfig) -> None:
    msg = build_message(subject, markdown_body, config)
    if config.port == 465:
        with smtplib.SMTP_SSL(config.host, config.port, timeout=30) as smtp:
            smtp.login(config.user, config.password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(config.host, config.port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(config.user, config.password)
            smtp.send_message(msg)
    log.info("메일 발송 완료: %s -> %s", subject, ", ".join(config.to))


def _wrap_html(body: str) -> str:
    return (
        '<!doctype html><html><body style="font-family:sans-serif;line-height:1.5;'
        'max-width:720px;margin:auto;padding:16px">'
        f"{body}</body></html>"
    )
