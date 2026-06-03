from dataclasses import dataclass

from paper_crawler.settings import Settings


@dataclass(slots=True)
class PipelineResult:
    fetched_count: int
    matched_count: int


def run_pipeline(settings: Settings) -> PipelineResult:
    _ = settings
    return PipelineResult(fetched_count=0, matched_count=0)
