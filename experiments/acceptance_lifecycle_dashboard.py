"""Destructive fixtures ONLY on an empty disposable *_test DB and fresh Metabase."""
import argparse,json,os,secrets,sys,time
from datetime import date,timedelta
from pathlib import Path
import requests
from sqlalchemy import text
from sqlalchemy.engine import make_url

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'bi/metabase'))
if not make_url(os.environ['DATABASE_URL']).database.endswith('_test'):
    raise RuntimeError('Refusing to initialize a non-disposable database')
from fastapi.testclient import TestClient
from app.main import app
from app.database.session import engine,SessionLocal
from app.models.instrument import InstrumentType,InstrumentUnit
from app.models.calibration import CalibrationEvent
from app.models.document import Document
from app.models.maintenance import Incident,MaintenanceEvent
from provision_fleet import provision


def run(url):
    if not engine.url.database.endswith('_test'): raise RuntimeError('Disposable database name must end in _test')
    session=requests.Session();session.trust_env=False
    def api(method,path,body=None):
        response=session.request(method,url.rstrip('/')+'/api/'+path,json=body,timeout=60)
        response.raise_for_status();return response.json()
    for _ in range(12):
        try:
            if session.get(url+'/api/health',timeout=3).status_code==200:break
        except requests.RequestException:pass
        time.sleep(5)
    else:raise RuntimeError('Metabase not ready')
    properties=api('GET','session/properties')
    if not properties.get('setup-token'):raise RuntimeError('Metabase must be a fresh disposable instance')
    with SessionLocal() as db:
        if db.query(InstrumentUnit).count() or db.query(InstrumentType).count():raise RuntimeError('Expected empty disposable application DB')
        family=InstrumentType(name='pressure',magnitude='Pressure',unit='bar')
        other=InstrumentType(name='temperature',magnitude='Temperature',unit='C')
        db.add_all([family,other]);db.flush()
        instruments=[]
        for serial,location,due,errors in [('GREEN','Lab A',100,[.1,.12,.09,.11]),('YELLOW','Lab B',20,[.1,.12,.09,.11]),
                                         ('RED','Lab B',-1,[.8,.9,1.05,1.2]),('GRAY','Lab A',None,[])]:
            inst=InstrumentUnit(instrument_type_id=family.id if serial in ('GREEN','RED') else other.id,serial_number=serial,manufacturer='TEST',model='TEST',location=location,
                                lifecycle_state='out_of_tolerance' if serial=='RED' else 'operational')
            db.add(inst);db.flush();instruments.append((serial,inst.id))
            for j,error in enumerate(errors):
                db.add(CalibrationEvent(instrument_unit_id=inst.id,calibration_date=date.today()-timedelta(days=(4-j)*30),
                    next_due_date=date.today()+timedelta(days=due),error_value=error,tolerance=1,
                    result='out_of_tolerance' if error>1 else 'pass'))
            if errors:db.add(Document(instrument_unit_id=inst.id,original_filename='test',file_path='test',sha256_hash=secrets.token_hex(32),processing_status='ACCEPTED'))
        db.commit()
        for file in ('bi/sql/fleet_overview.sql','bi/sql/fleet_analytics.sql'):
            db.connection().exec_driver_sql((ROOT/file).read_text())
        db.commit()
    client=TestClient(app)
    snapshots={}
    for serial,i in instruments:
        response=client.post(f'/api/v1/instruments/{i}/analytics-snapshots');assert response.status_code==201
        snapshots[serial]=response.json()
        assert client.get(f'/api/v1/instruments/{i}/health-score').json()['health_score']==snapshots[serial]['health_score']
    assert snapshots['GRAY']['health_score'] is None
    assert snapshots['RED']['health_score']<snapshots['GREEN']['health_score']
    ids=dict(instruments)
    with SessionLocal() as db:
        db.add(Incident(instrument_unit_id=ids['GREEN'],incident_date=date.today(),severity='HIGH',description='acceptance'))
        db.execute(text('UPDATE analytics_snapshot SET as_of=CURRENT_DATE-1 WHERE instrument_unit_id=:id'),{'id':ids['YELLOW']})
        db.commit()
        rows=db.execute(text('SELECT serial_number,analytics_status,current_health_score FROM passporttwin_bi.fleet_analytics')).all()
        states={r[0]:r[1] for r in rows}
        assert states=={'GREEN':'STALE_INPUTS','YELLOW':'STALE_DATE','RED':'CURRENT','GRAY':'CURRENT'}
        assert all(r[2] is None for r in rows if r[0] in ('GREEN','YELLOW','GRAY'))
    auth=api('POST','setup',{'token':properties['setup-token'],'user':{'first_name':'Test','last_name':'Acceptance','email':'acceptance@example.com','password':secrets.token_urlsafe(32)+'Aa1!'},'prefs':{'site_name':'Disposable acceptance','allow_tracking':False}})
    session.headers['X-Metabase-Session']=auth['id']
    dburl=engine.url
    database=api('POST','database',{'name':'Disposable acceptance','engine':'postgres','details':{'host':dburl.host,'port':dburl.port or 5432,'dbname':dburl.database,'user':dburl.username,'password':dburl.password,'ssl':False}})
    collection=api('POST','collection',{'name':'Acceptance','color':'#509EE3'})
    passport_origin=os.getenv('PASSPORT_FRONTEND_BASE_URL','http://localhost:5173').rstrip('/')
    link=provision(url,database['id'],collection['id'],session,passport_base_url=passport_origin)
    dashboard=api('GET','dashboard/'+link.rsplit('/',1)[-1]);assert len(dashboard['dashcards'])==10
    tests=0
    for card in dashboard['dashcards']:
        for location,family,expected in [(None,None,4),('Lab A',None,2),(None,'pressure',2),('Lab A','pressure',1),(None,'absent',0)]:
            params=[{'id':key,'type':'category','target':['variable',['template-tag',key]],'value':value}
                    for key,value in [('location',location),('family',family)] if value]
            result=api('POST',f"card/{card['card_id']}/query",{'parameters':params})
            assert result['status']=='completed'
            if card['card']['name']=='Instrumentos activos':assert result['data']['rows']==[[expected]]
            if card['card']['name'] in ('Prioridad de intervención','Riesgo experimental · snapshots vigentes'):
                cols=[c['name'] for c in result['data']['cols']]
                assert 'passport_url' in cols and 'measurement_unit' in cols
                for row in result['data']['rows']:
                    assert row[cols.index('passport_url')].startswith(passport_origin+'/passport/')
                    assert row[cols.index('measurement_unit')] in ('bar','C')

            if card['card']['name']=='Riesgo experimental · snapshots vigentes' and not location and not family:
                cols=[c['name'] for c in result['data']['cols']]
                assert result['data']['rows'][0][cols.index('serial_number')]=='RED'
                for row in result['data']['rows']:
                    if row[cols.index('serial_number')] in ('GREEN','YELLOW','GRAY'):
                        assert row[cols.index('current_probability_90')] is None
            tests+=1
    refreshed=client.post(f"/api/v1/instruments/{ids['GREEN']}/analytics-snapshots").json()
    assert refreshed['health_score']==snapshots['GREEN']['health_score']-20
    with SessionLocal() as db:
        db.add(MaintenanceEvent(instrument_unit_id=ids['GREEN'],event_date=date.today(),description='acceptance'));db.commit()
    guarded=client.post(f"/api/v1/instruments/{ids['GREEN']}/analytics-snapshots").json()
    assert guarded['risk_result']['reason']=='INSUFFICIENT_POST_MAINTENANCE_HISTORY' and guarded['health_score'] is None
    return {'metabase_version':properties['version'],'dashboard_cards':10,'dashboard_path':'/dashboard/'+link.rsplit('/',1)[-1],'passport_link_origin':passport_origin,'successful_card_queries':tests,
            'acceptance':'PASS','checks':['parity API/snapshot','family/location/combined/empty filters','risk ordering',
             'missing history','stale inputs','stale date','stale probabilities hidden','incident penalty after refresh','maintenance rebaseline'],
            'scope':'Disposable synthetic acceptance; no shared deployment or real data validation'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--disposable',action='store_true',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    report=run(os.environ['METABASE_URL']);args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
