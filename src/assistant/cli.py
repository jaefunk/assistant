"""`assistant` 커맨드라인 진입점."""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, date, datetime
from pathlib import Path

from assistant import report as report_mod
from assistant.collector import collect
from assistant.config import DEFAULT_CONFIG_PATH, load_settings
from assistant.mailer import MailConfig, send
from assistant.summarizer import summarize


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="assistant", description="관심사 정보 리포트")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("report", help="리포트를 생성한다")
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    run.add_argument("--output-dir", type=Path, default=report_mod.DEFAULT_OUTPUT_DIR)
    run.add_argument("--date", type=date.fromisoformat, default=None, help="YYYY-MM-DD")
    run.add_argument("--no-summary", action="store_true", help="Claude 요약 생략")
    run.add_argument("--stdout", action="store_true", help="파일 대신 표준출력으로")
    run.add_argument(
        "--email", action="store_true", help="SMTP_* / MAIL_TO 환경변수로 리포트를 메일 발송"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)

    if args.command == "report":
        settings = load_settings(args.config)
        digests = collect(settings)
        if not args.no_summary:
            summarize(digests)
        report_date = args.date or datetime.now(tz=UTC).date()
        markdown = report_mod.render(digests, report_date)
        if args.stdout:
            print(markdown, end="")
        else:
            path = report_mod.write(markdown, report_date, args.output_dir)
            print(path)
        if args.email:
            config = MailConfig.from_env()
            if config is None:
                logging.error(
                    "SMTP_USER / SMTP_PASSWORD / MAIL_TO 가 없어 메일을 보낼 수 없습니다."
                )
                return 1
            send(f"관심사 리포트 {report_date.isoformat()}", markdown, config)
    return 0
