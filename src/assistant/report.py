"""수집 결과를 Markdown 리포트로 렌더링하고 파일로 저장한다."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from assistant.models import InterestDigest, Item

DEFAULT_OUTPUT_DIR = Path("reports")


def render(digests: list[InterestDigest], report_date: date) -> str:
    lines = [f"# 관심사 리포트 {report_date.isoformat()}", ""]
    attributions: list[str] = []
    failures: list[str] = []
    for digest in digests:
        failures.extend(digest.failures)
        news = [i for i in digest.items if not i.standing]
        standing = [i for i in digest.items if i.standing]
        for item in digest.items:
            if item.attribution and item.attribution not in attributions:
                attributions.append(item.attribution)
        lines.append(f"## {digest.interest.name}")
        lines.append("")
        if not news:
            lines.append(
                "_새로 올라온 항목이 없습니다._" if standing else "_수집된 항목이 없습니다._"
            )
            lines.append("")
        for item in news:
            when = f" · {item.published:%Y-%m-%d}" if item.published else ""
            label = f"[{item.title}]({item.url})" if item.url else item.title
            if item.details:
                lines.append(f"- {label}{when}  ")  # 끝의 공백 두 개 = Markdown 줄바꿈
                lines.append(f"  {item.details}")
            else:
                lines.append(f"- {label}{when}")
        if news:
            lines.append("")
        if standing:
            lines.append(f"**예정 ({len(standing)}건)**")
            lines.append("")
            for item in standing:
                lines.append(f"- {_standing_line(item, report_date)}")
            lines.append("")
    if failures or attributions:
        lines.append("---")
        lines.extend(f"_수집 실패: {text}_" for text in failures)
        lines.extend(f"_{text}_" for text in attributions)
    return "\n".join(lines).rstrip() + "\n"


def _standing_line(item: Item, report_date: date) -> str:
    """예정 공연 한 줄: `10.22(목) D-6 · [제목](url) · 장소 · 티켓 오픈 …`"""
    label = f"[{item.title}]({item.url})" if item.url else item.title
    parts: list[str] = []
    if item.event_date:
        dday = (item.event_date - report_date).days
        weekday = "월화수목금토일"[item.event_date.weekday()]
        parts.append(
            f"{item.event_date:%m.%d}({weekday}) " + ("D-Day" if dday == 0 else f"D-{dday}")
        )
    parts.append(label)
    if item.details:
        parts.append(item.details)
    return " · ".join(parts)


def write(markdown: str, report_date: date, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{report_date.isoformat()}.md"
    path.write_text(markdown, encoding="utf-8")
    return path
