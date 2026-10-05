import os
import json
import random
from datetime import date, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUTPUT_DIR = "test_certificates_batch"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Semilla determinista fija según DoD técnico (Sección 21.1)
random.seed(42)

# Catálogo de instrumentos válidos existentes en PostgreSQL
VALID_INSTRUMENTS = [
    {"serial": "PT-WIKA-001", "mfr": "WIKA", "model": "S-20", "tol": 0.10},
    {"serial": "PT-WIKA-101", "mfr": "WIKA", "model": "S-20", "tol": 0.10},
    {"serial": "PT-WIKA-102", "mfr": "WIKA", "model": "S-20", "tol": 0.10},
    {"serial": "TT-EH-201", "mfr": "Endress+Hauser", "model": "iTHERM-TM411", "tol": 0.50},
    {"serial": "TT-EH-202", "mfr": "Endress+Hauser", "model": "iTHERM-TM411", "tol": 0.50},
    {"serial": "PH-MT-301", "mfr": "Mettler Toledo", "model": "InPro-3250i", "tol": 0.20},
    {"serial": "PH-MT-302", "mfr": "Mettler Toledo", "model": "InPro-3250i", "tol": 0.20},
]

def draw_pdf(filepath, title, fields):
    """Renderiza un PDF con texto digital vectorial estandarizado."""
    c = canvas.Canvas(filepath, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, 750, title)
    c.setLineWidth(1)
    c.line(100, 740, 500, 740)
    
    c.setFont("Helvetica", 11)
    y = 700
    for label, val in fields.items():
        c.drawString(100, y, f"{label}: {val}")
        y -= 25
    c.save()

def generate_dataset(num_certificates=20):
    manifest = []
    today = date.today()

    for idx in range(1, num_certificates + 1):
        filename = f"cert_{idx:03d}.pdf"
        filepath = os.path.join(OUTPUT_DIR, filename)

        # Seleccionar activo base
        inst = random.choice(VALID_INSTRUMENTS)
        serial = inst["serial"]
        mfr = inst["mfr"]
        model = inst["model"]
        tol = inst["tol"]

        # Determinar si se inyecta error (tasa ~20%)
        error_mode = random.choices(
            ["NONE", "SERIAL_MISMATCH", "FUTURE_DATE", "INVALID_DUE_DATE", "OUT_OF_TOLERANCE"],
            weights=[0.60, 0.10, 0.10, 0.10, 0.10],
            k=1
        )[0]

        cal_date = today - timedelta(days=random.randint(30, 200))
        due_date = cal_date + timedelta(days=365)
        error_val = round(random.uniform(0.01, tol * 0.8), 3)

        expected_rules_failed = []
        expected_status = "ACCEPTED"

        if error_mode == "SERIAL_MISMATCH":
            serial = f"UNKNOWN-ERR-{random.randint(100, 999)}"
            expected_rules_failed.append("R-ID-01")
            expected_status = "REVIEW_REQUIRED"

        elif error_mode == "FUTURE_DATE":
            cal_date = today + timedelta(days=45)
            due_date = cal_date + timedelta(days=365)
            expected_rules_failed.append("R-DATE-01")
            expected_status = "REVIEW_REQUIRED"

        elif error_mode == "INVALID_DUE_DATE":
            due_date = cal_date - timedelta(days=30)
            expected_rules_failed.append("R-DATE-02")
            expected_status = "REVIEW_REQUIRED"

        elif error_mode == "OUT_OF_TOLERANCE":
            error_val = round(tol * 1.5, 3)
            # R-TOL-01 no bloquea la extracción, pero condiciona /accept
            expected_status = "ACCEPTED"

        pdf_fields = {
            "Fabricante": mfr,
            "Modelo": model,
            "Número de Serie": serial,
            "Fecha de Calibración": cal_date.isoformat(),
            "Próxima Calibración": due_date.isoformat(),
            "Error Máximo": error_val,
            "Tolerancia": tol
        }

        draw_pdf(filepath, "CERTIFICADO METROLOGICO DE CALIBRACION", pdf_fields)

        manifest.append({
            "certificate_id": idx,
            "filename": filename,
            "error_injection": error_mode,
            "ground_truth": {
                "serial_number": serial,
                "calibration_date": cal_date.isoformat(),
                "next_due_date": due_date.isoformat(),
                "error_value": error_val,
                "tolerance": tol
            },
            "expected_status": expected_status,
            "expected_rules_failed": expected_rules_failed
        })

    manifest_path = os.path.join(OUTPUT_DIR, "ground_truth.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"Lote generado: {num_certificates} PDFs y manifiesto en '{OUTPUT_DIR}/ground_truth.json'.")

if __name__ == "__main__":
    generate_dataset(num_certificates=20)