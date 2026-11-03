"""Command-line entry point: `newsletter run` and `newsletter should-send`."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from weekly_ai_newsletter.adapters.http import make_http_client
from weekly_ai_newsletter.bootstrap import build_pipeline
from weekly_ai_newsletter.config import Secrets, load_config
from weekly_ai_newsletter.domain.errors import ConfigError, NewsletterError
from weekly_ai_newsletter.pipeline import BuildResult, RunReport
from weekly_ai_newsletter.scheduling import PARIS, should_send

logger = logging.getLogger("weekly_ai_newsletter")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    if args.command == "should-send":
        return _should_send(args)
    return _run(args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="newsletter", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="build the newsletter and send it")
    run.add_argument("--dry-run", action="store_true", help="write a local preview, send nothing")
    run.add_argument("--date", type=date.fromisoformat, help="issue date (default: today in Paris)")
    run.add_argument("--config-dir", type=Path, default=Path("config"))
    run.add_argument("--preview", type=Path, default=Path("preview.html"))

    check = commands.add_parser("should-send", help="print true when it is time to send")
    check.add_argument("--hour", type=int, default=7)
    check.add_argument(
        "--any-time", action="store_true", help="ignore the hour, only skip if already sent today"
    )
    check.add_argument("--config-dir", type=Path, default=Path("config"))
    return parser


def _should_send(args: argparse.Namespace) -> int:
    config = load_config(args.config_dir)
    send = should_send(
        datetime.now(UTC), config.settings.archive_dir, hour=args.hour, any_time=args.any_time
    )
    print("true" if send else "false")
    return 0


def _run(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config_dir)
        secrets = Secrets.from_env(os.environ, require_email=not args.dry_run)
    except ConfigError as exc:
        logger.error("%s", exc)
        return 2
    run_date: date = args.date or datetime.now(PARIS).date()
    result: BuildResult | None = None
    with make_http_client() as http:
        pipeline = build_pipeline(config, secrets, http)
        try:
            result = pipeline.build(run_date)
            if args.dry_run:
                args.preview.write_text(result.rendered.html, encoding="utf-8")
                logger.info("Preview written to %s", args.preview)
            else:
                pipeline.publish(result)
                logger.info("Newsletter %s sent", run_date.isoformat())
        except NewsletterError as exc:
            logger.error("Newsletter run failed: %s", exc)
            if result is not None:
                _report(result.report)
            return 1
    _report(result.report)
    return 0


def _report(report: RunReport) -> None:
    markdown = report.to_markdown()
    logger.info("Run summary:\n%s", markdown)
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write(markdown)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for name, error in report.failures.items():
            print(f"::warning title=Section unavailable::{_escape(f'{name}: {error}')}")


def _escape(message: str) -> str:
    """Encode a workflow-command message so multi-line errors stay in one annotation."""
    return message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
