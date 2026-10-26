"""Source semantics and attribution, independent of transport/provider."""
from datetime import datetime
import json
from urllib.parse import urlencode, quote

if __package__ and __package__.startswith("agents.legal_agent"):
    from ..models.schemas import EvidenceItem
else:
    from models.schemas import EvidenceItem
if __package__ and __package__.startswith("agents.legal_agent"):
    from ..tools.address_data import equals, literal
else:
    from tools.address_data import equals, literal

BOROUGHS={'1':'MANHATTAN','2':'BRONX','3':'BROOKLYN','4':'QUEENS','5':'STATEN ISLAND'}


def normalize_agency_status(status, *, raw=None):
    """Canonical comparison state, never a replacement for agency wording.

    Closed is not 'corrected', and certification is not independent verification.
    HPD's separate violationstatus field is preferred over ambiguous NOV wording.
    """
    raw=raw or {}
    value=str(raw.get('violationstatus') or status or '').strip().upper().replace(' ','_')
    aliases={'OPEN':'open','VIOLATION_OPEN':'open','ACTIVE':'open','UNVERIFIED':'unverified',
        'CLOSED':'closed','CLOSE':'closed','VIOLATION_CLOSED':'closed','INACTIVE':'closed',
        'CORRECTED':'corrected','NO_VIOLATION':'no_violation','CLOSED_NO_VIOLATION':'closed_no_violation',
        'CLOSED_NO_ACCESS':'closed_no_access','NO_ACCESS':'closed_no_access'}
    return aliases.get(value,'unknown')


def identifier_where(source, identity, *, registration_id=None):
    ids=identity.identifiers
    for kind in ('hpd_building_id','bin','bbl'):
        field=source['identifiers'].get(kind)
        if field and ids.get(kind):
            return equals(source,field,ids[kind]),kind
    if registration_id and source['identifiers'].get('registration_id'):
        return equals(source,source['identifiers']['registration_id'],registration_id),'registration_id'
    if source['key']=='fdny_oath' and ids.get('bbl'):
        bbl=ids['bbl'];boro=BOROUGHS.get(bbl[0])
        # Official violation LOCATION fields, never respondent mailing address.
        fields=[('violation_location_block_no',str(int(bbl[1:6])),5),('violation_location_lot_no',str(int(bbl[6:])),4)]
        clauses=[]
        for field,value,width in fields:
            variants={value,value.zfill(width),value.zfill(6)}
            clauses.append('('+' OR '.join(equals(source,field,x) for x in sorted(variants))+')')
        aliases=[boro,'NEW YORK'] if boro=='MANHATTAN' else [boro]
        clauses.append('('+' OR '.join(equals(source,'violation_location_borough',x) for x in aliases)+')')
        clauses.append(equals(source,'issuing_agency',source['extra_filters']['issuing_agency']))
        return ' AND '.join(clauses),'property_components'
    return None,None


def parse_date(value):
    if value is None or not str(value).strip():return None
    text=str(value).strip()
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f','%Y-%m-%dT%H:%M:%S','%Y-%m-%d','%Y%m%d','%m/%d/%Y','%m/%d/%Y %I:%M:%S %p'):
        try:return datetime.strptime(text,fmt).date()
        except ValueError:pass
    try:return datetime.fromisoformat(text.replace('Z','+00:00')).date()
    except ValueError:return None


def bbl_from_parts(row,boro_field,block_field='block',lot_field='lot'):
    boro=str(row.get(boro_field,''))
    boro=next((k for k,v in BOROUGHS.items() if v==boro.upper()),boro)
    values=[boro,str(row.get(block_field,'')),str(row.get(lot_field,''))]
    if all(v.isdigit() for v in values):
        b,bk,lot=map(int,values)
        if 1<=b<=5 and 0<bk<100000 and 0<lot<10000:return f'{b}{bk:05d}{lot:04d}'
    return None


def map_source_rows(source, retrieval, *, linked_registration=None):
    """Keep agency event semantics; summonses and filings remain allegations."""
    records=[]
    page_times=[p['retrieved_at'] for p in retrieval.pages if p.get('status')=='ok']
    row_times=[p['retrieved_at'] for p in retrieval.pages if p.get('status')=='ok' for _ in range(p.get('row_count',0))]
    for index,row in enumerate(retrieval.rows):
        components={k:str(row[k]) for k in source['record_id_fields']}
        rid='|'.join(components.values())
        address=' '.join(str(row.get(k) or '').strip() for k in source['address_fields']).strip() or None
        metadata={'dataset':source['dataset'],'source_key':source['key'],'source_agency':source['publisher'],
            'origin_source':source['dataset'],'origin_record_id':rid,'origin_record_components':components,
            'source_url':f'https://data.cityofnewyork.us/resource/{source["dataset"]}.json?'+urlencode(components),
            'retrieved_at':row_times[index] if index<len(row_times) else page_times[-1] if page_times else None,'data_provider':retrieval.provider,
            'issue_categories':source['categories'],'issue':'maintenance' if 'habitability' in source['categories'] else 'construction' if 'building_safety' in source['categories'] else 'litigation' if 'eviction_litigation' in source['categories'] else 'identity',
            'raw_record':row,'scope':source.get('scope','building')}
        for kind,field in source['identifiers'].items():
            if row.get(field):metadata[kind]=str(row[field])
        boro_field=source.get('borough_field')
        if not metadata.get('bbl') and boro_field and 'block' in row and 'lot' in row:
            derived=bbl_from_parts(row,boro_field)
            if derived:
                metadata['bbl']=derived;metadata['bbl_derivation']={k:row[k] for k in (boro_field,'block','lot')}
        if source['key']=='fdny_oath':
            derived=bbl_from_parts(row,'violation_location_borough','violation_location_block_no','violation_location_lot_no')
            if derived:metadata['bbl']=derived
        unit=str(row.get(source.get('unit_field')) or '').strip()
        if unit:metadata.update(scope='unit',unit=unit)
        if not metadata.get('bin') and not metadata.get('hpd_building_id') and metadata.get('bbl'):
            metadata['scope']='property' if not unit else 'unit'
        if source['key']=='registration_contacts':
            metadata['scope']='entity'
            if linked_registration and str(row.get('registrationid'))==linked_registration.metadata.get('origin_record_id'):
                metadata.update(scope='building',hpd_building_id=linked_registration.metadata['hpd_building_id'],
                    linkage_parent_evidence_ids=[linked_registration.evidence_id],address_provenance=linked_registration.evidence_id)
                address=linked_registration.building_address
        description='; '.join(f'{k}: {row[k]}' for k in source['description_fields'] if row.get(k)) or source['title']+' source record'
        rawdate=row.get(source.get('date_field'))
        metadata['normalized_status']=normalize_agency_status(row.get(source.get('status_field')),raw=row)
        metadata['original_event_date']=rawdate
        if rawdate and parse_date(rawdate) is None:metadata['date_parse_limitation']='Unrecognized agency date; original retained'
        # Stage remains conservative even if a source also has judgment fields;
        # original fields stay visible rather than automatic legal conclusions.
        record=EvidenceItem(evidence_id=source['dataset']+':'+quote(rid,safe=''),kind=source['kind'],
            source=source['publisher']+' via '+retrieval.provider,date=parse_date(rawdate),description=description,
            status=str(row[source['status_field']]) if source.get('status_field') and row.get(source['status_field']) is not None else None,
            violation_class=str(row.get('class') or row.get('severity') or '') or None,
            building_address=address,metadata=metadata)
        records.append(record)
    return records
