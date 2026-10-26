"""Pydantic schemas for the Legal Research Agent module."""

if __package__ and __package__.startswith("agents.legal_agent"):
    from ..models.schemas import (
        BuildingInfo,
        CriticReport,
        CriticOutcome,
        EvidenceItem,
        Finding,
        InvestigationContext,
        InvestigationResult,
        InvestigationStatus,
        LegalConclusion,
        LegalIssueTask,
        LegalSource,
        LegalSourceHit,
        ResearchPlan,
        ResearchQuestion,
    )
else:
    from models.schemas import (
        BuildingInfo,
        CriticReport,
        CriticOutcome,
        EvidenceItem,
        Finding,
        InvestigationContext,
        InvestigationResult,
        InvestigationStatus,
        LegalConclusion,
        LegalIssueTask,
        LegalSource,
        LegalSourceHit,
        ResearchPlan,
        ResearchQuestion,
    )

__all__ = [
    "BuildingInfo",
    "CriticReport",
    "CriticOutcome",
    "EvidenceItem",
    "Finding",
    "InvestigationContext",
    "InvestigationResult",
    "InvestigationStatus",
    "LegalConclusion",
    "LegalIssueTask",
    "LegalSource",
    "LegalSourceHit",
    "ResearchPlan",
    "ResearchQuestion",
]
