"""Presentation-only regressions; facts are already accepted by the investigation."""
import copy
from risk_reporting import write_renter_report


def fact(**changes):
    result={'finding_id':'fact-1','dataset':'3h2n-5cm9','record_id':'synthetic-1','kind':'confirmed_violation',
        'description':'Synthetic boiler record','event_date':'2009-01-01','recorded_status':'V*-DOB VIOLATION - DISMISSED',
        'scope':'building','source_url':'https://data.cityofnewyork.us/resource/3h2n-5cm9.json?id=synthetic-1',
        'categories':['construction'],'unknowns':['Historical records do not establish current conditions.']}
    result.update(changes);return result


def report():
    return {'request':{'original_input':'1 Mock Street'},'generated_at':'2026-01-01T12:00:00+00:00','provider':'synthetic-fixture','data_mode':'recorded_replay',
        'identity':{'canonical_address':'1 Mock Street, Manhattan','verification_status':'verified','identifiers':{'bin':'1000001'}},
        'factual_findings':[fact()],'coverage':[{'source':'dob_violations','title':'DOB Violations','status':'retrieved','complete_for_filter':True}],
        'legal_assessment':{'status':'inconclusive','errors':[{'message':'Invalid Critic response'}]},
        'board_update':{'legal_findings':[],'critic_outcome':None},'limitations':['The records describe a bounded slice.']}


def render(value,tmp_path):return write_renter_report(value,tmp_path).read_text()


def test_overview_and_plain_summary_use_accepted_records_only(tmp_path):
    value=report();value['legal_assessment']['findings']=[{'summary':'UNSUPPORTED LIABILITY'}]
    original=copy.deepcopy(value);text=render(value,tmp_path)
    assert '## Property overview' in text and '1000001' in text and value['generated_at'] in text
    assert '1 accepted agency record' in text and '1 recorded violation' in text
    assert 'UNSUPPORTED LIABILITY' not in text and 'PARTIAL — FACTUAL-ONLY' in text
    assert value==original


def test_findings_grouped_without_empty_topics(tmp_path):
    value=report();value['factual_findings']+=[fact(dataset='wvxf-dwi5',record_id='hpd',categories=['maintenance']),
        fact(dataset='ipu4-2q9a',record_id='permit',kind='permit'),fact(dataset='jz4z-kudi',record_id='oath',kind='case_filing'),
        fact(dataset='tesw-yqqr',record_id='registration',kind='other',categories=['identity'])]
    text=render(value,tmp_path)
    for title in ['Building maintenance and housing violations','Building safety and DOB violations','Permits and construction activity','Litigation and administrative proceedings','Other relevant records']:
        assert text.count('## '+title)==1
    single=render(report(),tmp_path)
    assert '## Building maintenance' not in single and '## Permits' not in single


def test_original_status_dates_ids_and_official_links_are_preserved(tmp_path):
    value=report();text=render(value,tmp_path)
    assert '[3h2n-5cm9:synthetic-1]('+value['factual_findings'][0]['source_url']+')' in text
    assert '2009-01-01' in text and 'V\\*-DOB VIOLATION - DISMISSED' in text
    assert 'do not establish current' in text


def test_all_original_statuses_remain_distinct(tmp_path):
    value=report();statuses=['OPEN','CLOSED','PENDING','DISMISSED','PAID IN FULL',None]
    value['factual_findings']=[fact(record_id=str(i),recorded_status=s) for i,s in enumerate(statuses)]
    text=render(value,tmp_path)
    for status in statuses:assert '**'+(status or 'Unknown')+'**' in text


def test_no_record_results_distinguished_from_failed_or_unavailable_queries(tmp_path):
    value=report();value['coverage']=[{'title':'No match source','status':'no_records','complete_for_filter':True},
        {'title':'Timed-out source','status':'unavailable','reason':'Request timed out','complete_for_filter':False},
        {'title':'Paged source','status':'bounded','reason':'Page cap reached','complete_for_filter':False},
        {'title':'Court source','status':'manual_only','complete_for_filter':False}]
    text=render(value,tmp_path)
    assert 'No records returned for the queried filters:** No match source' in text
    assert '**Unavailable:** Timed-out source. Request timed out' in text
    assert '**Pagination limited:** Paged source' in text and '**Manual verification required:** Court source' in text
    assert 'not proof of no problems' in text


def test_invalid_critic_or_root_block_cannot_render_draft_legal_claims(tmp_path):
    for outcome in [None,'BLOCKED','REVISE']:
        value=report();value['legal_assessment'].update(status='inconclusive',critic_outcome=outcome)
        value['board_update'].update(critic_outcome='PASS',legal_findings=[{'summary':'SHOULD NOT APPEAR'}])
        text=render(value,tmp_path)
        assert 'SHOULD NOT APPEAR' not in text and 'Legal assessment remains incomplete' in text
        assert 'synthetic-1' in text


def test_reviewed_legal_context_uses_published_canonical_citations(tmp_path):
    value=report();value['legal_assessment'].update(status='completed',critic_outcome='PASS')
    value['board_update'].update(critic_outcome='PASS',legal_findings=[{'summary':'Published observation','legal_conclusions':[
        {'statement':'Current official guidance states: a verified quotation.', 'citations':[{'authority_id':'hpd-heat-hot-water','title':'Official heat guidance','source_url':'https://www.nyc.gov/site/hpd/services-and-information/heat-and-hot-water-information.page'}]}]}])
    text=render(value,tmp_path)
    assert '**COMPLETE' in text and 'Published observation' in text and '[Official heat guidance](https://www.nyc.gov/' in text


def test_empty_results_and_missing_fields_render_without_claiming_safety(tmp_path):
    text=render({},tmp_path)
    assert '**INCONCLUSIVE' in text and 'No accepted factual findings' in text
    assert 'Address not supplied' in text and '## Building safety' not in text
    value=report();value['factual_findings']=[{}];text=render(value,tmp_path)
    assert 'Unknown' in text and 'source link not supplied' in text


def test_no_fabricated_risk_or_severity_from_arbitrary_metadata(tmp_path):
    value=report();value['risk_score']=99;value['factual_findings'][0]['risk_score']='HIGH RISK'
    text=render(value,tmp_path)
    assert 'HIGH RISK' not in text and 'risk score' not in text.lower() and 'landlord is liable' not in text.lower()
    assert 'Synthetic boiler record' in text


def test_special_characters_and_untrusted_links_are_safe(tmp_path):
    value=report();value['identity']['canonical_address']='<script>alert(1)</script> [x]*'
    value['factual_findings']=[fact(description='<b> OPEN [not a link](javascript:bad) * status',source_url='javascript:alert(1)')]
    text=render(value,tmp_path)
    assert '<script>' not in text and '<b>' not in text and '&lt;script&gt;' in text
    assert '[not a link](javascript:bad)' not in text and '(javascript:alert(1))' not in text
    assert 'source link not supplied' in text


def test_repetitive_caveats_deduplicated_but_conflicts_retained(tmp_path):
    value=report();value['factual_findings']=[fact(),fact(record_id='2',unknowns=['Historical records do not establish current conditions.','Contradictory agency statuses remain unresolved.'])]
    text=render(value,tmp_path)
    assert text.count('Historical records do not establish current conditions.')==1
    assert 'Contradictory agency statuses remain unresolved.' in text
    assert 'synthetic-1' in text and '3h2n-5cm9:2' in text


def test_zero_rows_from_incomplete_query_not_presented_as_complete_no_match(tmp_path):
    value=report();value['coverage']=[{'title':'Incomplete zero rows','status':'no_records','complete_for_filter':False,'reason':'Partial response'}]
    text=render(value,tmp_path)
    assert 'No records returned for the queried filters' not in text
    assert 'Incomplete query; no rows in retrieved slice' in text
