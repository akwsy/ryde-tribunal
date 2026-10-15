"""Exercise assembled API and restart persistence using synthetic submission data only."""
import json
from pathlib import Path
import httpx
import psycopg
from app.settings import Settings
from app.persistence.postgres_store import PostgresResultStore


def run(env_file,output):
    settings=Settings(_env_file=env_file)
    if 'ryde_tribunal_submission_' not in settings.tribunal_database_dsn:
        raise ValueError('Only isolated submission database allowed')
    with psycopg.connect(settings.tribunal_database_dsn) as conn:
        assert conn.execute('SELECT current_database()').fetchone()[0].startswith('ryde_tribunal_submission_')
    client=httpx.Client(base_url='http://127.0.0.1:8000/api/v1',timeout=180)
    assert client.get('/health').json()['database']=='ok'
    trips=client.get('/trips',params={'query':'','limit':20}).json()['items']
    checks=[];hdr={'X-Reviewer-Id':'REV-SYNTHETIC-INTEGRATION-TEST'}
    for category,status in [('route_deviation','completed'),('no_show_charge','cancelled_after_arrival')]:
        ride=next(x for x in trips if x['status']==status)
        file=client.post('/disputes',headers=hdr,json={'category':category,'ride_id':ride['ride_id'],
            'filed_by':'rider','subject':'Synthetic integration smoke','description':'Generated test case; check evidence and current policy.'})
        assert file.status_code==201,file.text
        cid=file.json()['case_id']
        response=client.post('/disputes/'+cid+'/adjudicate',headers=hdr)
        assert response.status_code==200,response.text
        result=response.json();trace=client.get('/disputes/'+cid+'/trace')
        assert trace.status_code==200 and trace.json()['events']
        rebuilt=PostgresResultStore(settings.tribunal_database_dsn)
        stored=rebuilt.get_case_result(cid)
        assert stored['trace']==result['trace']
        assert stored['model_proposed_ruling']==result['model_proposed_ruling']
        for ref in result['judge']['evidence_references']:
            assert client.get('/evidence/'+ref).status_code==200
        review_test = False
        if category == 'route_deviation':
            proposed=result['model_proposed_ruling']
            approved=client.post('/disputes/'+cid+'/approve',headers=hdr,json={'note':'Synthetic integration test of reviewer persistence; not a human training label.'})
            assert approved.status_code==200
            overridden=client.post('/disputes/'+cid+'/override',headers=hdr,json={'ruling_type':'no_action',
                'recommended_action':{'description':'Synthetic reviewer-flow test; no funds executed','delivery':'none'},
                'reason_code':'other','rationale':'Synthetic integration test only; verify separate proposal and reviewer record.'})
            assert overridden.status_code==200,overridden.text
            assert overridden.json()['model_proposed_ruling']==proposed
            assert rebuilt.get_case_result(cid)['reviewer_approved_ruling']['rationale'].startswith('Synthetic integration test')
            review_test=True
        checks.append({'reviewer_flow_test':review_test,'category' :category,'case_id':cid,'status':result['status'],
            'synthetic_reasoning':result['synthetic_reasoning'],'trace_events':len(result['trace']),
            'restart_persistence':True})
    target=Path(output);target.mkdir(parents=True,exist_ok=True)
    (target/'stack-smoke.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--env-file',required=True);p.add_argument('--output',required=True);a=p.parse_args();run(a.env_file,a.output)
