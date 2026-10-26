from tools.legal_search import LegalSearchTool, search_legal_sources


def test_heat_query_returns_temperature_statute(search_tool: LegalSearchTool) -> None:
    hits = search_tool.search("required indoor heat temperature during heat season")
    identifiers = {hit.source.identifier for hit in hits}
    assert "NYC Admin. Code § 27-2029" in identifiers
    assert all(hit.score > 0 for hit in hits)


def test_pest_query_returns_pest_code(search_tool: LegalSearchTool) -> None:
    hits = search_tool.search("mice cockroaches pest infestation violation")
    source_ids = {hit.source.id for hit in hits}
    assert "nyc-admin-27-2017-4" in source_ids


def test_empty_query_returns_nothing(search_tool: LegalSearchTool) -> None:
    assert search_tool.search("   ") == []


def test_module_helper_matches_class() -> None:
    hits = search_legal_sources("warranty of habitability residential lease")
    assert any(hit.source.id == "rpl-235-b" for hit in hits)


def test_sources_have_verified_urls(search_tool: LegalSearchTool) -> None:
    for source in search_tool.sources:
        assert source.url.startswith("https://")
        assert source.identifier
        assert source.id
