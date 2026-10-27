from app.models.calibration import CalibrationEvent
from app.models.document import Document
from app.models.maintenance import Incident, MaintenanceEvent


def load_context(db,instrument_id,as_of):
    return {
        'calibrations':db.query(CalibrationEvent).filter(CalibrationEvent.instrument_unit_id==instrument_id,
            CalibrationEvent.calibration_date<=as_of).order_by(CalibrationEvent.calibration_date,CalibrationEvent.id).all(),
        'documents':db.query(Document).filter(Document.instrument_unit_id==instrument_id).order_by(Document.id).all(),
        'incidents':db.query(Incident).filter(Incident.instrument_unit_id==instrument_id,Incident.incident_date<=as_of).order_by(Incident.id).all(),
        'maintenance':db.query(MaintenanceEvent).filter(MaintenanceEvent.instrument_unit_id==instrument_id,MaintenanceEvent.event_date<=as_of).order_by(MaintenanceEvent.id).all(),
    }
