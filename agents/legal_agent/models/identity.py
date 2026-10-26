from typing import Literal
from pydantic import BaseModel, Field, model_validator


class IdentifierEvidence(BaseModel):
    kind: Literal['bin', 'bbl', 'hpd_building_id']
    value: str
    source: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    authoritative: bool = False
    fictional: bool = False


    @model_validator(mode='after')
    def valid_identifier(self):
        lengths = {'bin':7, 'bbl':10}
        if not self.value.isdigit() or (self.kind in lengths and len(self.value) != lengths[self.kind]):
            raise ValueError('Invalid NYC identifier format')
        return self


class IdentityCandidate(BaseModel):
    candidate_id: str
    address: str
    borough: str | None = None
    aliases: list[str] = Field(default_factory=list)
    identifiers: list[IdentifierEvidence] = Field(default_factory=list)


class IdentityResult(BaseModel):
    schema_version: str = '1.1'
    canonical_address: str
    unit: str | None = None
    borough: str | None = None
    identifiers: dict[str, str] = Field(default_factory=dict)
    verified_identifiers: list[IdentifierEvidence] = Field(default_factory=list)
    candidates: list[IdentityCandidate] = Field(default_factory=list)
    rejected_candidates: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    match_method: str = 'none'
    confidence: float = Field(default=0, ge=0, le=1)
    verification_status: Literal['verified', 'sample', 'unverified', 'ambiguous', 'missing'] = 'missing'


class RecordMatch(BaseModel):
    evidence_id: str
    decision: Literal['accepted', 'rejected', 'quarantined']
    method: str
    scope: Literal['building', 'property', 'unit', 'entity'] = 'building'
    confidence: float = Field(ge=0, le=1)
    reason: str
