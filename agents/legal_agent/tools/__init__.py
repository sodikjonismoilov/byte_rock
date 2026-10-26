"""Local retrieval tools used by the Legal Research Agent."""

if __package__ and __package__.startswith("agents.legal_agent"):
    from ..tools.legal_search import LegalSearchTool, search_legal_sources
else:
    from tools.legal_search import LegalSearchTool, search_legal_sources

__all__ = ["LegalSearchTool", "search_legal_sources"]
