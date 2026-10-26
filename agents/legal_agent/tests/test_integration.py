from main import create_app, sample_task
from identity import resolve_building_identity
from workflow import LegalResearchWorkflow
from models.schemas import LegalIssueTask, InvestigationContext


def test_flask_routes_and_bad_inputs():
    client=create_app().test_client()
    assert client.get('/health').status_code == 200
    assert client.post('/resolve-identity',json={'address':'214 E 7th St'}).json['verification_status']=='sample'
    task,context=sample_task()
    response=client.post('/investigate',json={'task':task,'context':context})
    assert response.status_code==200 and response.json['status']=='completed'
    assert client.post('/investigate',json={'task':{}}).status_code==400
    assert client.post('/resolve-identity',json={'address':3}).status_code==400
    assert client.post('/investigate',json=[]).status_code==400


def test_independent_identity_reused_without_shared_state_mutation(heat_task,heat_context):
    from models.identity import IdentityResult
    context=heat_context.model_copy(update={'identity':IdentityResult.model_validate(resolve_building_identity(heat_task.building.address))})
    before=context.model_dump_json()
    assert LegalResearchWorkflow().run(heat_task,context).status.value=='completed'
    assert before==context.model_dump_json()


def test_unknown_identity_blocks_without_fabrication(heat_task,heat_context):
    task=heat_task.model_copy(update={'building':heat_task.building.model_copy(update={'address':'999 Unknown Street'})})
    result=LegalResearchWorkflow().run(task,heat_context)
    assert result.critic_outcome.value=='BLOCKED'
    assert not result.identity.identifiers
    assert result.research_requests
