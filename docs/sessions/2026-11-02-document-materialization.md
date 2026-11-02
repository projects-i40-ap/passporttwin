# Sesión: 2026-11-02 · Pau/Codex · Incorporar calibraciones TD-02

## Inicio

- Pau pide «continúa» después de PR #29; siguiente tarea acordada: materialización de calibraciones desde UI con validación separada.
- Fetch: main sigue en `823a4bb`; PR #29 abierta. Rama apilada `feature/document-materialization` desde `541c2a3`, base PR `feature/document-original`; revisar/integrar #29 primero y retargetear después a main si corresponde. No alterar PR #29 ni fusionar automáticamente.
- Leídas instrucciones y cierre anterior. Alcance TD-02, no cierre de estados por campo ni ampliación de extractor; sin mensajes externos a Alexander ni edición de Notion.

## Cierre — SESSION END STATUS

- Implementado estado de incorporación respaldado por auditoría, IDs canónicos para nuevos eventos y vínculo a UUID correcto; control de certificado/vínculo/estado; acción explícita UI, borradores bloqueados, recarga/solo lectura y tratamiento de 409.
- Incorporación canónica se conserva si AAS falla: respuesta separada, estado ERROR y evento AAS_SYNC_FAILED; sin reintento automático ni nueva calibración para recuperar proyección.
- TESTED: 292 backend/BI pasan en Docker/Python 3.11/PostgreSQL 17 (10 nuevos sobre base #29), build Node 20, nueve controles Chromium con API/DB/AAS/RAW reales, incluida caída intencional del BaSyx propio. Sin errores JS en lo comprobado; móvil 390 px.
- Ajustes de preparación: copia frontend temporal antigua actualizada; tests acotados a su instrumento en vez de contar toda una base con fixtures de navegador. Repetición con fixtures nuevos, sin borrar anteriores. Avisos de dependencias siguen sin resolver.
- Contrato/evidencia en `docs/architecture/document-materialization.md` y JSON. `git diff --check` y enlaces locales correctos. Sin esquema/dependencias ni estudio humano final.
- Rama preparada para commit/push/PR apilada. TD-02 implementado/probado pendiente revisión/integración; TD-03/04 abiertos. Concurrencia y corrección canónica posterior siguen fuera de alcance. Registro de PR #28 recibirá enlace sin declarar cierre.
- Recursos desechables se retiran al terminar; servicios habituales preservados. Siguiente paso: revisión; después resolver estados por campo y extractor en cambios acotados.
