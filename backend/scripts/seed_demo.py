"""Add four labelled synthetic fixtures. Existing demo records are never reset."""
from datetime import date,timedelta
import hashlib
import os
from pathlib import Path

from reportlab.pdfgen.canvas import Canvas
from app.core.config import settings
from app.database.session import SessionLocal
from app.models.instrument import InstrumentType,InstrumentUnit
from app.models.calibration import CalibrationEvent
from app.models.document import Document,ExtractedField
from app.services.analytics_snapshots import create_snapshot
from app.services.audit_service import AuditService

CASES=(('PTWIN-DEMO-SANO','Sin alertas',100,'ACCEPTED'),
       ('PTWIN-DEMO-VENCIDO','Calibración vencida',-1,'ACCEPTED'),
       ('PTWIN-DEMO-REVISION','Documento por revisar',90,'REVIEW_REQUIRED'),
       ('PTWIN-DEMO-SIN-HISTORIAL','Sin historial',None,None))


def seed_demo(db,today=None):
    today=today or date.today()
    family=db.query(InstrumentType).filter(InstrumentType.name=='passporttwin_demo_pressure').first()
    if family is None:
        family=InstrumentType(name='passporttwin_demo_pressure',magnitude='Pressure',unit='bar')
        db.add(family);db.flush()
    elif family.unit!='bar':
        raise ValueError('Existing demo family has a different unit; review it before continuing')
    results=[]
    for serial,title,due,status in CASES:
        instrument=db.query(InstrumentUnit).filter(InstrumentUnit.serial_number==serial).first()
        created=instrument is None
        if instrument is not None and instrument.manufacturer!='PassportTwin Demo':
            raise ValueError(f'Refusing to reuse a non-demo instrument: {serial}')
        if created:
            instrument=InstrumentUnit(instrument_type_id=family.id,serial_number=serial,
                manufacturer='PassportTwin Demo',model='Transmisor sintético',location='Laboratorio Demo',criticality='MEDIUM')
            db.add(instrument);db.flush()
            if due is not None:
                for index,error in enumerate([.01,.018,.012,.02,.014,.019,.013,.021]):
                    db.add(CalibrationEvent(instrument_unit_id=instrument.id,
                        calibration_date=today-timedelta(days=(8-index)*30),error_value=error,tolerance=.1,
                        result='pass',next_due_date=today+timedelta(days=due)))
                raw_dir=Path(os.getenv('STORAGE_RAW_DIR','./storage/raw'))/'demo'
                raw_dir.mkdir(parents=True,exist_ok=True)
                file=raw_dir/f'{serial}.pdf'
                fields={'serial_number':serial if status=='ACCEPTED' else 'REVISAR-SERIAL',
                    'calibration_date':(today-timedelta(days=30)).isoformat() if status=='ACCEPTED' else today.isoformat(),
                    'next_due_date':(today+timedelta(days=due)).isoformat(),
                    'error_value':'0.021' if status=='ACCEPTED' else '0.02','tolerance':'0.1','unit':'bar'}
                canvas=Canvas(str(file),invariant=1)
                canvas.setTitle(f'PassportTwin synthetic demo: {serial}')
                canvas.drawString(50,790,'PassportTwin - SYNTHETIC DEMO CERTIFICATE')
                for index,(name,value) in enumerate(fields.items()):canvas.drawString(50,750-index*25,f'{name}: {value}')
                canvas.save()
                digest=hashlib.sha256(file.read_bytes()).hexdigest()
                document=Document(instrument_unit_id=instrument.id,original_filename=file.name,file_path=str(file),
                    sha256_hash=digest,source_type='PDF_CERTIFICATE',processing_status=status)
                db.add(document);db.flush()
                for name,value in fields.items():
                    db.add(ExtractedField(document_id=document.id,field_name=name,raw_value=value,normalized_value=value,
                        confidence='1.0',validation_status=status))
            AuditService.log_event(db=db,entity_name='instrument_unit',entity_id=instrument.id,
                action='DEMO_FIXTURE_CREATED',source='scripts.seed_demo',details={'synthetic':True,'scenario':title})
    db.commit()
    for serial,title,_,_ in CASES:
        instrument=db.query(InstrumentUnit).filter(InstrumentUnit.serial_number==serial).first()
        snapshot=create_snapshot(db,instrument,today)
        results.append({'serial_number':serial,'scenario':title,'snapshot_id':snapshot.id,
            'passport_url':str(settings.passport_frontend_base_url).rstrip('/')+f'/passport/{instrument.public_id}'})
    return results


def main():
    with SessionLocal() as db:
        for result in seed_demo(db):print(f"{result['serial_number']} · {result['scenario']} · {result['passport_url']}")
    print('Datos sintéticos preparados. No se ha ejecutado ingesta ni sincronización AAS; ese recorrido se ensaya por separado.')


if __name__=='__main__':main()
