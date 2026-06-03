from dataclasses import dataclass, field

from paper_crawler.models import PaperRecord


@dataclass(slots=True)
class FetchResult:
    source: str = ""
    records: list[PaperRecord] = field(default_factory=list)


class BaseFetcher:
    source_name: str = ""

    def fetch(self) -> FetchResult:
        return FetchResult(source=self.source_name)
