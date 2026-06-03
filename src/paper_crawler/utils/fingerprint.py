from paper_crawler.utils.text_utils import slugify_text


def build_paper_fingerprint(title: str, authors: list[str]) -> str:
    first_author = authors[0] if authors else "unknown"
    return f"{slugify_text(title)}::{slugify_text(first_author)}"
