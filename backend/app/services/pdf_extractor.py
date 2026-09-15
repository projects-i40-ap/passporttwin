import re
from datetime import datetime
import pdfplumber
import logging

logger = logging.getLogger("passporttwin.extractor")

class PDFCertificateExtractor:
    @staticmethod
    def extract_and_parse(file_path: str) -> dict:
        """Extrae texto de un PDF digital y recupera campos clave mediante expresiones regulares."""
        raw_text = ""
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        raw_text += text + "\n"
        except Exception as e:
            logger.error(f"Error leyendo PDF con pdfplumber: {str(e)}")
            return {}

        fields = {}

        # 1. Extracción de Número de Serie (ej. S/N: PT-WIKA-001 o Serial: PT-WIKA-001)
        serial_match = re.search(r"(?:S/N|Serial|Número de Serie)[:\s]+([A-Za-z0-9\-_]+)", raw_text, re.IGNORECASE)
        if serial_match:
            fields["serial_number"] = serial_match.group(1).strip()

        # 2. Extracción de Fecha de Calibración (Formatos ISO YYYY-MM-DD o DD/MM/YYYY)
        cal_date_match = re.search(r"(?:Calibration Date|Fecha de Calibración)[:\s]+(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})", raw_text, re.IGNORECASE)
        if cal_date_match:
            raw_date = cal_date_match.group(1).strip()
            fields["calibration_date"] = PDFCertificateExtractor._normalize_date(raw_date)

        # 3. Extracción de Fecha de Próximo Vencimiento
        due_date_match = re.search(r"(?:Due Date|Próxima Calibración)[:\s]+(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})", raw_text, re.IGNORECASE)
        if due_date_match:
            raw_date = due_date_match.group(1).strip()
            fields["next_due_date"] = PDFCertificateExtractor._normalize_date(raw_date)

        # 4. Extracción de Error Máximo y Tolerancia
        error_match = re.search(r"(?:Max Error|Error Máximo)[:\s]+([+\-]?\d+(?:\.\d+)?)", raw_text, re.IGNORECASE)
        if error_match:
            fields["error_value"] = float(error_match.group(1).strip())

        tol_match = re.search(r"(?:Tolerance|Tolerancia)[:\s]+([+\-]?\d+(?:\.\d+)?)", raw_text, re.IGNORECASE)
        if tol_match:
            fields["tolerance"] = float(tol_match.group(1).strip())

        return fields

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """Convierte fechas a estándar canónico ISO-8601 (YYYY-MM-DD)."""
        if "/" in date_str:
            parts = date_str.split("/")
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
        return date_str