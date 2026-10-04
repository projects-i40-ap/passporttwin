import os
import json
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def create_pdf(filename: str, title: str, serial: str, cal_date: str, due_date: str, max_error: float, tol: float):
    c = canvas.Canvas(filename, pagesize=letter)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, 750, title)
    c.setFont("Helvetica", 10)
    c.drawString(72, 710, f"Número de Serie: {serial}")
    c.drawString(72, 690, f"Fecha de Calibración: {cal_date}")
    c.drawString(72, 670, f"Próxima Calibración: {due_date}")
    c.drawString(72, 650, f"Error Máximo: {max_error}")
    c.drawString(72, 630, f"Tolerancia: {tol}")
    c.save()

def generate_ground_truth_dataset(output_dir: str = "data/fixtures/synthetic_certificates"):
    os.makedirs(output_dir, exist_ok=True)
    manifest = []

    # Caso 1: Certificado Válido (Nominal)
    f1 = os.path.join(output_dir, "CAL_NOMINAL_001.pdf")
    create_pdf(f1, "CERTIFICADO METROLÓGICO NOMINAL", "PT-WIKA-001", "2026-05-10", "2027-05-10", 0.02, 0.10)
    manifest.append({"file": "CAL_NOMINAL_001.pdf", "expected_status": "ACCEPTED", "target_rule_fail": None})

    # Caso 2: Violación R-DATE-01 (Fecha de calibración futura)
    f2 = os.path.join(output_dir, "CAL_ERR_FUTURE_002.pdf")
    create_pdf(f2, "CERTIFICADO CON ANOMALÍA TEMPORAL", "PT-WIKA-001", "2028-01-01", "2029-01-01", 0.02, 0.10)
    manifest.append({"file": "CAL_ERR_FUTURE_002.pdf", "expected_status": "REVIEW_REQUIRED", "target_rule_fail": "R-DATE-01"})

    # Caso 3: Violación R-DATE-02 (Due date anterior a Cal date)
    f3 = os.path.join(output_dir, "CAL_ERR_DUEDATE_003.pdf")
    create_pdf(f3, "CERTIFICADO CON INCOHERENCIA DE VENCIMIENTO", "PT-WIKA-001", "2026-05-10", "2025-05-10", 0.02, 0.10)
    manifest.append({"file": "CAL_ERR_DUEDATE_003.pdf", "expected_status": "REVIEW_REQUIRED", "target_rule_fail": "R-DATE-02"})

    # Caso 4: Violación R-ID-01 (Serial inexistente)
    f4 = os.path.join(output_dir, "CAL_ERR_SERIAL_004.pdf")
    create_pdf(f4, "CERTIFICADO ACTIVO DESCONOCIDO", "UNKNOWN-SERIAL-999", "2026-05-10", "2027-05-10", 0.03, 0.10)
    manifest.append({"file": "CAL_ERR_SERIAL_004.pdf", "expected_status": "REVIEW_REQUIRED", "target_rule_fail": "R-ID-01"})

    # Caso 5: Fuera de Tolerancia R-TOL-01 (|error| > tol)
    f5 = os.path.join(output_dir, "CAL_OUT_OF_TOL_005.pdf")
    create_pdf(f5, "CERTIFICADO FUERA DE TOLERANCIA", "PT-WIKA-001", "2026-06-01", "2027-06-01", 0.14, 0.10)
    manifest.append({"file": "CAL_OUT_OF_TOL_005.pdf", "expected_status": "ACCEPTED", "target_rule_fail": "R-TOL-01_FLAG"})

    with open(os.path.join(output_dir, "manifest_ground_truth.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

if __name__ == "__main__":
    generate_ground_truth_dataset()