"""새 소식이 있을 때 ntfy (https://ntfy.sh) 로 휴대폰 푸시를 보낸다.

환경변수 (GitHub Actions 에서는 Secrets / Variables 로 주입):
  NTFY_TOPIC   구독 토픽. 아는 사람은 누구나 볼 수 있으니 길고 무작위한 이름을 쓴다.
               없으면 푸시를 건너뛴다
  NTFY_SERVER  기본 https://ntfy.sh. 직접 띄운 서버면 그 주소
  NTFY_TOKEN   (선택) 서버에 접근 토큰이 필요할 때

메시지는 JSON publish 형식(POST {server} 에 {"topic", "title", "message", ...})으로 보낸다.
헤더 방식은 제목에 한글을 넣으려면 따로 인코딩해야 해서 JSON 을 쓴다.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date

import httpx

from assistant.models import InterestDigest, Item

log = logging.getLogger(__name__)

MAX_LINES = 8  # 알림 본문에 싣는 새 소식 줄 수. 나머지는 "외 N건"


@dataclass(frozen=True)
class NtfyConfig:
    server: str
    topic: str
    token: str = ""

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> NtfyConfig | None:
        env = os.environ if env is None else env
        topic = env.get("NTFY_TOPIC", "").strip()
        if not topic:
            return None
        return cls(
            server=(env.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/"),
            topic=topic,
            token=env.get("NTFY_TOKEN", "").strip(),
        )


def build_push(digests: list[InterestDigest], report_date: date) -> tuple[str, str] | None:
    """(제목, 본문). 새 소식(standing 이 아닌 항목)이 하나도 없으면 None."""
    news = [(d.interest.name, i) for d in digests for i in d.items if not i.standing]
    if not news:
        return None
    title = f"{report_date:%m/%d} 새 소식 {len(news)}건"
    lines = [_line(name, item, multi=len(digests) > 1) for name, item in news[:MAX_LINES]]
    if len(news) > MAX_LINES:
        lines.append(f"외 {len(news) - MAX_LINES}건")
    return title, "\n".join(lines)


def _line(interest_name: str, item: Item, multi: bool) -> str:
    when = f" ({item.event_date:%m.%d})" if item.event_date else ""
    prefix = f"[{interest_name}] " if multi else ""
    return f"{prefix}{item.title}{when}"


def send(
    title: str,
    message: str,
    config: NtfyConfig,
    click: str = "",
    client: httpx.Client | None = None,
) -> None:
    payload: dict[str, object] = {
        "topic": config.topic,
        "title": title,
        "message": message,
        "tags": ["bell"],
    }
    if click:
        payload["click"] = click
    headers = {"Authorization": f"Bearer {config.token}"} if config.token else {}
    own = client is None
    client = client or httpx.Client(timeout=20.0)
    try:
        response = client.post(config.server, json=payload, headers=headers)
        response.raise_for_status()
    finally:
        if own:
            client.close()
    log.info("ntfy 푸시 발송: %s", title)


def report_url(report_date: date, env: dict[str, str] | None = None) -> str:
    """GitHub Actions 안이면 커밋될 리포트 파일 주소. 알림을 누르면 열린다."""
    env = os.environ if env is None else env
    repo = env.get("GITHUB_REPOSITORY", "")
    branch = env.get("GITHUB_REF_NAME", "main")
    if not repo:
        return ""
    return f"https://github.com/{repo}/blob/{branch}/reports/{report_date.isoformat()}.md"
