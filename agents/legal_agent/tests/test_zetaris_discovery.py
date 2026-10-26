"""Mock transport tests; no network or real property records."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock


def probe():
    script = Path(__file__).resolve().parents[3] / 'scripts' / 'discover_zetaris.py'
    spec = importlib.util.spec_from_file_location('signsafe_discovery_test', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.discover


def topology_probe():
    script = Path(__file__).resolve().parents[3] / 'scripts' / 'discover_zetaris.py'
    spec = importlib.util.spec_from_file_location('signsafe_topology_test', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.discover_topology


def test_topology_does_not_guess_engine_from_default_database():
    request = Mock(side_effect=[[], [], [], [], {'databases':[]}, {'headers':['database_name'],'data':[['default']]}, {'headers':['alias','name','properties','id','count'],'data':[]}, {'headers':['catalog_name'],'data':[['spark_catalog']]}, {'headers':['table_identifier','catalog_name','catalog_type'],'data':[]}, {'headers':['name'],'data':[]}])
    capture = topology_probe()(request)
    assert capture['engine_id_sent'] is False
    assert 'identity_not_exposed' in capture['engine_resolution']
    assert capture['checks'][0]['count'] == 0
    assert capture['checks'][5]['items'] == [{'database_name':'default'}]
    assert capture['checks'][7]['items'] == [{'catalog_name':'spark_catalog'}]
    assert capture['checks'][8]['count'] == 0
    assert all('engineId' not in c.args[2] for c in request.call_args_list if len(c.args) > 2)


def test_topology_filters_connection_properties():
    request = Mock(side_effect=[[{'id':7,'name':'mock-engine','config':{'password':'mock-secret'}}], [], [], [], {'databases':[]}, {'headers':['database_name'],'data':[['default']]}, {'headers':['alias','properties'],'data':[['mock-catalog','mock-secret']]}, {'headers':['catalog_name'],'data':[['spark_catalog']]}, {'headers':['table_identifier','catalog_name','catalog_type'],'data':[]}, {'headers':['name'],'data':[]}])
    capture = topology_probe()(request)
    assert 'mock-secret' not in json.dumps(capture)
    assert capture['checks'][0]['items'] == [{'id':7,'name':'mock-engine'}]


def test_empty_catalog_is_not_property_evidence():
    request = Mock(side_effect=[{'headers':['1'], 'data':[['1']], 'total':1}, {'headers':['name','description','id'], 'data':[], 'total':0}])
    capture = probe()(request, engine_id='mock-engine')
    assert capture['status'] == 'connected_no_visible_logical_sources'
    assert capture['property_records_retrieved'] == 0
    assert all(c.args[2]['engineId'] == 'mock-engine' for c in request.call_args_list)
    assert [c.args[2]['sql'] for c in request.call_args_list] == ['SELECT 1', 'SHOW DATASOURCES']


def test_errors_do_not_persist_response_bodies_or_secrets():
    request = Mock(side_effect=RuntimeError('mock-sensitive-auth-response'))
    capture = probe()(request)
    assert capture['status'] == 'discovery_failed'
    assert 'mock-sensitive-auth-response' not in json.dumps(capture)


def test_unexpected_headers_do_not_persist_arbitrary_server_data():
    request = Mock(return_value={'headers':['unexpected_private_field'], 'data':[['mock-sensitive-value']]})
    capture = probe()(request)
    assert capture['status'] == 'discovery_failed'
    assert 'mock-sensitive-value' not in json.dumps(capture)
