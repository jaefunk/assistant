"""Claude 로 관심사별 수집 결과를 요약한다.

- ANTHROPIC_API_KEY 가 없으면 요약을 건너뛰고 원문 목록만 리포트에 싣는다.
- 요약 호출이 실패해도 예외를 밖으로 내지 않는다. 아침 메일은 요약 없이라도 나가야 한다.
"""

from __future__ import annotations

import logging

from assistant.claude import DEFAULT_MODEL, FALLBACK_BETA, make_client
from assistant.models import InterestDigest

log = logging.getLogger(__name__)


def summarize(digests: list[InterestDigest], model: str = DEFAULT_MODEL) -> None:
    client = make_client()
    if client is None:
        log.warning("ANTHROPIC_API_KEY 가 없어 요약을 건너뜁니다.")
        return

    for digest in digests:
        if not digest.items:
            continue
        digest.summary = summarize_one(client, model, digest)


def summarize_one(client, model: str, digest: InterestDigest) -> str | None:
    """한 관심사를 요약한다. 실패하면 경고 로그만 남기고 None 을 돌려준다."""
    from anthropic import APIError

    try:
        message = client.beta.messages.create(
            model=model,
            max_tokens=4096,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            messages=[{"role": "user", "content": _prompt(digest)}],
        )
    except APIError as exc:
        log.warning("요약 실패 (%s): %s", digest.interest.name, exc)
        return None

    if message.stop_reason == "refusal":
        log.warning("요약 거절됨 (%s): %s", digest.interest.name, message.stop_details)
        return None
    text = "".join(block.text for block in message.content if block.type == "text").strip()
    return text or None


def _prompt(digest: InterestDigest) -> str:
    bullet_lines = "\n".join(
        f"- {item.title} ({item.url})" + (f": {item.summary}" if item.summary else "")
        for item in digest.items
    )
    return (
        f"다음은 '{digest.interest.name}' 주제로 수집한 최신 글 목록입니다.\n"
        "핵심 흐름을 한국어로 3~5개의 불릿으로 요약해 주세요. "
        "각 불릿은 한 문장으로, 과장 없이 사실만 적어 주세요.\n\n"
        f"{bullet_lines}"
    )
