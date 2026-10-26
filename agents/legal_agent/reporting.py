"""Minimal local verification renderer; team Reporter owns product verdicts."""
import json
from pathlib import Path

if __package__ and __package__.startswith("agents.legal_agent"):
    from .integration import board_update
else:
    from integration import board_update


def write_report(result, evidence, output_dir, root_decisions=(), *, identity_records=()):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    board = board_update(result, evidence, root_decisions)
    pack = {'report_type': 'legal_research_only', 'safety_certification': False,
            'publication_note': 'Only board_update.legal_findings are publishable; result retains drafts and review diagnostics for audit.',
            'result': result.model_dump(mode='json'), 'board_update': board,
            'identity_source_records':[e.model_dump(mode='json') for e in identity_records]}
    (output / 'sample_report.json').write_text(json.dumps(pack, indent=2) + '\n')
    lines = ['# Legal investigation', '', f'Data mode: {result.data_mode}',
             f'Provider: {result.data_provider}', f'Address: {result.building.address}', f'Status: {result.status.value}',
             '', 'Legal review is not a certification of rental safety.']
    if any(i.code == 'applicability_unresolved' for i in result.critic_issues):
        lines += ['', 'Operative legal applicability is unverified. Authorities below are background research, not findings of legal liability.']
    lines += ['', '## Identity', '']
    if result.identity:
        lines += [f'{result.identity.canonical_address}; verification: {result.identity.verification_status}.', '']
        lines.extend(f'- {kind}: {value}' for kind, value in result.identity.identifiers.items())
    lines += ['', '## Reviewed findings']
    for finding in board['legal_findings']:
        lines += ['', finding['summary'], 'Evidence: ' + ', '.join(finding['evidence_ids']), '']
        lines.extend('- HPD record reports: ' + fact for fact in finding['supported_facts'])
        lines.extend(f'- {c["statement"]} (authorities: {", ".join(c["source_ids"])})' for c in finding['legal_conclusions'])
    lines += ['', '## Source records']
    for e in [*identity_records, *evidence]:
        lines.append(f'- {e.evidence_id}; {e.source}; original ID={e.metadata.get("origin_record_id")}; event={e.date}; status={e.status}; scope={e.metadata.get("scope")}; retrieved={e.metadata.get("retrieved_at")}; URL={e.metadata.get("source_url") or "not supplied"}')
    lines += ['', '## Attribution review']
    lines.extend(f'- {entry["record_id"]}: {entry["decision"]}; rule={entry["rule"]}; {entry["reason"]}' for entry in root_decisions)
    lines += ['', '## Legal authorities']
    lines.extend(f'- [{s.title}]({s.url}): {s.identifier}; {s.temporal_limitations}' for s in result.legal_sources)
    lines += ['', '## Limitations and follow-up']
    lines.extend('- ' + text for text in [*result.caveats, *result.research_requests, *[i.message for i in result.critic_issues]])
    for gap in board['coverage_gaps']:
        lines.append('- ' + gap['summary'])
    lines += ['', '## Review history']
    lines.extend(f'- Review {i + 1}: {r.outcome.value}; ' + '; '.join(x.message for x in r.issues) for i, r in enumerate(result.review_history))
    (output / 'sample_report.md').write_text('\n'.join(lines) + '\n')
    return pack
