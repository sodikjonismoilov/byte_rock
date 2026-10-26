"""Explicit row mapping only. Transport/auth/schema discovery belong to Clerk.

No endpoint, table name or column spelling is assumed. ColumnMap must be filled
from the accessible Zetaris schema, never inferred from a model response.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
if __package__ and __package__.startswith("agents.legal_agent"):
    from ..models.identity import IdentityCandidate, IdentifierEvidence
else:
    from models.identity import IdentityCandidate, IdentifierEvidence
if __package__ and __package__.startswith("agents.legal_agent"):
    from ..models.schemas import EvidenceItem, EvidenceKind
else:
    from models.schemas import EvidenceItem, EvidenceKind


class ColumnMap(BaseModel):
    dataset: str = Field(min_length=1)
    source: str = Field(min_length=1)
    record_id: str
    address: str
    description: str
    event_date: str
    status: str
    kind: EvidenceKind
    scope: Literal['building', 'property', 'unit', 'entity']
    identifiers: dict[Literal['bin', 'bbl', 'hpd_building_id'], str] = Field(default_factory=dict)
    source_url: str | None = None
    borough: str | None = None
    unit: str | None = None
    violation_class: str | None = None
    issue: str | None = None
    matcher_confidence: str | None = None
    latitude: str | None = None
    longitude: str | None = None


def map_rows(rows, mapping: ColumnMap, *, retrieved_at: datetime):
    """Map genuine loader rows; kind/scope are configured per source semantics.

    Mapping does not assert identifiers authoritative or invent a URL/date. A
    missing required column is an error, a null source value remains unknown.
    """
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError('Retrieval time must include a timezone')
    evidence = []
    for row in rows:
        rid = row[mapping.record_id]
        if rid is None or not str(rid).strip():
            raise ValueError('Original source record ID is required')
        meta = {'dataset': mapping.dataset, 'origin_source': mapping.dataset,
                'origin_record_id': str(rid), 'retrieved_at': retrieved_at.isoformat(),
                'scope': mapping.scope}
        for kind, column in mapping.identifiers.items():
            if row[column] is not None:
                meta[kind] = str(row[column]).strip()
        for field in ('source_url', 'unit'):
            column = getattr(mapping, field)
            if column:
                meta[field] = row[column]
        for field, target in (('matcher_confidence', 'matcher_confidence'), ('latitude', 'lat'), ('longitude', 'lon')):
            column = getattr(mapping, field)
            if column and row[column] is not None:
                meta[target] = float(row[column])
        if mapping.issue:
            meta['issue'] = mapping.issue
        when = row[mapping.event_date]
        if isinstance(when, datetime):
            when = when.date()
        elif isinstance(when, str) and 'T' in when:
            when = datetime.fromisoformat(when.replace('Z', '+00:00')).date()
        evidence.append(EvidenceItem(evidence_id=f'{mapping.dataset}:{rid}', kind=mapping.kind,
            source=mapping.source, date=when, description=row[mapping.description],
            status=row[mapping.status], building_address=row[mapping.address],
            violation_class=row[mapping.violation_class] if mapping.violation_class else None, metadata=meta))
    if len({e.evidence_id for e in evidence}) != len(evidence):
        raise ValueError('Duplicate dataset-qualified record IDs')
    return evidence


def identity_candidate(record: EvidenceItem, *, borough=None, authoritative=False, aliases=()):
    """Explicit provenance assertion by trusted Clerk; never auto-verify rows."""
    if not record.building_address:
        raise ValueError('An identity candidate needs a source address')
    identifiers = [IdentifierEvidence(kind=k, value=record.metadata[k], source=record.source,
        record_id=record.metadata['origin_record_id'], authoritative=authoritative, fictional=False)
        for k in ('bin', 'bbl', 'hpd_building_id') if record.metadata.get(k)]
    return IdentityCandidate(candidate_id=record.evidence_id, address=record.building_address,
        borough=borough, aliases=list(aliases), identifiers=identifiers)


def map_hpd_rows(rows, *, retrieved_at: datetime, provider='zetaris'):
    """Map HPD wvxf-dwi5 rows queried THROUGH Zetaris after registration.

    Column names verified against NYC's public dataset metadata, not an existing
    Zetaris table. No network call, inferred current conditions or invented BIN.
    Unit records stay unit-scoped; an absent apartment is only building-scoped
    research evidence, not proof that every apartment has a condition.
    """
    from urllib.parse import urlencode
    records = []
    for original in rows:
        row = dict(original)
        if not row.get('housenumber') or not row.get('streetname'):
            raise ValueError('HPD source address components are required')
        row['source_address'] = f'{row["housenumber"]} {row["streetname"]}'
        row['source_record_url'] = 'https://data.cityofnewyork.us/resource/wvxf-dwi5.json?' + urlencode({'violationid': row['violationid']})
        apartment = str(row.get('apartment') or '').strip()
        for key in ('bin', 'bbl', 'buildingid', 'inspectiondate', 'apartment'):
            if key not in row or row[key] == '':
                row[key] = None
        label = 'Zetaris' if provider == 'zetaris' else 'NYC Open Data API DEVELOPMENT FALLBACK'
        mapping = ColumnMap(dataset='wvxf-dwi5', source=f'NYC HPD Housing Maintenance Code Violations via {label}',
            record_id='violationid', address='source_address', description='novdescription',
            event_date='inspectiondate', status='currentstatus', kind='confirmed_violation',
            scope='unit' if apartment else 'building',
            identifiers={'bin': 'bin', 'bbl': 'bbl', 'hpd_building_id': 'buildingid'},
            source_url='source_record_url', unit='apartment', violation_class='class')
        record = map_rows([row], mapping, retrieved_at=retrieved_at)[0]
        record.metadata['data_provider'] = provider
        for key in ('boro', 'boroid', 'zip', 'violationstatus', 'currentstatusdate', 'novissueddate', 'novid'):
            record.metadata[key] = row.get(key)
        records.append(record)
    if len({e.evidence_id for e in records}) != len(records):
        raise ValueError('Duplicate HPD violation IDs')
    return records


def map_hpd_building(row, *, retrieved_at: datetime, provider='zetaris'):
    """Authoritative identity is grounded in Building Files, not violation rows."""
    from urllib.parse import urlencode
    if not row.get('housenumber') or not row.get('streetname') or not row.get('buildingid'):
        raise ValueError('Incomplete Building Files identity record')
    label = 'Zetaris' if provider == 'zetaris' else 'NYC Open Data API DEVELOPMENT FALLBACK'
    metadata = {'dataset':'kj4p-ruqc', 'origin_source':'kj4p-ruqc',
                'origin_record_id':str(row['buildingid']), 'hpd_building_id':str(row['buildingid']),
                'scope':'building', 'data_provider':provider, 'retrieved_at':retrieved_at.isoformat(),
                'source_url':'https://data.cityofnewyork.us/resource/kj4p-ruqc.json?' + urlencode({'buildingid':row['buildingid']})}
    if row.get('bin') and str(row['bin']).isdigit() and len(str(row['bin'])) == 7:
        metadata['bin'] = str(row['bin'])
    if all(str(row.get(k, '')).isdigit() for k in ('boroid','block','lot')):
        borough, block, lot = (int(row[k]) for k in ('boroid','block','lot'))
        if 1 <= borough <= 5 and 0 < block <= 99999 and 0 < lot <= 9999:
            metadata['bbl'] = f'{borough}{block:05d}{lot:04d}'
            metadata['bbl_derivation'] = {k:row[k] for k in ('boroid','block','lot')}
    for key in ('boro','zip','recordstatus','lifecycle','lowhousenumber','highhousenumber'):
        metadata[key] = row.get(key)
    record = EvidenceItem(evidence_id=f'kj4p-ruqc:{row["buildingid"]}', kind='other',
        source=f'NYC HPD Building Files via {label}', date=None,
        description='HPD building identity registry record; not a condition inspection or safety certification.',
        status=row.get('recordstatus'), building_address=f'{row["housenumber"]} {row["streetname"]}', metadata=metadata)
    candidate = identity_candidate(record, borough=row.get('boro'), authoritative=True)
    return candidate, record
