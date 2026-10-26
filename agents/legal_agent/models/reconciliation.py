from pydantic import BaseModel, Field


class EvidenceConflict(BaseModel):
    category: str
    evidence_ids: list[str]
    explanation: str
    resolved: bool = False


class ReconciliationResult(BaseModel):
    accepted_ids: list[str] = Field(default_factory=list)
    rejected_ids: list[str] = Field(default_factory=list)
    quarantined_ids: list[str] = Field(default_factory=list)
    duplicate_groups: list[list[str]] = Field(default_factory=list)
    conflicts: list[EvidenceConflict] = Field(default_factory=list)
    historical_ids: list[str] = Field(default_factory=list)
    invalidated_finding_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
