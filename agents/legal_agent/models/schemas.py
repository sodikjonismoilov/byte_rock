from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as Date
from enum import Enum
from typing import Any, Literal, Annotated
import re
import json
from pathlib import Path
from functools import lru_cache

from pydantic import BaseModel, Field, field_validator, AfterValidator
if __package__ and __package__.startswith("agents.legal_agent"):
    from ..models.identity import IdentityCandidate, IdentityResult, RecordMatch
else:
    from models.identity import IdentityCandidate, IdentityResult, RecordMatch
if __package__ and __package__.startswith("agents.legal_agent"):
    from ..models.reconciliation import ReconciliationResult
else:
    from models.reconciliation import ReconciliationResult


def _authoritative_reference(value: str) -> str:
    if not value.strip() or re.match(r'^mem-',value.strip(),re.I):
        raise ValueError('Memory IDs are context only, never evidence or legal authority references')
    return value

@lru_cache(maxsize=1)
def _catalog_authority_ids():
    return {s['id'] for s in json.loads((Path(__file__).resolve().parents[1]/'data'/'legal_sources.json').read_text())}


def _evidence_reference(value):
    _authoritative_reference(value)
    if value in _catalog_authority_ids():raise ValueError('Legal authority IDs cannot be factual evidence references')
    return value


def _legal_reference(value):
    _authoritative_reference(value)
    if re.match(r'^[a-z0-9]{4}-[a-z0-9]{4}:|^EV-',value):
        raise ValueError('Official record IDs cannot be legal authority references')
    return value

EvidenceId = Annotated[str, AfterValidator(_evidence_reference), Field(description='Exact ID from accepted evidence registry; never an authority or mem-* ID')]
AuthorityId = Annotated[str, AfterValidator(_legal_reference), Field(description='Exact retrieved legal catalog authority ID; never evidence or mem-* IDs')]
MemoryId = Annotated[str, Field(pattern=r'^mem-[0-9]+$',description='H-MEM context ID only; cannot support factual or legal conclusions')]


class EvidenceKind(str, Enum):
    COMPLAINT = "complaint"
    CONFIRMED_VIOLATION = "confirmed_violation"
    TENANT_REPORT = "tenant_report"
    OTHER = "other"
    INSPECTION = "inspection"
    PERMIT = "permit"
    CASE_FILING = "case_filing"
    DECISION = "decision"
    JUDGMENT = "judgment"
    WARRANT = "warrant"
    EXECUTED_EVICTION = "executed_eviction"


class CriticOutcome(str, Enum):
    BLOCKED = "BLOCKED"
    PASS = "PASS"
    REVISE = "REVISE"
    INCONCLUSIVE = "INCONCLUSIVE"


class InvestigationStatus(str, Enum):
    COMPLETED = "completed"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"


class BuildingInfo(BaseModel):
    address: str
    borough: str | None = None
    bin: str | None = None
    bbl: str | None = None
    unit: str | None = None
    year_built: int | None = None
    residential_units: int | None = None


class EvidenceItem(BaseModel):
    evidence_id: EvidenceId
    kind: EvidenceKind
    source: str
    date: Date | None = None
    description: str
    status: str | None = None
    violation_class: str | None = None
    statute_or_code: str | None = None
    building_address: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegalIssueTask(BaseModel):
    task_id: str
    question: str
    building: BuildingInfo
    issue_types: list[str] = Field(default_factory=list)
    evidence_ids: list[EvidenceId] = Field(default_factory=list)
    requested_by: str | None = None

    @field_validator("task_id")
    @classmethod
    def task_id_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task_id must not be empty")
        return value


class InvestigationContext(BaseModel):
    untrusted_memory: list[dict[str, Any]] = Field(default_factory=list)
    source_coverage: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    root_critic_outcome: CriticOutcome | None = None
    data_mode: Literal['sample', 'live', 'recorded_replay', 'mock', 'development_fallback'] = 'sample'
    data_provider: str = 'unspecified'
    schema_version: str = "1.1"
    identity_candidates: list[IdentityCandidate] | None = None
    identity: IdentityResult | None = None
    record_matches: list[RecordMatch] = Field(default_factory=list)
    reconciliation: ReconciliationResult | None = None
    as_of: Date = Field(default_factory=Date.today)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    notes: str | None = None
    retrieved_source_ids: list[AuthorityId] = Field(default_factory=list)

    @field_validator('evidence')
    @classmethod
    def unique_evidence_ids(cls, value):
        if len({e.evidence_id for e in value}) != len(value):
            raise ValueError('Evidence IDs must be unique')
        return value


class LegalSource(BaseModel):
    authority_type: Literal["statute", "agency_guidance", "court_guidance", "judicial_decision"] = "agency_guidance"
    effective_from: Date | None = None
    effective_to: Date | None = None
    checked_on: Date | None = None
    temporal_limitations: str = "Effective version must be checked for the incident date."
    id: AuthorityId
    excerpt_provenance: dict[str, Any] = Field(default_factory=dict)
    title: str
    jurisdiction: str
    identifier: str
    url: str
    topics: list[str] = Field(default_factory=list)
    summary: str
    excerpt: str | None = None


class LegalSourceHit(BaseModel):
    source: LegalSource
    score: float
    matched_terms: list[str] = Field(default_factory=list)


class ResearchQuestion(BaseModel):
    memory_ids: list[MemoryId] = Field(default_factory=list, description="Optional context hints only, not evidence inputs")
    recommended_tool: Literal["legal_search", "evidence_review", "request_external"] = "legal_search"
    required_inputs: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    priority: int = Field(default=2, ge=1, le=3)
    completion_condition: str = "Return cited analysis or an explicit evidence gap."
    question_id: str
    prompt: str
    focus_topics: list[str] = Field(default_factory=list)
    evidence_ids: list[EvidenceId] = Field(default_factory=list)


class ResearchPlan(BaseModel):
    task_id: str
    revision: int = 0
    objective: str
    questions: list[ResearchQuestion]
    constraints: list[str] = Field(default_factory=list)
    reasoning_mode: str = "demo_deterministic"
    notes: list[str] = Field(default_factory=list)


class LegalConclusion(BaseModel):
    claim_scope: Literal['current_guidance','statute_text','historical_application'] = 'historical_application'
    support_quotes: dict[str, str] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list, description='Runtime-grounded metadata; never trusted from model output')
    grounding_version: str | None = None
    grounding_errors: list[str] = Field(default_factory=list)
    statement: str
    source_ids: list[AuthorityId] = Field(default_factory=list)
    identifiers: list[str] = Field(default_factory=list)
    supported: bool = True


class Finding(BaseModel):
    memory_ids: list[MemoryId] = Field(default_factory=list, description="Context influences only; claims must cite evidence and legal authorities separately")
    supported_facts: list[str] = Field(default_factory=list)
    contradictory_evidence_ids: list[EvidenceId] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    sufficiency: Literal["sufficient", "partial", "insufficient"] = "partial"
    follow_up_tasks: list[str] = Field(default_factory=list)
    valid: bool = True
    interpretation_type: str = "research_interpretation"
    finding_id: str
    issue: str
    summary: str
    evidence_ids: list[EvidenceId] = Field(default_factory=list)
    evidence_kinds: list[EvidenceKind] = Field(default_factory=list)
    legal_conclusions: list[LegalConclusion] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"
    treats_complaint_as_violation: bool = False
    notes: list[str] = Field(default_factory=list)


class ResearchDraft(BaseModel):
    task_id: str
    plan_revision: int
    findings: list[Finding]
    retrieved_sources: list[LegalSourceHit] = Field(default_factory=list)
    evidence_ids_used: list[EvidenceId] = Field(default_factory=list)
    reasoning_mode: str = "demo_deterministic"
    caveats: list[str] = Field(default_factory=list)


class CriticIssue(BaseModel):
    memory_ids: list[MemoryId] = Field(default_factory=list)
    recoverable: bool = False
    follow_up_query: str | None = Field(default=None,max_length=3000)
    evidence_ids: list[EvidenceId] = Field(default_factory=list)
    required_correction: str = "Recheck affected evidence and retrieve supporting authority."
    recommended_agent_or_tool: str = "legal_search"
    priority: int = Field(default=1, ge=1, le=3)
    code: str
    message: str
    finding_ids: list[str] = Field(default_factory=list)


class CriticReport(BaseModel):
    task_id: str
    outcome: CriticOutcome
    issues: list[CriticIssue] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)
    reasoning_mode: str = "demo_deterministic"


class InvestigationError(BaseModel):
    code: str
    message: str


class InvestigationResult(BaseModel):
    citation_metrics: dict[str, int] = Field(default_factory=dict)
    citation_audit: list[dict[str, Any]] = Field(default_factory=list)
    activity_events: list[dict[str, Any]] = Field(default_factory=list)
    execution: dict[str, Any] = Field(default_factory=dict)
    data_mode: Literal['sample', 'live', 'recorded_replay', 'mock', 'development_fallback'] = 'sample'
    data_provider: str = 'unspecified'
    caveats: list[str] = Field(default_factory=list)
    review_history: list[CriticReport] = Field(default_factory=list)
    schema_version: str = "1.1"
    identity: IdentityResult | None = None
    record_matches: list[RecordMatch] = Field(default_factory=list)
    reconciliation: ReconciliationResult | None = None
    research_requests: list[str] = Field(default_factory=list)
    plans: list[ResearchPlan] = Field(default_factory=list)
    tool_calls: int = 0
    legal_sources: list[LegalSource] = Field(default_factory=list)
    task_id: str
    building: BuildingInfo
    evidence_ids: list[EvidenceId]
    findings: list[Finding]
    status: InvestigationStatus
    critic_outcome: CriticOutcome | None = None
    revision_cycles: int = 0
    reasoning_mode: str = "demo_deterministic"
    retrieved_source_ids: list[AuthorityId] = Field(default_factory=list)
    errors: list[InvestigationError] = Field(default_factory=list)
    critic_issues: list[CriticIssue] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: list[str] = Field(default_factory=list)
