"""Genera certificados de calibración de ejemplo para los instrumentos cargados.

Los PDFs se crean a partir de los activos canónicos de PostgreSQL y usan las
mismas etiquetas que reconoce el extractor determinista (`Número de Serie`,
`Fecha de Calibración`, `Próxima Calibración`, `Error Máximo`, `Tolerancia`,
`Unidad`, `Rango Operativo`). Así se pueden subir a PassportTwin y ver cómo
quedan en la revisión documental, el historial y el pasaporte.

Uso típico (contenedor con el repositorio y el escritorio montados):

    python /generators/generate_sample_certificates.py --output /desktop/PassportTwin-Certificados
"""

import argparse
import hashlib
import io
import json
from datetime import date, timedelta
from pathlib import Path

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.calibration import CalibrationEvent
from app.models.document import Document, ExtractedField
from app.models.instrument import InstrumentUnit

# Tolerancia por familia cuando el activo aún no tiene calibraciones registradas.
DEFAULT_TOLERANCE = {"pressure": 0.1, "temperature": 0.5, "ph": 0.1}
DEFAULT_RANGE = {
    "pressure": "0 - 600 bar",
    "temperature": "-55 - 125 °C",
    "ph": "0 - 14 pH",
}
UNIT_FAMILY = {"bar": "pressure", "kpa": "pressure", "mpa": "pressure", "psi": "pressure",
               "°c": "temperature", "c": "temperature", "k": "temperature", "ph": "ph"}


def _seed(serial_number: str) -> int:
    return int(hashlib.sha256(serial_number.encode("utf-8")).hexdigest()[:8], 16)


def _integer(serial_number: str, modulo: int, offset: int = 0) -> int:
    return _seed(serial_number) % modulo + offset


def _family(instrument) -> str:
    unit = (getattr(instrument.instrument_type, "unit", None) or "bar").lower()
    return UNIT_FAMILY.get(unit, "pressure")


def _linked_range(db, instrument) -> str:
    """Rango declarado en la ficha técnica vinculada, si existe."""
    document_ids = [
        document.id
        for document in db.query(Document).filter(Document.instrument_unit_id == instrument.id).all()
    ]
    if not document_ids:
        return ""

    field = (
        db.query(ExtractedField)
        .filter(
            ExtractedField.document_id.in_(document_ids),
            ExtractedField.field_name == "operating_range",
        )
        .order_by(ExtractedField.document_id.desc())
        .first()
    )

    return getattr(field, "normalized_value", None) or getattr(field, "raw_value", None) or ""


def _certificate_data(db, instrument, *, out_of_tolerance=False) -> dict:
    latest = (
        db.query(CalibrationEvent)
        .filter(CalibrationEvent.instrument_unit_id == instrument.id)
        .order_by(CalibrationEvent.calibration_date.desc(), CalibrationEvent.id.desc())
        .first()
    )

    family = _family(instrument)
    tolerance = float(getattr(latest, "tolerance", None) or DEFAULT_TOLERANCE.get(family, 1.0))
    today = date.today()

    if latest and latest.calibration_date:
        calibration_date = latest.calibration_date
        next_due_date = latest.next_due_date or calibration_date + timedelta(days=365)
        error_value = float(latest.error_value)
    else:
        calibration_date = today - timedelta(days=_integer(instrument.serial_number, 180, 30))
        next_due_date = calibration_date + timedelta(days=365)
        error_value = round(tolerance * (0.2 + (_integer(instrument.serial_number, 30) / 100)), 3)

    if out_of_tolerance:
        error_value = round(tolerance * 1.6, 3)

    unit = getattr(instrument.instrument_type, "unit", None) or "bar"
    operating_range = _linked_range(db, instrument) or DEFAULT_RANGE.get(family, "0 - 100")

    return {
        "manufacturer": instrument.manufacturer or "Sin fabricante",
        "model": instrument.technical_name or instrument.model or "Sin modelo",
        "serial_number": instrument.serial_number,
        "location": instrument.location or "Laboratorio",
        "calibration_date": calibration_date,
        "next_due_date": next_due_date,
        "error_value": error_value,
        "tolerance": tolerance,
        "unit": unit,
        "operating_range": operating_range,
        "result": "NO CONFORME" if abs(error_value) > tolerance else "CONFORME",
        "certificate_number": f"CERT-{calibration_date.year}-{instrument.serial_number}",
        "passport_url": f"{str(settings.passport_frontend_base_url).rstrip('/')}/passport/{instrument.public_id}",
    }


def _qr_reader(url: str):
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    buffer = io.BytesIO()
    qr.make_image(fill_color="#122945", back_color="white").save(buffer, format="PNG")
    buffer.seek(0)
    return ImageReader(buffer)


def _draw_row(pdf, x, y, width, label, value):
    pdf.setFillColorRGB(0.32, 0.36, 0.42)
    pdf.setFont("Helvetica-Bold", 8.2)
    pdf.drawString(x, y, label.upper())
    pdf.setFillColorRGB(0.09, 0.2, 0.3)
    pdf.setFont("Helvetica", 11)
    pdf.drawString(x + 52 * mm, y, str(value))
    pdf.setStrokeColorRGB(0.86, 0.9, 0.94)
    pdf.setLineWidth(0.5)
    pdf.line(x, y - 3 * mm, x + width, y - 3 * mm)
    return y - 8.4 * mm


def _draw_section(pdf, x, y, width, title, rows):
    pdf.setFillColorRGB(0.09, 0.2, 0.3)
    pdf.setFont("Helvetica-Bold", 11.5)
    pdf.drawString(x, y, title)
    y -= 6 * mm
    for label, value in rows:
        y = _draw_row(pdf, x, y, width, label, value)
    return y - 3 * mm


def render_certificate(path: Path, data: dict) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    # Banda superior de marca.
    pdf.setFillColorRGB(0.071, 0.161, 0.271)
    pdf.rect(0, height - 34 * mm, width, 34 * mm, stroke=0, fill=1)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(20 * mm, height - 18 * mm, "PassportTwin")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(20 * mm, height - 25 * mm, "Gemelo de fiabilidad y pasaporte digital de instrumentación")
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(width - 20 * mm, height - 18 * mm, "Laboratorio de Metrología Demo")
    pdf.drawRightString(width - 20 * mm, height - 23 * mm, "Polígono Industrial 12 · Barcelona")
    pdf.drawRightString(width - 20 * mm, height - 28 * mm, "ISO/IEC 17025 (simulado)")

    y = height - 50 * mm
    pdf.setFillColorRGB(0.09, 0.2, 0.3)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(20 * mm, y, "CERTIFICADO DE CALIBRACIÓN")
    pdf.setFont("Helvetica", 10)
    pdf.setFillColorRGB(0.32, 0.36, 0.42)
    pdf.drawString(20 * mm, y - 7 * mm, f"N.º de certificado: {data['certificate_number']}")
    pdf.drawRightString(width - 20 * mm, y - 7 * mm, f"Fecha de emisión: {data['calibration_date'].isoformat()}")
    pdf.setStrokeColorRGB(0.77, 0.83, 0.9)
    pdf.setLineWidth(0.8)
    pdf.line(20 * mm, y - 11 * mm, width - 20 * mm, y - 11 * mm)

    y -= 20 * mm
    y = _draw_section(pdf, 20 * mm, y, width - 40 * mm, "1. Instrumento calibrado", [
        ("Fabricante", data["manufacturer"]),
        ("Modelo", data["model"]),
        ("Número de Serie", data["serial_number"]),
        ("Ubicación", data["location"]),
    ])

    y = _draw_section(pdf, 20 * mm, y, width - 40 * mm, "2. Resultado de la calibración", [
        ("Fecha de Calibración", data["calibration_date"].isoformat()),
        ("Próxima Calibración", data["next_due_date"].isoformat()),
        ("Error Máximo", f"{data['error_value']:.3f}"),
        ("Tolerancia", f"{data['tolerance']:.3f}"),
        ("Unidad", data["unit"]),
        ("Rango Operativo", data["operating_range"]),
    ])

    # Caja de resultado (debajo de la última fila, sin tapar datos).
    conforming = data["result"] == "CONFORME"
    box_height = 18 * mm
    box_y = y - box_height - 2 * mm
    if conforming:
        pdf.setFillColorRGB(0.88, 0.96, 0.9)
    else:
        pdf.setFillColorRGB(0.99, 0.9, 0.9)
    pdf.roundRect(20 * mm, box_y, width - 40 * mm, box_height, 3 * mm, stroke=0, fill=1)
    if conforming:
        pdf.setFillColorRGB(0.06, 0.27, 0.14)
    else:
        pdf.setFillColorRGB(0.55, 0.1, 0.12)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(26 * mm, box_y + 11 * mm, f"Resultado: {data['result']}")
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(26 * mm, box_y + 6 * mm,
                   "El error máximo declarado se compara con la tolerancia del instrumento (regla R-TOL-01).")

    # Observaciones: metodología y condiciones del acto de calibración.
    obs_y = box_y - 12 * mm
    pdf.setFillColorRGB(0.09, 0.2, 0.3)
    pdf.setFont("Helvetica-Bold", 11.5)
    pdf.drawString(20 * mm, obs_y, "3. Observaciones")
    pdf.setFont("Helvetica", 9)
    pdf.setFillColorRGB(0.32, 0.36, 0.42)
    observations = (
        "Método: comparación directa contra patrón de referencia trazable.",
        "Condiciones ambientales: 22 °C ± 2 °C y 45 % HR ± 10 %.",
        "Incertidumbre expandida (k = 2): 0.02 % del fondo de escala.",
    )
    for offset, line in enumerate(observations, start=1):
        pdf.drawString(20 * mm, obs_y - offset * 5.5 * mm, line)

    # Pie: firma, QR y aviso.
    footer_y = 42 * mm
    pdf.setStrokeColorRGB(0.6, 0.65, 0.7)
    pdf.setLineWidth(0.6)
    pdf.line(20 * mm, footer_y + 12 * mm, 78 * mm, footer_y + 12 * mm)
    pdf.line(88 * mm, footer_y + 12 * mm, 146 * mm, footer_y + 12 * mm)
    pdf.setFillColorRGB(0.32, 0.36, 0.42)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(20 * mm, footer_y + 8 * mm, "Técnico de calibración")
    pdf.drawString(88 * mm, footer_y + 8 * mm, "Responsable de calidad")

    pdf.drawImage(_qr_reader(data["passport_url"]), width - 52 * mm, footer_y + 2 * mm,
                  width=30 * mm, height=30 * mm, mask="auto")
    pdf.setFont("Helvetica", 6.5)
    pdf.drawRightString(width - 20 * mm, footer_y - 1 * mm, "Escanear para abrir el pasaporte digital")

    pdf.setStrokeColorRGB(0.86, 0.9, 0.94)
    pdf.line(20 * mm, 18 * mm, width - 20 * mm, 18 * mm)
    pdf.setFillColorRGB(0.42, 0.46, 0.52)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(20 * mm, 13 * mm,
                   "Documento de ejemplo generado para la demostración del TFM PassportTwin. No es un certificado real.")
    pdf.drawRightString(width - 20 * mm, 13 * mm, "Página 1 de 1")

    pdf.showPage()
    pdf.save()


def build_catalog(db) -> list[dict]:
    instruments = (
        db.query(InstrumentUnit)
        .order_by(InstrumentUnit.serial_number.asc())
        .all()
    )

    return [
        {"instrument": instrument, "data": _certificate_data(db, instrument)}
        for instrument in instruments
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera certificados de calibración de ejemplo.")
    parser.add_argument("--output", required=True, help="Carpeta de destino de los PDFs")
    parser.add_argument("--out-of-tolerance", action="store_true",
                        help="Genera también una variante NO CONFORME por instrumento")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        catalog = build_catalog(db)
    finally:
        db.close()

    manifest = []

    for entry in catalog:
        instrument = entry["instrument"]
        data = entry["data"]
        filename = f"{instrument.serial_number}-certificado.pdf"
        render_certificate(output / filename, data)
        manifest.append({
            "archivo": filename,
            "serial_number": instrument.serial_number,
            "calibration_date": data["calibration_date"].isoformat(),
            "next_due_date": data["next_due_date"].isoformat(),
            "error_value": data["error_value"],
            "tolerance": data["tolerance"],
            "unit": data["unit"],
            "operating_range": data["operating_range"],
            "passport_url": data["passport_url"],
        })

    if args.out_of_tolerance:
        variants = output / "variantes"
        variants.mkdir(exist_ok=True)
        for entry in catalog:
            instrument = entry["instrument"]
            non_conforming = dict(entry["data"])
            non_conforming["error_value"] = round(entry["data"]["tolerance"] * 1.6, 3)
            non_conforming["result"] = "NO CONFORME"
            filename = f"{instrument.serial_number}-no-conforme.pdf"
            render_certificate(variants / filename, non_conforming)
            manifest.append({"archivo": f"variantes/{filename}", "serial_number": instrument.serial_number,
                             "result": "NO CONFORME"})

    (output / "indice.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output / "LEEME.md").write_text(
        "# Certificados de ejemplo\n\n"
        "Un certificado por cada instrumento cargado en PassportTwin, generado a partir de sus datos\n"
        "canónicos (serial, fabricante, modelo, ubicación, tolerancia y rango).\n\n"
        "Cada PDF incluye las etiquetas que reconoce el extractor (`Número de Serie`,\n"
        "`Fecha de Calibración`, `Próxima Calibración`, `Error Máximo`, `Tolerancia`, `Unidad` y\n"
        "`Rango Operativo`) y un QR al pasaporte digital del activo.\n\n"
        "## Cómo usarlos\n\n"
        "1. Entra en «Revisión documental» y sube uno de los PDFs.\n"
        "2. Procesa el documento: debería vincularse por número de serie sin tocar los campos.\n"
        "3. Valida y pulsa «Incorporar calibración al historial».\n"
        "4. Abre el pasaporte del instrumento para ver la nueva calibración y su estado.\n\n"
        "Las variantes con `NO CONFORME` sirven para demostrar el estado «fuera de tolerancia».\n\n"
        "Documentos de demostración: no tienen validez metrológica real.\n",
        encoding="utf-8",
    )

    print(f"Generados {len(manifest)} certificados en {output}")


if __name__ == "__main__":
    main()
