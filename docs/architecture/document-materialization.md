# Incorporación de calibraciones desde UI · TD-02 / UI-02

La revisión distingue **campos validados en staging** de **calibración incorporada al historial canónico**. Aceptar el estado de staging no crea por sí solo una calibración. La entrega se apoya en la apertura de originales de PR #29 y conserva su navegación.

## Recorrido

1. Cargar documento. Campos y acciones se refieren al documento efectivamente cargado, no al ID que se esté escribiendo en el formulario.
2. Editar y guardar correcciones. Los cambios sin guardar bloquean validar/incorporar; guardar exige revalidar. No se descartan otras ediciones locales por guardar un solo campo.
3. «Validar campos guardados» llama a `/revalidate`, recarga el estado real y avisa que todavía no se ha incorporado la calibración. No hace POST `/accept` automáticamente.
4. «Incorporar calibración al historial» solo se habilita para certificado PDF validado, vinculado y sin incorporación registrada. Llama explícitamente a `/accept` y muestra confirmación únicamente tras `CANONICAL_COMMITTED`.
5. La recarga consulta evidencia persistida de incorporación. La UI es de solo lectura para el documento ya incorporado y enlaza al pasaporte del instrumento canónico de esa incorporación, incluso si la URL de entrada tenía otro contexto. No ofrece una edición que simule actualizar una calibración ya guardada.

## Contrato aditivo

`GET /documents/{id}/fields` conserva sus campos anteriores y añade `source_type`, `matched_instrument_id` y `materialization`:

- `status`: NOT_MATERIALIZED o MATERIALIZED. ACCEPTED por sí solo no se interpreta como MATERIALIZED.
- `can_materialize`: habilitación según tipo, validación, vínculo y ausencia de evento previo; mensaje legible de lo que falta.
- Incorporación respaldada por `CALIBRATION_INGESTED` con `details.document_id`: ID de auditoría, instrumento y UUID público. Nuevos eventos incluyen también `calibration_event_id`; para eventos antiguos sin ese dato se devuelve null, sin inferirlo por fechas o proximidad.

`POST /accept` reutiliza la guarda existente `R-DUP-ACCEPT` y devuelve 409 ante repetición secuencial. Rechaza tipos distintos de PDF_CERTIFICATE. El ID de calibración se registra en la misma transacción de incorporación. No cambia el esquema ni introduce dependencias.

La respuesta mantiene CANONICAL_COMMITTED e incluye `aas_projection.status=UPDATED/ERROR` para el intento de actualizar los tres submodelos dinámicos. UPDATED no certifica sincronización completa de los cuatro submodelos; `/instruments/{id}/sync` sigue siendo la reconstrucción completa. Si falla una proyección, la calibración ya confirmada se conserva, el instrumento queda ERROR y se registra AAS_SYNC_FAILED. La UI distingue explícitamente ambos resultados; no vuelve a incorporar para reintentar AAS.

Si otra pestaña ya incorporó el documento, el 409 provoca una consulta del estado real; no se fabrica éxito a partir del texto del error. Si la respuesta se pierde por red, el usuario puede recargar/reintentar para consultar la evidencia existente; no se declara confirmación automática sin respuesta ni evidencia.

## Evidencia del 02/11/2026

[Resumen técnico](../verification/document-materialization-2026-11-02.json): 292 backend/BI pasan en Docker/Python 3.11/PostgreSQL 17, diez pruebas nuevas (sobre base PR #29 con 282). Build Node 20/Vite correcto, dependencias cacheadas. Tests comprueban staging sin materialización, elegibilidad, revalidación separada, IDs de auditoría/canónico, eventos antiguos, duplicado, corrección que exige revalidar y fallo AAS sin perder calibración.

Nueve controles Chromium contra servicios desechables reales: borradores bloqueados, guardar/validar sin crear calibración, incorporación explícita una vez, recarga/solo lectura, enlace al instrumento correcto, historial visible, pestaña desactualizada con 409, móvil 390 px y caída real de BaSyx con calibración retenida/estado ERROR. Sin errores JavaScript en recorridos comprobados. No se han recogido participantes ni ejecutado EXP-07 final.

Durante preparación hubo una copia temporal de frontend antigua y tests que contaban calibraciones de otros fixtures coexistentes: se actualizó la copia y se acotaron conteos al instrumento de cada test. Se conservaron fixtures anteriores y se repitió navegador con otros identificadores; no se borran resultados adversos del producto.

## Límites y trabajo separado

- La protección secuencial existente no demuestra atomicidad concurrente; REV-02 sigue pendiente. No se añade bloqueo/índice único ni se afirma idempotencia completa.
- Estado de incorporación usa el evento de auditoría existente; no adivina procedencia de calibraciones históricas sin esa evidencia ni recalifica masivamente documentos antiguos.
- Solo lectura es una protección UX. Los endpoints anteriores de edición/reprocesado mantienen su contrato; una política general de corrección de calibraciones ya materializadas requiere otro cambio. No se actualizan eventos canónicos a partir de edición de staging.
- TD-03 (semántica de estados por campo STAGING) no queda cerrado; se aclara la fase documental, sin pintar todos los campos como validados. TD-04 (`Serial Number:`) tampoco cambia.
- No se implementan reintentos AAS ni la actualización de snapshots desde UI; un fallo de proyección se informa y puede recuperarse mediante sincronización completa. Los avisos Requests/Starlette persisten.
