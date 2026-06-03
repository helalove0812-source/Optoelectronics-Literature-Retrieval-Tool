from paper_crawler.utils.fingerprint import build_paper_fingerprint


def test_build_paper_fingerprint_is_stable():
    value = build_paper_fingerprint(
        title=" Silicon Photonics for Coherent Links ",
        authors=["Alice Smith", "Bob Chen"],
    )

    assert value == "silicon-photonics-for-coherent-links::alice-smith"
