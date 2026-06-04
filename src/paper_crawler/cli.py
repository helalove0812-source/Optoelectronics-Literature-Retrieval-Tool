import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from paper_crawler.logging_utils import configure_logging
from paper_crawler.main import run_application

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper-crawler")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--config", default="config")
    return parser


def load_root_dotenv() -> None:
    dotenv_path = PROJECT_ROOT / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    load_root_dotenv()
    configure_logging()

    if args.command == "run":
        print(run_application(Path(args.config)))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
