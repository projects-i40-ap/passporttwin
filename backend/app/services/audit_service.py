"""Servicio centralizado de auditoría (RF-AUDIT-01).

Encapsula la creación de entradas en la tabla canónica `audit_log` para que
ningún endpoint escriba el JSONB `details` de forma dispersa. El llamador es
dueño de la frontera transaccional: `log_event` añade la entrada y la deja
lista para el `commit` de la operación maestra.
"""

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.calibration import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """Punto único de registro de eventos de trazabilidad."""

    @staticmethod
    def log_event(
        db: Session,
        entity_name: str,
        entity_id: int,
        action: str,
        actor: str = "system",
        source: Optional[str] = None,
        rule_or_model: Optional[str] = None,
        before: Optional[dict[str, Any]] = None,
        after: Optional[dict[str, Any]] = None,
        details: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AuditLog:
        """Registra un evento inmutable en `audit_log`.

        Args:
            db: Sesión SQLAlchemy (o fake de test) que participa en la transacción.
            entity_name: Nombre de la entidad afectada (`document`, `instrument_unit`).
            entity_id: Identificador canónico de la entidad.
            action: Acción auditada (`FIELD_CORRECTED`, `DOCUMENT_REVALIDATED`, ...).
            actor: Usuario o proceso responsable del cambio.
            source: Origen técnico del evento (endpoint, job, integración).
            rule_or_model: Regla de negocio o modelo de IA implicado.
            before: Estado previo de los valores mutados.
            after: Estado resultante de los valores mutados.
            details: Metadatos adicionales (por ejemplo `document_id`).
            metadata: Evidencia complementaria (hash SHA-256, versión de modelo).

        Returns:
            La entrada `AuditLog` añadida a la sesión, pendiente de `commit`.
        """
        # Copia defensiva: el diccionario del llamador nunca se muta.
        payload: dict[str, Any] = dict(details or {})
        payload["actor"] = actor

        if source is not None:
            payload["source"] = source

        if rule_or_model is not None:
            payload["rule_or_model"] = rule_or_model

        if before is not None:
            payload["before"] = before

        if after is not None:
            payload["after"] = after

        if metadata:
            payload["metadata"] = dict(metadata)

        audit_entry = AuditLog(
            entity_name=entity_name,
            entity_id=entity_id,
            action=action,
            details=payload,
        )

        try:
            db.add(audit_entry)

            # `flush` sincroniza la fila dentro de la transacción del llamador.
            # Los `FakeSession` de los tests pueden no implementarlo.
            flush = getattr(db, "flush", None)
            if callable(flush):
                flush()
        except Exception:
            # La auditoría nunca debe tumbar la operación maestra (patrón LEGO:
            # degradación controlada y trazada en el log de la aplicación).
            logger.exception(
                "No se pudo registrar el evento de auditoría '%s' para %s:%s",
                action,
                entity_name,
                entity_id,
            )

        return audit_entry
