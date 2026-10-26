from __future__ import annotations

import json
from pathlib import Path

import pytest

from models.schemas import (
    BuildingInfo,
    EvidenceItem,
    InvestigationContext,
    LegalIssueTask,
)
from tools.legal_search import LegalSearchTool

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PATH = ROOT / "data" / "sample_evidence.json"


@pytest.fixture
def sample_bundle() -> dict:
    with SAMPLE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def search_tool() -> LegalSearchTool:
    return LegalSearchTool()


def _building(bundle: dict, address: str) -> BuildingInfo:
    raw = next(item for item in bundle["buildings"] if item["address"] == address)
    return BuildingInfo.model_validate(raw)


def _evidence(bundle: dict, address: str) -> list[EvidenceItem]:
    return [
        EvidenceItem.model_validate(item)
        for item in bundle["evidence"]
        if item.get("building_address") == address
    ]


@pytest.fixture
def heat_task(sample_bundle: dict) -> LegalIssueTask:
    address = "214 East 7th Street"
    evidence = _evidence(sample_bundle, address)
    return LegalIssueTask(
        task_id="task-heat-confirmed",
        question="Does this building have a confirmed heat problem under NYC housing rules?",
        building=_building(sample_bundle, address),
        issue_types=["heat"],
        evidence_ids=[item.evidence_id for item in evidence],
    )


@pytest.fixture
def heat_context(sample_bundle: dict) -> InvestigationContext:
    return InvestigationContext(evidence=_evidence(sample_bundle, "214 East 7th Street"))


@pytest.fixture
def complaint_only_task(sample_bundle: dict) -> LegalIssueTask:
    address = "88-12 Roosevelt Avenue"
    evidence = _evidence(sample_bundle, address)
    return LegalIssueTask(
        task_id="task-pest-complaints",
        question="Are the pest reports confirmed violations?",
        building=_building(sample_bundle, address),
        issue_types=["pests"],
        evidence_ids=[item.evidence_id for item in evidence],
    )


@pytest.fixture
def complaint_only_context(sample_bundle: dict) -> InvestigationContext:
    return InvestigationContext(evidence=_evidence(sample_bundle, "88-12 Roosevelt Avenue"))


@pytest.fixture
def pest_violation_task(sample_bundle: dict) -> LegalIssueTask:
    address = "410 West 145th Street"
    evidence = _evidence(sample_bundle, address)
    return LegalIssueTask(
        task_id="task-pest-violation",
        question="What pest duties apply given the HPD violation?",
        building=_building(sample_bundle, address),
        issue_types=["pests"],
        evidence_ids=[item.evidence_id for item in evidence],
    )


@pytest.fixture
def pest_violation_context(sample_bundle: dict) -> InvestigationContext:
    return InvestigationContext(evidence=_evidence(sample_bundle, "410 West 145th Street"))
