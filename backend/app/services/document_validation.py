import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.instrument import InstrumentType, InstrumentUnit

# R-UNIT-01: familias de unidades dimensionalmente compatibles.
UNIT_COMPATIBILITY_MAP: dict[str, set[str]] = {
    "pressure": {"bar", "kpa", "mbar", "mpa", "psi"},
    "temperature": {"°c", "c", "k", "f"},
    "ph": {"ph"},
}

# R-MISSING-01: campos obligatorios para materializar una calibración.
REQUIRED_FIELDS: tuple[str, ...] = ("serial_number", "calibration_date")

# R-RANGE-01: "0-10 bar", "1,5 - 2,5 kPa", "10 to 20 MPa".
_RANGE_PATTERN = re.compile(
    r"(-?\d+(?:[.,]\d+)?)\s*(?:-|–|—|\ba\b|\bto\b)\s*(-?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)


def _normalize_unit(unit: str | None) -> str | None:
    """Normaliza una unidad para compararla de forma tolerante."""
    if unit is None:
        return None

    return str(unit).strip().lower().replace("º", "°").replace(" ", "")


def _unit_family(unit: str | None) -> str | None:
    """Devuelve la familia dimensional de una unidad, si se reconoce."""
    normalized = _normalize_unit(unit)

    if not normalized:
        return None

    for family, units in UNIT_COMPATIBILITY_MAP.items():
        if normalized in units:
            return family

    return None


def validate_unit_compatibility(doc_unit: str, canonical_unit: str) -> bool:
    """
    R-UNIT-01: comprueba que la unidad del documento pertenece a la misma
    familia dimensional que la unidad canónica del `InstrumentType`.

    Unidades desconocidas se aceptan solo si coinciden exactamente tras
    normalizar, evitando falsos positivos ante unidades no mapeadas.
    """
    normalized_doc = _normalize_unit(doc_unit)
    normalized_canonical = _normalize_unit(canonical_unit)

    if not normalized_doc or not normalized_canonical:
        return False

    doc_family = _unit_family(normalized_doc)
    canonical_family = _unit_family(normalized_canonical)

    if doc_family is None or canonical_family is None:
        return normalized_doc == normalized_canonical

    return doc_family == canonical_family


def validate_operating_range(range_str: str) -> bool:
    """
    R-RANGE-01: valida que un rango operativo textual tenga un límite inferior
    estrictamente menor que el superior. Un valor vacío o ausente se considera
    válido (regla no aplicable).
    """
    if range_str is None:
        return True

    text = str(range_str).strip()

    if not text:
        return True

    match = _RANGE_PATTERN.search(text)

    if not match:
        return False

    lower = float(match.group(1).replace(",", "."))
    upper = float(match.group(2).replace(",", "."))

    return lower < upper


def _resolve_canonical_unit(db: Session, target_unit: InstrumentUnit) -> str | None:
    """
    Obtiene la unidad canónica del tipo de instrumento, bien desde la relación
    ya cargada, bien consultando `InstrumentType` en base de datos.
    """
    instrument_type = getattr(target_unit, "instrument_type", None)

    if instrument_type is not None:
        canonical_unit = getattr(instrument_type, "unit", None)

        if canonical_unit:
            return canonical_unit

    instrument_type_id = getattr(target_unit, "instrument_type_id", None)

    if instrument_type_id is None:
        return None

    instrument_type = (
        db.query(InstrumentType)
        .filter(InstrumentType.id == instrument_type_id)
        .first()
    )

    if instrument_type is None:
        return None

    return getattr(instrument_type, "unit", None)


def validate_document_fields(
    db: Session,
    fields: dict,
) -> tuple[InstrumentUnit | None, list[str]]:
    """
    Ejecuta el matching determinista y las reglas de validación documental.

    Este servicio se reutiliza tanto durante el procesamiento inicial del
    documento como durante la revalidación posterior a una corrección humana.

    No modifica datos en base de datos. Devuelve:
    - el InstrumentUnit encontrado, si existe;
    - la lista de reglas incumplidas.
    """

    fields = fields or {}
    rules_failed = []

    # R-MISSING-01: campos obligatorios presentes.
    missing_fields = [
        name for name in REQUIRED_FIELDS if not fields.get(name)
    ]

    if missing_fields:
        rules_failed.append(
            "R-MISSING-01: Faltan campos obligatorios en el documento."
        )

    # R-ID-01: matching determinista por número de serie
    matched_serial = fields.get("serial_number")
    target_unit = None

    if matched_serial:
        target_unit = (
            db.query(InstrumentUnit)
            .filter(InstrumentUnit.serial_number == matched_serial)
            .first()
        )

    if not target_unit:
        rules_failed.append(
            "R-ID-01: Serial no coincide con ningún activo canónico registrado."
        )

    # R-UNIT-01: compatibilidad de unidades frente al InstrumentType.
    doc_unit = fields.get("unit")

    if doc_unit and target_unit:
        canonical_unit = _resolve_canonical_unit(db, target_unit)

        if canonical_unit and not validate_unit_compatibility(
            doc_unit, canonical_unit
        ):
            rules_failed.append(
                "R-UNIT-01: Unidad incompatible con la magnitud canónica del activo."
            )

    # R-RANGE-01: coherencia numérica del rango operativo.
    operating_range = fields.get("operating_range")

    if operating_range is not None and str(operating_range).strip():
        if not validate_operating_range(operating_range):
            rules_failed.append(
                "R-RANGE-01: Rango operativo incoherente o inválido."
            )

    # R-DATE-01 y R-DATE-02: coherencia temporal
    cal_date_str = fields.get("calibration_date")
    due_date_str = fields.get("next_due_date")

    if cal_date_str:
        cal_date = datetime.strptime(cal_date_str, "%Y-%m-%d").date()

        if cal_date > datetime.utcnow().date():
            rules_failed.append(
                "R-DATE-01: La fecha de calibración es futura."
            )

        if due_date_str:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()

            if due_date <= cal_date:
                rules_failed.append(
                    "R-DATE-02: La fecha de vencimiento es anterior o igual a la de calibración."
                )

    return target_unit, rules_failed
