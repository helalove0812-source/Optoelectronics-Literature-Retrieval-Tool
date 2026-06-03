from dataclasses import dataclass, field

from paper_crawler.models import PaperRecord


@dataclass(slots=True)
class FetchResult:
    records: list[PaperRecord] = field(default_factory=list)


class BaseFetcher:
    def fetch(self) -> FetchResult:
        return FetchResult()
