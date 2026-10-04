import io
import hashlib
import pandas as pd
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.document import Document
from app.models.instrument import InstrumentUnit, InstrumentType

class InventoryCSVAdapter:
    REQUIRED_COLUMNS = {"serial_number", "manufacturer", "model", "type_name", "magnitude", "unit"}

    @staticmethod
    def process_inventory_csv(file_bytes: bytes, filename: str, db: Session) -> Dict[str, Any]:
        """Procesa un CSV de inventario, registra la evidencia RAW y crea activos canónicos."""
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # Validación R-DUP-01
        existing_doc = db.query(Document).filter(Document.sha256_hash == file_hash).first()
        if existing_doc:
            raise ValueError(f"R-DUP-01: Archivo CSV duplicado detectado. SHA-256: {file_hash}")

        # Registro RAW
        raw_doc = Document(
            original_filename=filename,
            file_path=f"/app/storage/raw/{file_hash}.csv",
            source_type="INVENTORY_CSV",
            sha256_hash=file_hash,
            processing_status="PROCESSING"
        )
        db.add(raw_doc)
        db.flush()

        df = pd.read_csv(io.BytesIO(file_bytes), dtype=str)
        missing = InventoryCSVAdapter.REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raw_doc.processing_status = "FAILED_EXTRACTION"
            db.commit()
            raise ValueError(f"Columnas requeridas ausentes en el CSV: {missing}")

        created_units = []
        for _, row in df.iterrows():
            serial = str(row["serial_number"]).strip()
            
            # Verificar si el serial ya existe
            if db.query(InstrumentUnit).filter(InstrumentUnit.serial_number == serial).first():
                continue

            # Resolver o crear InstrumentType dinámicamente
            type_name = str(row["type_name"]).strip().lower()
            inst_type = db.query(InstrumentType).filter(InstrumentType.name == type_name).first()
            if not inst_type:
                inst_type = InstrumentType(
                    name=type_name,
                    magnitude=str(row["magnitude"]).strip(),
                    unit=str(row["unit"]).strip()
                )
                db.add(inst_type)
                db.flush()

            unit = InstrumentUnit(
                instrument_type_id=inst_type.id,
                serial_number=serial,
                manufacturer=str(row["manufacturer"]).strip(),
                model=str(row["model"]).strip(),
                location=str(row.get("location", "Plant-A")).strip(),
                criticality=str(row.get("criticality", "MEDIUM")).strip().upper(),
                lifecycle_state="operational",
                aas_sync_status="PENDING"
            )
            db.add(unit)
            created_units.append(serial)

        raw_doc.processing_status = "ACCEPTED"
        db.commit()
        return {"document_id": raw_doc.id, "created_count": len(created_units), "serials": created_units}