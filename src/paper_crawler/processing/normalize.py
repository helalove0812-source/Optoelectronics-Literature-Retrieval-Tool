def normalize_record(source: str, payload: dict[str, object]) -> dict[str, object]:
    return {"source": source, "payload": payload}
