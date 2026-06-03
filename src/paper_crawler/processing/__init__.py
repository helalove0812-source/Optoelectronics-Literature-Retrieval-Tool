from paper_crawler.processing.deduplicate import deduplicate_records
from paper_crawler.processing.normalize import normalize_record
from paper_crawler.processing.pipeline import PipelineResult, run_pipeline

__all__ = [
    "PipelineResult",
    "deduplicate_records",
    "normalize_record",
    "run_pipeline",
]
