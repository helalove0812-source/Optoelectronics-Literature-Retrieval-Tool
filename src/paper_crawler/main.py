from pathlib import Path

from paper_crawler.processing import run_pipeline
from paper_crawler.settings import load_settings


def run_application(config_dir: Path) -> str:
    settings = load_settings(config_dir)
    result = run_pipeline(settings)
    return (
        f"Pipeline finished: fetched={result.fetched_count}, "
        f"matched={result.matched_count}"
    )
