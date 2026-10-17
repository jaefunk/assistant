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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="assistant", description="관심사 정보 리포트")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("report", help="리포트를 생성한다")
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    run.add_argument("--output-dir", type=Path, default=report_mod.DEFAULT_OUTPUT_DIR)
    run.add_argument("--date", type=date.fromisoformat, default=None, help="YYYY-MM-DD")
    run.add_argument("--stdout", action="store_true", help="파일 대신 표준출력으로")
    run.add_argument(
        "--email", action="store_true", help="SMTP_* / MAIL_TO 환경변수로 리포트를 메일 발송"
    )

    sync = sub.add_parser("sync-kopis", help="KOPIS 공연 장부만 동기화한다 (리포트·메일 없음)")
    sync.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    sync.add_argument("--budget-minutes", type=float, default=120, help="전체 시간 예산 (분)")
    sync.add_argument("--max-detail", type=int, default=5000, help="상세 조회 상한")
    sync.add_argument("--full-sync", action="store_true", help="장부가 있어도 전체 동기화")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)

    if args.command == "report":
        settings = load_settings(args.config)
        digests = collect(settings)
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
    elif args.command == "sync-kopis":
        return sync_kopis(args)
    return 0


def sync_kopis(args: argparse.Namespace) -> int:
    from assistant.sources.kopis import KopisSource

    settings = load_settings(args.config)
    specs = [s for i in settings.interests for s in i.sources if s.type == "kopis"]
    if not specs:
        logging.error("설정에 kopis 소스가 없습니다.")
        return 1
    source = KopisSource(
        time_budget=args.budget_minutes * 60,
        max_detail=args.max_detail,
        full_sync=True if args.full_sync else None,
    )
    for spec in specs:
        _, store = source.sync(spec)
        performances = store["performances"]
        pending = sum(1 for v in performances.values() if "checked" not in v)
        waiting = sum(1 for v in performances.values() if v.get("pending_report"))
        print(f"장부 {len(performances)}건, 미확인 {pending}건, 보고 대기 {waiting}건")
    return 0
