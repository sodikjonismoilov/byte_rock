"""Root R5 sees a content signature in record_date: distinct same-day records are not duplicates."""
from datetime import date

from integration import review_records
from models.schemas import EvidenceItem

CARD = {'address_raw': '686 3 AVENUE', 'bbl': '1012980034'}


def violation(n, *, description='A', apartment=None, bbl='1012980034', raw=True, day=date(1996, 11, 6), **extra):
    row = {'violationid': str(n), 'novid': str(n), 'ordernumber': str(n), 'class': 'C', 'novdescription': description,
           'apartment': apartment, 'inspectiondate': '1996-11-06', **extra}
    meta = {'dataset': 'wvxf-dwi5', 'bbl': bbl, 'bin': '1036164', 'matcher_confidence': .99, 'scope': 'building'}
    if raw:
        meta['raw_record'] = row
    return EvidenceItem(evidence_id=f'wvxf-dwi5:{n}', kind='confirmed_violation', source='HPD', date=day,
                        description='x', building_address='686 3 AVENUE', metadata=meta)


def rules(records, card=CARD):
    return [(d['decision'], d['rule']) for d in review_records(records, card)[1]]


def test_same_day_violations_differing_in_description_are_both_accepted():
    assert rules([violation(1, description='Rat holes'), violation(2, description='Broken lock')]) == [('accept', None)] * 2


def test_same_day_violations_differing_in_apartment_are_both_accepted():
    assert rules([violation(1, apartment='1A'), violation(2, apartment='2B')]) == [('accept', None)] * 2


def test_records_identical_apart_from_their_ids_are_still_rejected_by_r5():
    assert rules([violation(1), violation(2), violation(3)]) == [('accept', None), ('reject', 'R5'), ('reject', 'R5')]


def test_records_without_raw_record_are_never_collapsed_by_r5():
    assert rules([violation(1, raw=False), violation(2, raw=False)]) == [('accept', None)] * 2


def test_different_days_are_never_duplicates():
    assert rules([violation(1), violation(2, day=date(1996, 11, 7))]) == [('accept', None)] * 2


def test_r1_bbl_mismatch_is_unchanged():
    assert rules([violation(1, bbl='1012980099')]) == [('reject', 'R1')]


def test_r2_borough_conflict_is_unchanged():
    assert rules([violation(1, bbl='3012980034')]) == [('reject', 'R2')]


def test_r4_still_reads_the_year_prefix_of_the_dated_signature():
    card = {**CARD, 'year_built': 1999}
    assert rules([violation(1)], card) == [('reject', 'R4')]  # 1996 < 1999 even with '|signature' appended
    assert rules([violation(2, day=None)], card) == [('accept', None)]  # undated: R4 not applicable, as before
