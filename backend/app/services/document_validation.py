from datetime import datetime

from sqlalchemy.orm import Session

from app.models.instrument import InstrumentUnit


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

    rules_failed = []

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