from datetime import date, timedelta
import io,json

import pytest
from reportlab.pdfgen import canvas
from app.api import documents
from app.models.instrument import InstrumentUnit
from tests.test_analytics_snapshots import setup


@pytest.mark.parametrize('scenario',['single','repeated','ambiguous','missing'])
def test_real_pdf_label_does_not_bind_to_label_word_number(setup,tmp_path,monkeypatch,scenario):
    client,db,instrument=setup
    monkeypatch.setattr(documents,'STORAGE_RAW_DIR',str(tmp_path))
    # A plausible catalogue collision proves that the old bug could mislink,
    # not only fail to find the intended instrument.
    phantom=InstrumentUnit(instrument_type_id=instrument.instrument_type_id,serial_number='Number',manufacturer='Synthetic',model='Trap')
    other=InstrumentUnit(instrument_type_id=instrument.instrument_type_id,serial_number='LABEL-OTHER',manufacturer='Synthetic',model='Other')
    db.add_all([phantom,other]);db.flush()
    labels=[f'Serial Number: {instrument.serial_number}']
    if scenario=='repeated':labels.append(f'S/N: {instrument.serial_number}')
    if scenario=='ambiguous':labels.append('Serial: LABEL-OTHER')
    if scenario=='missing':labels=['Serial Number:']
    lines=labels+[f'Calibration Date: {date.today()-timedelta(days=1)}',f'Due Date: {date.today()+timedelta(days=90)}','Max Error: 0.02','Tolerance: 0.1']
    stream=io.BytesIO();pdf=canvas.Canvas(stream,invariant=1)
    for index,line in enumerate(lines):pdf.drawString(40,780-index*22,line)
    pdf.save()
    upload=client.post('/api/v1/documents/upload',files={'file':('serial-label.pdf',stream.getvalue(),'application/pdf')})
    assert upload.status_code==201
    response=client.post(f"/api/v1/documents/{upload.json()['document_id']}/process?extractor=deterministic")
    assert response.status_code==200
    result=response.json();fields=result['extracted_fields']
    assert result['matched_instrument_id']!=phantom.id
    if scenario in ('single','repeated'):
        assert result['processing_status']=='ACCEPTED'
        assert result['matched_instrument_id']==instrument.id
        assert fields['serial_number']==instrument.serial_number
        assert 'serial_candidates' not in fields
    else:
        assert result['processing_status']=='REVIEW_REQUIRED'
        assert result['matched_instrument_id'] is None
        if scenario=='ambiguous':
            assert fields['serial_number']==''
            assert set(json.loads(fields['serial_candidates']))=={instrument.serial_number,'LABEL-OTHER'}
        else:assert 'serial_number' not in fields
