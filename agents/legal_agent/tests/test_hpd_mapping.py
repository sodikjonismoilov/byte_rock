"""Synthetic row tests for the verified public HPD schema; not NYC captures."""
from datetime import UTC, datetime
import pytest
from tools.zetaris import identity_candidate, map_hpd_rows


def row():
    return {'violationid':'mock-7','housenumber':'1','streetname':'MOCK STREET',
            'buildingid':12345,'bin':'1000001','bbl':'1000010001',
            'inspectiondate':'2026-01-01T00:00:00.000','currentstatus':'VIOLATION CLOSED',
            'novdescription':'Synthetic violation description','class':'B','apartment':'',
            'boro':'MANHATTAN','zip':'10017'}


def test_hpd_map_preserves_origin_status_and_identifiers():
    record = map_hpd_rows([row()], retrieved_at=datetime.now(UTC))[0]
    assert record.evidence_id == 'wvxf-dwi5:mock-7'
    assert record.metadata['origin_record_id'] == 'mock-7'
    assert record.metadata['scope'] == 'building'
    assert record.status == 'VIOLATION CLOSED'
    assert record.metadata['zip'] == '10017'
    assert record.kind.value == 'confirmed_violation'
    assert 'violationid=mock-7' in record.metadata['source_url']
    candidate = identity_candidate(record, borough='MANHATTAN', authoritative=True)
    assert {i.kind for i in candidate.identifiers} == {'bin','bbl','hpd_building_id'}


def test_hpd_map_never_upgrades_unit_scope_or_invents_bin():
    source = row()
    source.update(apartment='4B', bin='', inspectiondate='')
    record = map_hpd_rows([source], retrieved_at=datetime.now(UTC))[0]
    assert record.metadata['scope'] == 'unit'
    assert record.metadata['unit'] == '4B'
    assert 'bin' not in record.metadata
    assert record.date is None


def test_hpd_duplicate_and_missing_address_fail_closed():
    with pytest.raises(ValueError):
        map_hpd_rows([row(),row()], retrieved_at=datetime.now(UTC))
    source = row()
    source['streetname']=''
    with pytest.raises(ValueError):
        map_hpd_rows([source], retrieved_at=datetime.now(UTC))
