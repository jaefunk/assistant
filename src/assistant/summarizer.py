"""Claude 로 관심사별 수집 결과를 요약한다.

ANTHROPIC_API_KEY 가 없으면 요약을 건너뛰고 원문 목록만 리포트에 싣는다.
"""

from __future__ import annotations

import logging
import os

from assistant.models import InterestDigest

log = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("ASSISTANT_MODEL", "claude-sonnet-5-5")


def summarize(digests: list[InterestDigest], model: str = DEFAULT_MODEL) -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("ANTHROPIC_API_KEY 가 없어 요약을 건너뜁니다.")
        return

    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    for digest in digests:
        if not digest.items:
            continue
        digest.summary = _summarize_one(client, model, digest)


def _summarize_one(client, model: str, digest: InterestDigest) -> str:
    bullet_lines = "\n".join(f"- {item.title} ({item.url})" for item in digest.items)
    prompt = (
        f"다음은 '{digest.interest.name}' 주제로 수집한 최신 글 목록입니다.\n"
        "핵심 흐름을 한국어로 3~5개의 불릿으로 요약해 주세요. "
        "각 불릿은 한 문장으로, 과장 없이 사실만 적어 주세요.\n\n"
        f"{bullet_lines}"
    )
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in message.content if block.type == "text").strip()
