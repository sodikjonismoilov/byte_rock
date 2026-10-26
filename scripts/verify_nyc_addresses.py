"""Real multi-borough identity retrieval smoke test; does not certify tenancy risk."""
from datetime import UTC,datetime
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agents.legal_agent.address_investigation import building_where,parse_address
from agents.legal_agent.identity import resolve_building_identity
from agents.legal_agent.tools.address_data import DynamicZetarisProvider
from agents.legal_agent.tools.source_registry import load_registry
from agents.legal_agent.tools.zetaris import map_hpd_building


def main():
    if __package__:
        from .zetaris_api import zetaris_request
    else:
        from zetaris_api import zetaris_request
    provider=DynamicZetarisProvider(zetaris_request,engine_id=os.environ.get('ZETARIS_ENGINE_ID'),page_size=2,max_pages=1,max_requests=15)
    source=load_registry()['hpd_buildings'];cases=[]
    try:
        for code in ('1','2','3','4','5'):
            seed=provider.fetch_where(source,f"boroid = {code} AND legalclassa > 0 AND recordstatus = 'Active'",max_pages=1)
            if not seed.rows:
                cases.append({'borough_code':code,'status':'source_unavailable','retrieval':seed.as_dict()});continue
            row=seed.rows[0]
            address=str(row['housenumber'])+' '+row['streetname']
            request=parse_address(address,row['boro'])
            result=provider.fetch_where(source,building_where(source,request),max_pages=1)
            candidates=[]
            for item in result.rows:
                candidate,_=map_hpd_building(item,retrieved_at=datetime.now(UTC),provider='zetaris')
                candidates.append(candidate.model_dump(mode='json'))
            identity=resolve_building_identity(address,{'candidates':candidates,'borough':row['boro']})
            if not result.complete:identity['verification_status']='ambiguous'
            cases.append({'borough_code':code,'address':address,'borough':row['boro'],'zip':row.get('zip'),
                'status':identity['verification_status'],'identity':identity,'retrieval':result.as_dict(),
                'source_selection':seed.as_dict()})
            print(row['boro']+': '+address+'; '+identity['verification_status'],flush=True)
    finally:provider.close()
    capture={'capture_type':'live_zetaris_multi_borough_identity_checks','captured_at':datetime.now(UTC).isoformat(),
        'cases':cases,'cleanup':provider.events[-1],
        'limitation':'Each address was selected from actual Building Files rows and queried again by address/borough. This validates identity retrieval, not complete risk coverage.'}
    (ROOT/'reports'/'multi_borough_addresses.json').write_text(json.dumps(capture,indent=2)+'\n')


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Address verification stopped: '+type(error).__name__,file=sys.stderr)
        raise SystemExit(1)
