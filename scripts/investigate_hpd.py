"""Run a genuine HPD investigation; provider selection is explicit.

Zetaris: --provider zetaris --source <actually registered source>
Fallback: --provider nyc-development-fallback (never silently selected)
"""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agents.legal_agent.investigate_property import investigate_property
from agents.legal_agent.tools.property_data import NYCOpenDataDevelopmentProvider, ZetarisPropertyProvider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=['zetaris','nyc-development-fallback'], required=True)
    parser.add_argument('--source')
    parser.add_argument('--buildings-table', default='hpd_buildings')
    parser.add_argument('--violations-table', default='hpd_violations')
    parser.add_argument('--output', type=Path, default=ROOT/'reports')
    args = parser.parse_args()
    if args.provider == 'zetaris':
        if not args.source:
            parser.error('--source must name an actually registered Zetaris source')
        if __package__:
            from .zetaris_api import zetaris_request
        else:
            from zetaris_api import zetaris_request
        provider = ZetarisPropertyProvider(zetaris_request, source=args.source,
            buildings_table=args.buildings_table, violations_table=args.violations_table,
            engine_id=os.environ.get('ZETARIS_ENGINE_ID'))
    else:
        provider = NYCOpenDataDevelopmentProvider()
    try:
        result, pack = investigate_property(provider, args.output)
    except Exception as error:
        print(f'Investigation stopped: {type(error).__name__}. No fictional records or automatic provider substitution were used.')
        return 1
    print(f'Provider: {provider.name}; mode: {result.data_mode}; address: {result.building.address}; unit: {result.building.unit or "building-scoped"}')
    print(f'Identity: {result.identity.verification_status}; legal status: {result.status.value}; accepted records: {len(result.reconciliation.accepted_ids)}')
    print(f'Reports: {args.output}; legal reasoning: {result.reasoning_mode}')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f'Provider setup failed: {type(error).__name__}. Credential-bearing error bodies are withheld.')
        raise SystemExit(1)
