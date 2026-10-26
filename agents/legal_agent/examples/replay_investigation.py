"""Replay a Clerk-captured real snapshot. Does not connect to Zetaris.

Run from legal_agent: python examples/replay_investigation.py snapshot.json
Snapshot keys: task, context, building_card. Keep provenance in source evidence.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integration import review_records
from models.schemas import EvidenceItem, InvestigationContext, LegalIssueTask
from reporting import write_report
from workflow import LegalResearchWorkflow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot')
    parser.add_argument('--output', default=str(Path(__file__).resolve().parents[3] / 'reports'))
    args = parser.parse_args()
    snapshot = json.loads(Path(args.snapshot).read_text())
    context = InvestigationContext.model_validate(snapshot['context'])
    if context.data_mode not in {'live', 'recorded_replay'}:
        raise ValueError('This runner requires a real-record capture, not sample/mock data')
    context.data_mode = 'recorded_replay'
    if not context.identity_candidates and not context.identity:
        raise ValueError('Real identity candidate provenance is required')
    for e in context.evidence:
        if not all(e.metadata.get(k) for k in ('dataset', 'origin_record_id', 'retrieved_at')):
            raise ValueError('Replay records require dataset, source ID and retrieval timestamp')
        if e.evidence_id != f'{e.metadata["dataset"]}:{e.metadata["origin_record_id"]}':
            raise ValueError('Replay evidence IDs must be dataset-qualified')
    context.record_matches, decisions = review_records(context.evidence, snapshot['building_card'])
    result = LegalResearchWorkflow().run(LegalIssueTask.model_validate(snapshot['task']), context)
    result.caveats = list(dict.fromkeys([*snapshot.get('limitations', []), *result.caveats]))
    identity_records = [EvidenceItem.model_validate(e) for e in snapshot.get('identity_source_records', [])]
    write_report(result, context.evidence, args.output, decisions, identity_records=identity_records)
    print(f'Recorded replay: {result.status.value}; reports in {args.output}')


if __name__ == '__main__':
    main()
