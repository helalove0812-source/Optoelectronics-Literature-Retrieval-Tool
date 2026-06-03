from paper_crawler.matchers.keyword_matcher import build_keyword_index, match_keywords


def test_match_keywords_returns_group_names_for_direct_and_synonym_hits() -> None:
    keyword_groups = {
        "硅光": ["silicon photonics"],
        "超表面": ["metasurface"],
    }
    synonyms = {
        "silicon photonics": ["SiPh", "硅光"],
        "metasurface": ["超表面"],
    }

    keyword_index = build_keyword_index(keyword_groups, synonyms)

    matched = match_keywords(
        title="SiPh packaging for datacenter optics",
        abstract="This metasurface platform improves coupling efficiency.",
        keyword_index=keyword_index,
    )

    assert matched == ["硅光", "超表面"]


def test_match_keywords_deduplicates_group_hits_and_returns_empty_when_unmatched() -> None:
    keyword_groups = {"光通信": ["optical communication", "coherent optics"]}
    synonyms = {"optical communication": ["optical communications"]}

    keyword_index = build_keyword_index(keyword_groups, synonyms)

    matched = match_keywords(
        title="Optical communication systems",
        abstract="Coherent optics remains central to optical communications.",
        keyword_index=keyword_index,
    )
    unmatched = match_keywords(
        title="Solid-state batteries",
        abstract="Electrochemistry only.",
        keyword_index=keyword_index,
    )

    assert matched == ["光通信"]
    assert unmatched == []
