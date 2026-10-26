"""Verify one genuine row per configured source without claiming property coverage."""
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agents.legal_agent.tools.address_data import DynamicZetarisProvider
from agents.legal_agent.tools.source_registry import load_registry


def main():
    if __package__:
        from .zetaris_api import zetaris_request
    else:
        from zetaris_api import zetaris_request
    provider=DynamicZetarisProvider(zetaris_request,engine_id=os.environ.get('ZETARIS_ENGINE_ID'),page_size=1,max_pages=1,max_requests=20)
    inventory=[]
    try:
        for key,source in load_registry().items():
            if source.get('capability')=='manual_only':
                inventory.append({'source':key,'status':'manual_only','source_url':source['source_url']});continue
            where="upper(issuing_agency) like '%FIRE%'" if key=='fdny_oath' else '1=1'
            result=provider.fetch_where(source,where)
            item={'source':key,'dataset':source['dataset'],'status':'live_row_verified' if result.rows and result.status!='unavailable' else result.status,
                  'row_count':len(result.rows),'pages':result.pages,'agency_id_fields':source['record_id_fields'],
                  'observed_columns':sorted(result.rows[0]) if result.rows else [],
                  'sample_record_components':{k:result.rows[0].get(k) for k in source['record_id_fields']} if result.rows else {}}
            if key=='fdny_oath' and result.rows:item['observed_issuing_agency']=result.rows[0].get('issuing_agency')
            inventory.append(item)
            print(key+': '+item['status'],flush=True)
    finally:provider.close()
    capture={'capture_type':'live_zetaris_source_capability_probe','captured_at':datetime.now(UTC).isoformat(),
             'inventory':inventory,'cleanup':provider.events[-1],
             'limitation':'One general source row verifies connector/schema/agency-ID capability only, not citywide or property-specific coverage. Temporary registrations were removed.'}
    (ROOT/'reports'/'source_runtime_inventory.json').write_text(json.dumps(capture,indent=2)+'\n')


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Source verification stopped: '+type(error).__name__,file=sys.stderr)
        raise SystemExit(1)
