"""One property investigation; only this coordinator knows the data provider."""
from datetime import UTC, datetime
import json
from pathlib import Path

if __package__ and __package__.startswith("agents.legal_agent"):
    from .identity import match_record, resolve_building_identity
else:
    from identity import match_record, resolve_building_identity
if __package__ and __package__.startswith("agents.legal_agent"):
    from .integration import review_records
else:
    from integration import review_records
if __package__ and __package__.startswith("agents.legal_agent"):
    from .models.identity import IdentityResult
else:
    from models.identity import IdentityResult
if __package__ and __package__.startswith("agents.legal_agent"):
    from .models.schemas import InvestigationContext, LegalIssueTask
else:
    from models.schemas import InvestigationContext, LegalIssueTask
if __package__ and __package__.startswith("agents.legal_agent"):
    from .reporting import write_report
else:
    from reporting import write_report
if __package__ and __package__.startswith("agents.legal_agent"):
    from .tools.property_data import BUILDINGS, VIOLATIONS, PropertyDataProvider
else:
    from tools.property_data import BUILDINGS, VIOLATIONS, PropertyDataProvider
if __package__ and __package__.startswith("agents.legal_agent"):
    from .tools.zetaris import map_hpd_building, map_hpd_rows
else:
    from tools.zetaris import map_hpd_building, map_hpd_rows
if __package__ and __package__.startswith("agents.legal_agent"):
    from .workflow import LegalResearchWorkflow
else:
    from workflow import LegalResearchWorkflow


if __package__ and __package__.startswith("agents.legal_agent"):
    from .tools.execution import ExecutionBudget
else:
    from tools.execution import ExecutionBudget


def investigate_property(provider: PropertyDataProvider, output_dir, *, workflow=None, budget=None, reasoning_mode=None):
    budget=budget or getattr(provider,"budget",None) or ExecutionBudget()
    provider.budget=budget
    seed = provider.fetch(VIOLATIONS, limit=200)
    # Prefer building-scoped evidence. If none is available, explicitly target
    # the unit from a real source row rather than applying it to every apartment.
    ordered = sorted(seed.rows, key=lambda r: bool(str(r.get('apartment') or '').strip()))
    selected, building_batch = None, None
    tried = set()
    for row in ordered:
        building_id = str(row.get('buildingid') or '')
        if not building_id or building_id in tried:
            continue
        tried.add(building_id)
        building_batch = provider.fetch(BUILDINGS, building_id=building_id, limit=2)
        if len(building_batch.rows) == 1:
            selected = row
            break
        if len(tried) >= 10:
            break
    if selected is None:
        raise ValueError('No unique Building Files identity corroborates the bounded violation batch')
    candidate, identity_record = map_hpd_building(building_batch.rows[0], retrieved_at=building_batch.retrieved_at, provider=provider.name)
    if identity_record.metadata.get('zip') not in {'10017','11103'}:
        raise ValueError('Real sample is outside the agreed ZIP scope')
    unit = str(selected.get('apartment') or '').strip() or None
    identity = IdentityResult.model_validate(resolve_building_identity(candidate.address, {'candidates':[candidate.model_dump(mode='json')], 'unit':unit, 'borough':candidate.borough}))
    if identity.verification_status != 'verified':
        raise ValueError('Official Building Files identity is unresolved')
    batch = provider.fetch(VIOLATIONS, building_id=selected['buildingid'], limit=200)
    evidence = map_hpd_rows(batch.rows, retrieved_at=batch.retrieved_at, provider=provider.name)
    for record in evidence:
        local_match = match_record(record, identity)
        record.metadata['matcher_confidence'] = local_match.confidence
        record.metadata['match_method'] = local_match.method
        record.metadata['issue'] = 'maintenance'
        record.metadata['query_reference'] = batch.query_reference
    # Reuse the existing resolver's matching; the root Critic still independently
    # runs its rules, then the legal scope gate applies to its accepted batch.
    card = {'address_raw':candidate.address, **identity.identifiers}
    matches, trace = review_records(evidence, card,budget=budget)
    mode = 'live' if provider.name == 'zetaris' else 'development_fallback'
    task = LegalIssueTask(task_id=f'hpd-{selected["buildingid"]}-{datetime.now(UTC):%Y%m%d}',
        question='Review these HPD maintenance records and explain relevant housing duties with source limitations.',
        building=dict(address=candidate.address, borough=candidate.borough, unit=unit,
                      bin=identity.identifiers.get('bin'), bbl=identity.identifiers.get('bbl')),
        issue_types=['maintenance'], evidence_ids=[e.evidence_id for e in evidence])
    limitations = [
        'Only HPD Building Files and HPD violation records were queried; complaints, DOB, eviction, litigation and rent-regulation coverage are absent.',
        'The registered Zetaris REST endpoints are bounded to ZIP 10017: up to 5000 buildings and the latest 200 violation IDs. Counts describe this retrieved slice only.' if mode == 'live' else 'NYC Open Data API DEVELOPMENT FALLBACK: direct API results are not Zetaris results and do not satisfy the sponsor data-layer requirement.',
        'Record status is the supplied city status, not an independent inspection of current conditions.',
        'Deterministic legal research uses a local curated catalog; current operative law has not been retrieved or verified.',
        'An administrative or reporting violation does not itself establish an infestation, lack of heat, or another physical condition.',
    ]
    if any(entry['rule'] == 'R5' for entry in trace):
        limitations.append('The unchanged team Critic R5 holds distinct same-day/address violation IDs as possible collisions; this is not proof they are duplicates, and those records do not support the published findings.')
    context = InvestigationContext(data_mode=mode, data_provider=provider.name, identity=identity,
        record_matches=matches, evidence=evidence, as_of=datetime.now(UTC).date(), notes=' '.join(limitations))
    result = (workflow or LegalResearchWorkflow(reasoning_mode=reasoning_mode)).run(task, context, budget=budget)
    result.caveats = list(dict.fromkeys([*limitations, *result.caveats]))
    pack = write_report(result, evidence, output_dir, trace, identity_records=[identity_record])
    output = Path(output_dir)
    capture = {'capture_type':'recorded_real_hpd_data', 'original_data_mode':mode,
        'original_provider':provider.name, 'captured_at':datetime.now(UTC).isoformat(),
        'batches':[b.capture() for b in (seed, building_batch, batch)],
        'identity_source_records':[identity_record.model_dump(mode='json')],
        'task':task.model_dump(mode='json'), 'context':context.model_dump(mode='json'),
        'building_card':card, 'limitations':limitations}
    capture['context']['data_mode'] = 'recorded_replay'
    (output / 'recorded_hpd_investigation.json').write_text(json.dumps(capture, indent=2)+'\n')
    return result, pack
