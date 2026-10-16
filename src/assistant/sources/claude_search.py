"""Claude 가 웹 검색으로 직접 글을 찾아오는 수집기.

config 예:
    - type: claude_search
      query: LLM 과 AI 에이전트 주요 뉴스
      days: 7        # 최근 며칠 이내 글만 (기본 7)

Claude 에게 web_search 서버 도구를 주고 최종 답변을 JSON 배열로 받는다.
서버 도구 루프가 길어져 pause_turn 으로 멈추면 같은 대화를 이어서 다시 보낸다.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime

from assistant.claude import DEFAULT_MODEL, FALLBACK_BETA, make_client
from assistant.models import Item, SourceSpec

log = logging.getLogger(__name__)

MAX_SEARCHES = 6
MAX_PAUSE_RESUMES = 3


class ClaudeSearchSource:
    def __init__(self, client=None, model: str = DEFAULT_MODEL) -> None:
        self._client = client
        self._model = model

    def fetch(self, spec: SourceSpec, limit: int) -> list[Item]:
        client = self._client or make_client()
        if client is None:
            raise RuntimeError("ANTHROPIC_API_KEY 가 없어 claude_search 를 쓸 수 없습니다.")

        messages = [{"role": "user", "content": build_prompt(spec, limit, date.today())}]
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_SEARCHES}]

        for _ in range(MAX_PAUSE_RESUMES + 1):
            response = client.beta.messages.create(
                model=self._model,
                max_tokens=8000,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                tools=tools,
                messages=messages,
            )
            if response.stop_reason != "pause_turn":
                break
            # 서버 도구 루프가 중간에 멈춤. assistant 턴을 그대로 붙여 이어서 보낸다.
            messages.append({"role": "assistant", "content": response.content})
        else:
            raise RuntimeError("claude_search: pause_turn 이 반복되어 중단합니다.")

        if response.stop_reason == "refusal":
            raise RuntimeError(f"claude_search: 요청이 거절되었습니다 ({response.stop_details})")

        text = "".join(block.text for block in response.content if block.type == "text")
        return parse_items(text, limit)


def build_prompt(spec: SourceSpec, limit: int, today: date) -> str:
    return (
        f"오늘은 {today.isoformat()} 입니다. 웹을 검색해서 최근 {spec.days}일 이내에 나온 "
        f"'{spec.query}' 관련 글 중 주목할 만한 것을 최대 {limit}개 고르세요.\n"
        "같은 소식은 하나로 합치고, 광고나 목록 페이지는 제외하세요.\n\n"
        "최종 답변은 설명 없이 아래 형태의 JSON 배열만 출력하세요.\n"
        '[{"title": "글 제목", "url": "검색 결과에 실제로 있던 URL", '
        '"published": "YYYY-MM-DD 또는 null", "summary": "한국어 한 문장 요약"}]'
    )


def parse_items(text: str, limit: int) -> list[Item]:
    """Claude 의 최종 텍스트에서 JSON 배열을 꺼내 Item 으로 바꾼다."""
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("claude_search: 응답에서 JSON 배열을 찾지 못했습니다.")
    raw = json.loads(text[start : end + 1])
    if not isinstance(raw, list):
        raise ValueError("claude_search: JSON 배열이 아닙니다.")

    items: list[Item] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or "").strip()
        title = str(entry.get("title") or "").strip()
        if not url or not title:
            continue
        items.append(
            Item(
                title=title,
                url=url,
                published=_parse_date(entry.get("published")),
                summary=str(entry.get("summary") or "").strip(),
            )
        )
    return items[:limit]


def _parse_date(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if not match:
        return None
    try:
        return datetime(*map(int, match.groups()), tzinfo=UTC)
    except ValueError:
        return None
