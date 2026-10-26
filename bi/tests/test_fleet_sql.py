import os
from pathlib import Path

import psycopg2
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def db():
    connection = psycopg2.connect(os.environ['DATABASE_URL'])
    with connection.cursor() as cursor:
        cursor.execute((ROOT / 'infra/postgres/schema.sql').read_text())
        cursor.execute((ROOT / 'bi/sql/fleet_overview.sql').read_text())
        cursor.execute("INSERT INTO instrument_type(name,magnitude,unit) VALUES ('test-fleet','Pressure','bar') RETURNING id")
        type_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO instrument_unit(instrument_type_id,serial_number,manufacturer,model) VALUES (%s,'TEST-FLEET','TEST','TEST') RETURNING id", (type_id,))
        instrument_id = cursor.fetchone()[0]
        try:
            yield cursor, instrument_id
        finally:
            connection.rollback()
            connection.close()


def calibrate(cursor, instrument_id, due_days=100, error=0.1, tolerance=1):
    cursor.execute("""INSERT INTO calibration_event(instrument_unit_id,calibration_date,
        next_due_date,error_value,tolerance,result)
        VALUES (%s,CURRENT_DATE-1,CURRENT_DATE+%s,%s,%s,'pass')""",
        (instrument_id, due_days, error, tolerance))


def row(cursor, instrument_id):
    cursor.execute("SELECT traffic_light,primary_reason,documents_to_review FROM passporttwin_bi.fleet_overview WHERE instrument_id=%s", (instrument_id,))
    return cursor.fetchone()


@pytest.mark.parametrize('due,error,tolerance,color,reason', [
    (100,0.1,1,'green','NO_ALERT'), (-1,0.1,1,'red','CALIBRATION_OVERDUE'),
    (0,0.1,1,'yellow','DUE_WITHIN_30_DAYS'), (30,0.1,1,'yellow','DUE_WITHIN_30_DAYS'),
    (31,0.1,1,'green','NO_ALERT'), (100,-1.1,1,'red','OUT_OF_TOLERANCE'),
    (100,0.8,1,'yellow','NEAR_TOLERANCE'), (100,0.1,0,'gray','INVALID_METROLOGY'),
    (100,0.1,None,'gray','INVALID_METROLOGY'), (100,'NaN',1,'gray','INVALID_METROLOGY'),
    (100,0.1,'Infinity','gray','INVALID_METROLOGY'),
])
def test_traffic_light_boundaries(db,due,error,tolerance,color,reason):
    cursor, instrument_id = db
    calibrate(cursor,instrument_id,due,error,tolerance)
    assert row(cursor,instrument_id)[:2] == (color,reason)


def test_unknown_and_retired(db):
    cursor, instrument_id = db
    assert row(cursor,instrument_id)[0] == 'gray'
    cursor.execute("UPDATE instrument_unit SET lifecycle_state='retired' WHERE id=%s",(instrument_id,))
    assert row(cursor,instrument_id) is None


def test_latest_calibration_ignores_future_and_resolves_ties_by_id(db):
    cursor, instrument_id = db
    calibrate(cursor,instrument_id,error=2)
    calibrate(cursor,instrument_id,error=0.1)
    cursor.execute("INSERT INTO calibration_event(instrument_unit_id,calibration_date,next_due_date,error_value,tolerance,result) VALUES (%s,CURRENT_DATE+1,CURRENT_DATE+200,2,1,'fail')",(instrument_id,))
    assert row(cursor,instrument_id)[0] == 'green'


def test_review_count_is_per_instrument_without_multiplying_rows(db):
    cursor, instrument_id = db
    calibrate(cursor,instrument_id)
    for index in range(2):
        cursor.execute("INSERT INTO document(instrument_unit_id,original_filename,file_path,sha256_hash,processing_status) VALUES (%s,'test','test',%s,'REVIEW_REQUIRED')",(instrument_id,f'fleet-hash-{index}'))
    assert row(cursor,instrument_id) == ('yellow','DOCUMENT_REVIEW',2)
    cursor.execute("SELECT COUNT(*) FROM passporttwin_bi.fleet_overview WHERE instrument_id=%s",(instrument_id,))
    assert cursor.fetchone()[0] == 1


def test_missing_due_date_and_red_precedence(db):
    cursor, instrument_id = db
    calibrate(cursor,instrument_id)
    cursor.execute("UPDATE calibration_event SET next_due_date=NULL WHERE instrument_unit_id=%s",(instrument_id,))
    assert row(cursor,instrument_id)[:2] == ('gray','MISSING_DUE_DATE')
    cursor.execute("UPDATE instrument_unit SET lifecycle_state='blocked' WHERE id=%s",(instrument_id,))
    assert row(cursor,instrument_id)[:2] == ('red','LIFECYCLE_ALERT')
