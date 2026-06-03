from __future__ import annotations

from collections import OrderedDict


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def build_keyword_index(
    keyword_groups: dict[str, list[str]],
    synonyms: dict[str, list[str]],
) -> dict[str, list[str]]:
    keyword_index: dict[str, list[str]] = OrderedDict()

    for group_name, keywords in keyword_groups.items():
        expanded_terms: list[str] = []
        seen_terms: set[str] = set()

        for keyword in keywords:
            for candidate in [keyword, *synonyms.get(keyword, [])]:
                normalized = _normalize_text(candidate)
                if normalized and normalized not in seen_terms:
                    seen_terms.add(normalized)
                    expanded_terms.append(normalized)

        keyword_index[group_name] = expanded_terms

    return keyword_index


def match_keywords(
    title: str,
    abstract: str,
    keyword_index: dict[str, list[str]],
) -> list[str]:
    haystack = _normalize_text(f"{title} {abstract}")
    if not haystack:
        return []

    matched_groups: list[str] = []
    for group_name, candidates in keyword_index.items():
        if any(candidate in haystack for candidate in candidates):
            matched_groups.append(group_name)

    return matched_groups
