"""Conservative event comparison; absence of a violation never disproves a complaint."""
from collections import defaultdict
from datetime import date
if __package__ and __package__.startswith("agents.legal_agent"):
    from .models.reconciliation import ReconciliationResult, EvidenceConflict
else:
    from models.reconciliation import ReconciliationResult, EvidenceConflict


if __package__ and __package__.startswith("agents.legal_agent"):
    from .tools.risk_mapping import normalize_agency_status
else:
    from tools.risk_mapping import normalize_agency_status


def reconcile_evidence(evidence, matches=(), findings=(), as_of=None, budget=None):
    as_of = as_of or date.today()
    decisions = {m.evidence_id:m.decision for m in matches}
    result = ReconciliationResult(limitations=['No complete public-record coverage is asserted; source labels are supplied provenance, not independently authenticated.'])
    groups = defaultdict(list)
    for e in evidence:
        if budget: budget.check()
        decision = decisions.get(e.evidence_id, 'quarantined')
        getattr(result, {'accepted':'accepted_ids','rejected':'rejected_ids','quarantined':'quarantined_ids'}[decision]).append(e.evidence_id)
        # A source record copied into another feed is not independent corroboration.
        origin = e.metadata.get('origin_record_id') or e.metadata.get('service_request') or e.metadata.get('nov_id')
        if origin:
            groups[(e.metadata.get('origin_source', e.source), origin)].append(e.evidence_id)
        if e.date and (as_of - e.date).days > 90:
            result.historical_ids.append(e.evidence_id)
    result.duplicate_groups = [ids for ids in groups.values() if len(ids)>1]
    accepted = [e for e in evidence if e.evidence_id in result.accepted_ids]
    for i, left in enumerate(accepted):
        if budget: budget.check()
        for right in accepted[i+1:]:
            if left.metadata.get('issue') != right.metadata.get('issue') or not left.metadata.get('issue'):
                continue
            statuses = {left.metadata.get("normalized_status") or normalize_agency_status(left.status,raw=left.metadata.get("raw_record")), right.metadata.get("normalized_status") or normalize_agency_status(right.status,raw=right.metadata.get("raw_record"))}
            if statuses & {'no_violation', 'closed_no_violation', 'corrected', 'closed_no_access', 'closed'} and statuses & {'open', 'unverified'}:
                result.conflicts.append(EvidenceConflict(category='condition_status_disagreement', evidence_ids=[left.evidence_id,right.evidence_id], explanation=f'Records differ in date/status ({left.date}/{left.status}; {right.date}/{right.status}). Inspection or closure is a point-in-time result; no access is not a negative inspection. Neither proves nor disproves an ongoing condition.'))
    invalid = set(result.rejected_ids + result.quarantined_ids)
    for f in findings:
        if set(f.evidence_ids) & invalid or not set(f.evidence_ids)<=set(result.accepted_ids):
            result.invalidated_finding_ids.append(f.finding_id)
    return result


def invalidate_findings(findings, reconciliation):
    """Clear rejected dependencies rather than leaving apparently supported conclusions."""
    for f in findings:
        if f.finding_id in reconciliation.invalidated_finding_ids:
            f.valid = False
            f.legal_conclusions = []
            f.supported_facts = []
            f.confidence = 'low'
            f.sufficiency = 'insufficient'
            f.notes.append('Invalidated because a dependent property record was rejected, quarantined or unknown.')
    return findings
