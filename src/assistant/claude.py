"""Anthropic 클라이언트 생성. summarizer 와 claude_search 수집기가 함께 쓴다.

- ANTHROPIC_API_KEY 가 없으면 None 을 돌려준다.
- ANTHROPIC_WORKSPACE_ID 가 있으면 anthropic-workspace-id 헤더로 보낸다
  (워크스페이스에 묶이지 않은 키는 이 헤더가 없으면 400 을 돌려준다).
"""

from __future__ import annotations

import os

DEFAULT_MODEL = os.environ.get("ASSISTANT_MODEL", "claude-opus-5-5")
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def make_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    from anthropic import Anthropic

    headers = {}
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    if workspace_id:
        headers["anthropic-workspace-id"] = workspace_id
    return Anthropic(api_key=api_key, default_headers=headers)
