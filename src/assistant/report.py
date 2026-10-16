"""수집/요약 결과를 Markdown 리포트로 렌더링하고 파일로 저장한다."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from assistant.models import InterestDigest

DEFAULT_OUTPUT_DIR = Path("reports")


def render(digests: list[InterestDigest], report_date: date) -> str:
    lines = [f"# 관심사 리포트 {report_date.isoformat()}", ""]
    for digest in digests:
        lines.append(f"## {digest.interest.name}")
        lines.append("")
        if digest.summary:
            lines.append(digest.summary)
            lines.append("")
        if not digest.items:
            lines.append("_수집된 항목이 없습니다._")
            lines.append("")
            continue
        for item in digest.items:
            when = f" · {item.published:%Y-%m-%d}" if item.published else ""
            label = f"[{item.title}]({item.url})" if item.url else item.title
            lines.append(f"- {label}{when}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write(markdown: str, report_date: date, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{report_date.isoformat()}.md"
    path.write_text(markdown, encoding="utf-8")
    return path
