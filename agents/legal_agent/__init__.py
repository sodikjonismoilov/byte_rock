"""Importable legal specialist; no provider calls or global module aliases."""
from .workflow import LegalResearchWorkflow, investigate_legal_issue

__all__ = ["LegalResearchWorkflow", "investigate_legal_issue"]
