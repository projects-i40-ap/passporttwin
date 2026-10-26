# PassportTwin: instrucciones para Codex

## Fuentes y evidencia

- Notion controla plan, alcance, prioridad, responsable y dependencias. Si no hay acceso, usar la exportación más reciente identificada por el equipo y registrar esa limitación. No afirmar haber actualizado Notion sin hacerlo.
- Git y GitHub describen el código, ramas, commits y PR existentes. Comprobarlos antes de asumir que una conversación refleja el estado actual.
- Las pruebas y la ejecución aportan evidencia de funcionamiento; la validación académica requiere el protocolo experimental correspondiente.
- Los documentos iniciales y chats son contexto histórico. Reconciliar contradicciones relevantes y hacerlas visibles antes de una decisión dependiente.
- Distinguir: PROPOSED → IMPLEMENTED → TESTED → INTEGRATED → VALIDATED. No equiparar estos estados con los estados de una tarjeta.

## Inicio de sesión

1. Leer estas instrucciones y el último cierre disponible en `docs/sessions/`.
2. Identificar persona, tarea principal, alcance, criterios de aceptación y dependencias. Consultar la tarjeta o su exportación.
3. Revisar `git status --short --branch`, rama actual, remotos e historial. Cuando haya conexión, ejecutar `git fetch --all --prune` y comprobar ramas remotas y divergencias.
4. Conservar los cambios locales existentes. No usar reset destructivo ni cambiar de rama con cambios sin entender su procedencia.
5. Una tarea principal por rama; no desarrollar directamente en `main`. Usar `feature/`, `fix/`, `docs/`, `test/` o `chore/`. En entornos con una rama de trabajo preasignada, comprobar y registrar su propósito antes de crear otra.
6. Revisar posibles solapamientos con el compañero. Preparar el aviso con tarea, rama y módulos previstos; enviarlo solo cuando el usuario haya autorizado el canal y el envío.

`CONTRIBUTING.md` conserva convenciones anteriores de ramas `track-a/` y `track-b/` y commits por capa. La metodología del equipo de septiembre de 2026 y las ramas recientes usan `feature/`, `fix/` y prefijos convencionales; estas instrucciones siguen esa evolución. Conservar las ramas existentes y no renombrarlas automáticamente.

## Desarrollo y arquitectura

- Inspeccionar antes de modificar. Hacer cambios pequeños vinculados a la tarea; registrar dependencias nuevas y evitar ampliaciones de alcance sin acuerdo.
- PostgreSQL es el estado canónico; AAS/BaSyx es su proyección interoperable reconstruible.
- Preservar RAW, hashes y procedencia. Los documentos y las salidas LLM requieren validación/revisión antes de actualizar datos aceptados.
- Mantener la separación entre extracción, normalización, matching, validación y aceptación.
- El frontend actual es React/Vite y la visualización BI utiliza Metabase. No introducir Streamlit por seguir documentos históricos.
- Revisar contratos, esquema y pruebas actuales antes de modificar persistencia o API. No asumir que existe Alembic: comprobar el mecanismo de esquema vigente.
- No versionar `.env`, credenciales, datos privados ni artefactos voluminosos de ejecución.

## Mapa y comprobaciones

- `backend/app/api/`: rutas FastAPI; `models/`, `schemas/`, `database/`: persistencia y contratos.
- `backend/app/services/`: documentos, reglas, CSV, analítica, AAS y RAG.
- `backend/tests/`: pruebas backend; `frontend/`: React/Vite.
- `infra/postgres/`: esquema e inicialización; `generators/`: datos sintéticos.
- `docs/architecture/`, `docs/diagrams/`, `docs/thesis/`: documentación estable.

Comandos existentes en el repositorio (su presencia no demuestra una ejecución correcta):

```sh
# Desde la raíz, con Docker disponible y .env local configurado:
docker compose up -d --build
docker compose run --rm backend python -m pytest tests -v

# Frontend; el mismo build se usa en CI:
cd frontend
npm install
npm run build
```

La CI usa Python 3.11, PostgreSQL 17 y `pytest` desde `backend/`; el build frontend usa Node 20. Inspeccionar `.github/workflows/ci.yml` si cambia.

- Elegir comprobaciones proporcionales al cambio. Para backend, la referencia del equipo es Docker; registrar por separado comprobaciones locales y ejecución en contenedor.
- Revisar fixtures y efectos de las pruebas antes de ejecutarlas; usar una base de pruebas, nunca datos compartidos importantes.
- Ejecutar `git diff --check` y revisar el diff. Para documentación, comprobar rutas y comandos contra la configuración; no ejecutar toda la suite sin necesidad.
- Informar comandos, resultados y bloqueos reales. No reutilizar resultados históricos como validación actual.

## Cierre y coordinación

- Registrar un cierre con `docs/sessions/TEMPLATE.md`; incluir evidencia, estado Git y siguiente paso concreto.
- Crear commits como checkpoints lógicos y revisados; subir la rama al finalizar cuando esté dentro del encargo y haya acceso. Si no se hace, declararlo.
- PR: tarea relacionada, problema, cambios, validación y limitaciones. Revisión del compañero antes de integrar según el acuerdo del equipo; no fusionar por asumir aprobación.
- Done requiere criterios completos, evidencia, integración/revisión correspondiente y plan actualizado. Si Notion está inaccesible, preparar el texto e indicar que la actualización sigue pendiente.
- Consolidar decisiones estables y resultados en `docs/` y la memoria; no presentar propuestas como hechos.
