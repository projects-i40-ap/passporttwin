# Sesión: 2026-11-02 · Pau/Codex · Corrección de identidades ambiguas

## Inicio

- Pau autoriza corregir el límite encontrado en EXP-02: varios seriales no deben producir vínculo automático.
- Base remota comprobada `0d9d1b9`; rama `fix/ambiguous-document-matching`. PR #19–23 pendientes, sin asumir aprobación.
- Cambios previstos: extractor/guardas de identidad, validación, revisión documental y selector frontend. No datos del equipo ni fórmulas.

## Cierre — SESSION END STATUS

- Evidencia de candidatas de solo lectura, serie inicialmente vacía, bloqueo de matching y guardas LLM; selección humana, auditoría y revalidación antes de vincular. Corrección/reproceso no conservan un vínculo anterior inválido.
- API rechaza edición de evidencia y guardar corrección requiere revalidar; UI ofrece candidatas, no JSON editable, y funciona a 390 px.
- Verificación rama: 177 tests backend+BI y build frontend correctos. Tests HTTP de procesamiento/revisión y guardas de identidad.
- Integración local de PR #19–23 más corrección: detectado pequeño conflicto de importaciones con #20; ajustada ubicación en esta rama y repetido merge limpio. 253 tests correctos; backend sin diferencias entre el commit de regresión y composición final.
- 28 casos conocidos de EXP-02, sin cambiar etiquetas/PDFs: 26→28 decisiones correctas, 2→0 falsos vínculos, 2→0 revisiones omitidas. Informe conserva antes/después y hashes. Regresión de desarrollo, no validación final.
- Chromium contra API/PostgreSQL reales, escritorio/móvil: opción vacía al cargar, evidencia protegida, PT-B guardada y aceptada tras revalidación; sin JS errors ni scroll horizontal móvil.
- Rama de prueba `test/ambiguity-pending-prs` conserva la composición para reproducir evidencia; no main ni integración aprobada. Se publica como evidencia de pruebas, sin PR de merge automático.
- Contenedores API/UI/PostgreSQL y red desechables retirados al cerrar. Servicios existentes conservados. No se cambió Notion ni se enviaron mensajes externos.
- Preparado para commit/push/PR de corrección; revisión de Alexander antes de integrar.
- Pendientes: revisión/integración, otro conjunto independiente final y ampliación del alcance/anotaciones de EXP-03 para R-ID-AMBIGUOUS. Documentos históricos dudosos no migrados en bloque; campos STAGING mantienen el comportamiento previo.
