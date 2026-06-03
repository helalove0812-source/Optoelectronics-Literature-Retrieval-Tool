def render_email_summary(records: list[dict[str, object]]) -> str:
    return f"Matched papers: {len(records)}"
