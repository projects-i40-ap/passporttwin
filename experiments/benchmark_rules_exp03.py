import os
import json
import requests
from typing import Dict, Any, List

# Configuración de URLs y rutas relativas desde la raíz del proyecto
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BATCH_DIR = os.path.join(PROJECT_ROOT, "generators", "test_certificates_batch")
MANIFEST_PATH = os.path.join(BATCH_DIR, "ground_truth.json")
OUTPUT_METRICS_PATH = os.path.join(PROJECT_ROOT, "experiments", "results_exp03.json")

def load_ground_truth(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"No se encontró el manifiesto en: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_rule_ids(rules: List[str]) -> List[str]:
    """
    Normaliza las reglas devueltas por el backend.

    Ejemplo:
    "R-DATE-01: La fecha de calibración es futura."
    -> "R-DATE-01"
    """
    return sorted({
        str(rule).split(":", 1)[0].strip()
        for rule in (rules or [])
        if str(rule).strip()
    })

def run_experiment_03():
    print("==================================================================")
    print("EJECUTANDO BENCHMARK EXP-03: MOTOR DE REGLAS Y CALIDAD DE DATOS")
    print("==================================================================")
    print(f"Ruta de artefactos: {BATCH_DIR}")
    print(f"Endpoint API      : {API_BASE_URL}\n")

    dataset = load_ground_truth(MANIFEST_PATH)
    total_samples = len(dataset)
    print(f"Total de certificados a evaluar: {total_samples}")

    tp = fp = tn = fn = 0
    exact_rule_matches = 0
    evaluated_rule_sets = 0
    detailed_results = []

    for item in dataset:
        filename = item["filename"]
        pdf_path = os.path.join(BATCH_DIR, filename)

        # Ground truth documental:
        # OUT_OF_TOLERANCE no implica REVIEW_REQUIRED porque R-TOL-01
        # se evalúa posteriormente durante /accept.
        is_anomalous_ground_truth = (
            item["expected_status"] == "REVIEW_REQUIRED"
        )
        expected_status = item["expected_status"]

        if not os.path.exists(pdf_path):
            print(f"Advertencia: Archivo {pdf_path} no existe. Omitiendo.")
            continue

        # 1. Ingesta RAW (POST /documents/upload)
        with open(pdf_path, "rb") as pdf_file:
            resp_upload = requests.post(
                f"{API_BASE_URL}/documents/upload",
                files={"file": (filename, pdf_file, "application/pdf")},
                timeout=10
            )

        # Control de deduplicación R-DUP-01: Si ya fue subido, extraer ID del error 409
        if resp_upload.status_code == 409:
            detail_msg = resp_upload.json().get("detail", "")
            doc_id = int(detail_msg.split("ID existente: ")[1])
        elif resp_upload.status_code == 201:
            doc_id = resp_upload.json()["document_id"]
        else:
            print(f"Error HTTP {resp_upload.status_code} al subir {filename}: {resp_upload.text}")
            continue

        # 2. Procesamiento Canónico (POST /documents/{id}/process)
        resp_process = requests.post(
            f"{API_BASE_URL}/documents/{doc_id}/process",
            timeout=10
        )
        if resp_process.status_code != 200:
            print(f"Error HTTP {resp_process.status_code} al procesar documento ID {doc_id}: {resp_process.text}")
            continue

        process_data = resp_process.json()
        actual_status = process_data["processing_status"]
        actual_failed_rules = process_data.get("rules_failed", [])

        expected_rule_ids = sorted(
            set(item.get("expected_rules_failed", []))
        )
        actual_rule_ids = extract_rule_ids(actual_failed_rules)

        # Detección documental:
        # Si el estado es REVIEW_REQUIRED, el motor clasificó anomalía documental.
        predicted_as_anomaly = (actual_status == "REVIEW_REQUIRED")

        if is_anomalous_ground_truth and predicted_as_anomaly:
            tp += 1
            classification = "TP (Anomalía documental detectada correctamente)"
        elif not is_anomalous_ground_truth and not predicted_as_anomaly:
            tn += 1
            classification = "TN (Documento documentalmente conforme)"
        elif not is_anomalous_ground_truth and predicted_as_anomaly:
            fp += 1
            classification = "FP (Documento conforme clasificado como error)"
        else:
            fn += 1
            classification = "FN (Anomalía documental no detectada)"

        # Coincidencia exacta entre reglas esperadas y reglas disparadas.
        rules_exact_match = (expected_rule_ids == actual_rule_ids)
        evaluated_rule_sets += 1

        if rules_exact_match:
            exact_rule_matches += 1

        detailed_results.append({
            "certificate_id": item["certificate_id"],
            "filename": filename,
            "error_injection": item["error_injection"],
            "ground_truth_status": expected_status,
            "actual_status": actual_status,
            "classification": classification,
            "expected_rules": expected_rule_ids,
            "triggered_rules": actual_rule_ids,
            "rules_exact_match": rules_exact_match
        })

    # 3. Cómputo de Métricas Metrológicas Formales
    evaluated = tp + tn + fp + fn
    accuracy = (tp + tn) / evaluated if evaluated > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    rule_exact_match_accuracy = (
        exact_rule_matches / evaluated_rule_sets
        if evaluated_rule_sets > 0
        else 0.0
    )

    print("\n------------------------------------------------------------------")
    print("MATRIZ DE CONFUSIÓN Y MÉTRICAS OBTENIDAS:")
    print("------------------------------------------------------------------")
    print(f"Total Evaluados      : {evaluated} / {total_samples}")
    print(f"Verdaderos Positivos : {tp}")
    print(f"Verdaderos Negativos : {tn}")
    print(f"Falsos Positivos     : {fp}")
    print(f"Falsos Negativos     : {fn}")
    print("------------------------------------------------------------------")
    print(f"Exactitud (Accuracy) : {accuracy * 100:.2f} %")
    print(f"Precisión (Precision): {precision * 100:.2f} %")
    print(f"Sensibilidad (Recall): {recall * 100:.2f} %")
    print(f"Puntaje F1 (F1-Score): {f1_score * 100:.2f} %")
    print(f"Coincidencia reglas  : {rule_exact_match_accuracy * 100:.2f} %")
    print("==================================================================")

    # 4. Guardar archivo de evidencia estructurado
    os.makedirs(os.path.dirname(OUTPUT_METRICS_PATH), exist_ok=True)
    report_payload = {
        "experiment": "EXP-03",
        "description": "Evaluación cuantitativa del motor de reglas documentales frente a ground truth",
        "validation_scope": (
            "Validación experimental sobre certificados sintéticos controlados. "
            "R-TOL-01 queda fuera de la clasificación documental porque se evalúa "
            "posteriormente durante /accept."
        ),
        "dataset_evaluated": "generators/test_certificates_batch/ground_truth.json",
        "ground_truth_definition": (
            "Un documento se considera anomalía documental cuando "
            "expected_status == REVIEW_REQUIRED."
        ),
        "confusion_matrix": {
            "true_positives": tp,
            "true_negatives": tn,
            "false_positives": fp,
            "false_negatives": fn
        },
        "metrics": {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1_score, 4),
            "rule_exact_match_accuracy": round(rule_exact_match_accuracy, 4)
        },
        "details": detailed_results
    }

    with open(OUTPUT_METRICS_PATH, "w", encoding="utf-8") as f_out:
        json.dump(report_payload, f_out, indent=2, ensure_ascii=False)

    print(f"\n[OK] Reporte experimental exportado en: {OUTPUT_METRICS_PATH}")

if __name__ == "__main__":
    run_experiment_03()