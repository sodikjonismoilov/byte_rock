import pytest
from identity import resolve_building_identity, match_record
from models.schemas import EvidenceItem


def record(**meta):
    return EvidenceItem(evidence_id='r', kind='complaint', source='fictional', description='heat',
                        building_address='214 E 7th St', metadata=meta)


@pytest.mark.parametrize('address', ['214 East 7th Street', ' 214 e 7th st. ', '216 East 7th Street'])
def test_addresses(address):
    result = resolve_building_identity(address, {})
    assert result['identifiers']['bin'] == '1000001'
    assert result['verification_status'] == 'sample'
    assert not result['verified_identifiers']


def test_multiple_buildings_and_conflicting_bins():
    r = resolve_building_identity('214 E 7th St')
    c = r['candidates'][0]
    assert resolve_building_identity(c['address'], {'candidates':[c,c]})['verification_status'] == 'ambiguous'
    c['identifiers'].append(dict(c['identifiers'][0], value='1000099'))
    assert resolve_building_identity(c['address'], {'candidates':[c]})['verification_status'] == 'ambiguous'


def test_record_identifiers_win_over_address():
    r = resolve_building_identity('214 E 7th St')
    assert match_record(record(bin='1000099'), r).decision == 'rejected'
    assert match_record(record(bbl='1003890024'), r).decision == 'quarantined'
    assert match_record(record(bbl='1003890024', scope='property'), r).decision == 'accepted'
    assert match_record(record(bin='1000001'), r).decision == 'accepted'


def test_missing_unrelated_and_unit():
    assert resolve_building_identity('999 Unknown St')['verification_status'] == 'missing'
    r = resolve_building_identity('214 E 7th St Apt 4B')
    assert r['unit'] == '4B'
    assert match_record(record(scope='unit',unit='2A'),r).decision == 'quarantined'
    e = record(); e.building_address = '410 West 145th Street'
    assert match_record(e,r).decision == 'rejected'
    c = dict(candidate_id='empty',address='1 Test St')
    assert resolve_building_identity('1 Test St',{'candidates':[c]})['verification_status'] == 'unverified'


def test_distinct_buildings_on_same_tax_lot_and_borough():
    r=resolve_building_identity('214 East 7th Street')
    first=r['candidates'][0]
    import copy
    second=copy.deepcopy(first)
    second['candidate_id']='second-building'
    second['address']='218 East 7th Street'
    second['aliases']=['214 East 7th Street']
    second['identifiers'][0]['value']='1000099'
    ambiguous=resolve_building_identity('214 E 7th St',{'candidates':[first,second]})
    assert ambiguous['verification_status']=='ambiguous'
    assert not ambiguous['identifiers']
    assert resolve_building_identity('214 E 7th St',{'borough':'Queens'})['verification_status']=='missing'


def test_authoritative_provenance_and_invalid_identifier():
    r=resolve_building_identity('214 East 7th Street')
    candidate=r['candidates'][0]
    for id in candidate['identifiers']:
        id.update(authoritative=True,fictional=False,source='Mock authoritative adapter')
    result=resolve_building_identity(candidate['address'],{'candidates':[candidate]})
    assert result['verification_status']=='verified'
    assert len(result['verified_identifiers'])==2
    candidate['identifiers'][0]['value']='invented'
    with pytest.raises(ValueError): resolve_building_identity(candidate['address'],{'candidates':[candidate]})
