"""Opt-in provider smoke test; never part of ordinary offline execution."""
import os
import pytest
from tools.execution import ExecutionLimits
from tools.llm import JSONModelAdapter
from models.schemas import CriticReport


@pytest.mark.live
@pytest.mark.skipif(os.getenv('RUN_LIVE_MODEL_TESTS') != '1',reason='Requires explicit live-model opt-in')
def test_live_structured_response():
    response=JSONModelAdapter(ExecutionLimits()).complete(CriticReport,{'task_id':'live-smoke','role':'independent_critic','request':'No building records provided. Return INCONCLUSIVE and explain the missing evidence.'})
    assert response.task_id=='live-smoke'
    assert response.outcome.value=='INCONCLUSIVE'
