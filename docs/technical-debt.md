# Registro de deuda técnica de PassportTwin

> Reading note, 24 November 2026: this register preserves the historical November status. The [current README](../README.md) and [evaluation closeout](experiments/mvp-final-results.md) describe the completed MVP. Not all findings have been revalidated here, and completing the MVP does not resolve industrial robustness debt.

Actualizado: **02/11/2026**. Inventario técnico central; incluye defectos confirmados, deuda de robustez/mantenimiento y revisiones pendientes, indicando la diferencia. No equivale al estado oficial de tarjetas de Notion ni declara tareas asignadas. Fuente: `main` `823a4bb`, [comprobación integrada](verification/integrated-2026-11-02.md) e inspección del código/configuración. Crear este registro no corrige hallazgos: consultar el estado y los commits de cada fila. Integraciones verificadas después en `main` `602b659`: #33 ha propagado #30/#31 a main.

## Cómo usarlo

- **P0:** bloquea una tarea del ensayo o puede hacer interpretar incorrectamente el resultado. Resolver antes del piloto afectado.
- **P1:** mejora la operación, robustez o reproducibilidad. Resolver antes del uso al que afecta o aceptar explícitamente la limitación para el TFM.
- **P2:** mantenimiento posterior o mejora que puede aplazarse con alcance documentado.
- **Confirmado:** existe evidencia de código, configuración o ejecución; consultar la columna fuente. **Por verificar:** falta comprobar el riesgo; no es un fallo demostrado.
- Todos los registros abiertos están **sin asignar** hasta acuerdo de Pau/Alexander. Al iniciar, registrar responsable y rama/PR. Cerrar solo con criterio comprobado, evidencia y commit integrado; conservar la fila como histórico.
- Una PR propuesta no convierte una deuda en resuelta. La prioridad no exige implementar robustez de producción para defender un MVP; sí exige explicar qué queda fuera y no afirmar capacidades no demostradas.

## Antes del piloto y evaluación de tareas

| ID / prioridad | Tipo / estado | Problema e impacto | Evidencia y correspondencia | Criterio de cierre |
| --- | --- | --- | --- | --- |
| TD-01 · P0 | Integrado en main por [PR #29](https://github.com/projects-i40-ap/passporttwin/pull/29), commit `9f34501`; validación final separada | Desde el pasaporte se revisan campos pero no se abre el PDF original. Bloquea recuperar el certificado en EXP-07 CERT. | `frontend/src/Passport.jsx`, OpenAPI y Chromium del ensayo; UI-01 del backlog. | Acción separada para original y revisión; archivo correcto servido por ID, hash coherente, error de ausencia legible y sin exponer rutas internas; prueba desde UI. |
| TD-02 · P0 | Integrado en main por [PR #33](https://github.com/projects-i40-ap/passporttwin/pull/33), commit `602b659`; origen #30 | Revalidar devuelve ACCEPTED pero no crea calibración. La UI anuncia aceptación sin ofrecer materialización canónica. | `frontend/src/main.jsx`, endpoints `revalidate`/`accept`; ensayo: cero calibraciones tras revalidar y una tras `/accept`; UI-02. | Fases y estado visibles; materializar desde UI con resultado verificable, historial actualizado y tratamiento de repetición/409. No confundir estado del staging con ingesta canónica. |
| TD-03 · P0 | Integrado en main por [PR #33](https://github.com/projects-i40-ap/passporttwin/pull/33), commit `602b659`; origen #31 | Documento ACCEPTED conserva campos STAGING («Pendiente de validación»). Dificulta saber qué queda pendiente. | `documents.py`, `presentation.js` y Chromium; UI-03. | Semántica por campo/documento/materialización acordada y consistente en API/UI; preservar RAW y correcciones; verificación del recorrido. |
| TD-04 · P0 para ampliar formatos | Integrado en main por [PR #32](https://github.com/projects-i40-ap/passporttwin/pull/32), commit `0f4f3ac`; evaluación independiente separada | `Serial Number: CLOSEOUT-A` produce `Number`; no encuentra el activo. `Serial:` funciona. | `backend/app/services/document_identity.py`, respuesta real del ensayo; DOC-01. | Etiquetas soportadas extraídas correctamente y regresiones de variantes, múltiples series y orden; no reciclar esa regresión como evaluación final independiente. |

## Operación, mantenimiento y reproducibilidad

| ID / prioridad | Tipo / estado | Deuda e impacto | Fuente / alcance | Criterio de cierre |
| --- | --- | --- | --- | --- |
| TD-05 · P1 | Usabilidad / abierto, confirmado | Navegación por IDs, mezcla de idiomas/etiquetas técnicas y feedback desigual entre pantallas. | `main.jsx`, `InstrumentFinder.jsx`; UI-04/05. No incluye automáticamente todo rediseño cosmético. | Tareas acordadas realizables sin memorizar IDs, términos y mensajes coherentes, regreso/contexto preservados; comprobación de tareas y piloto. |
| TD-06 · P1 antes de uso compartido persistente | Infraestructura / abierto, confirmado | BaSyx usa memoria en configuración de desarrollo; reiniciar puede perder la proyección. | README, `docker-compose.yml`; PostgreSQL sigue siendo canónico y `/sync` permite reconstruir. | Persistencia y recuperación demostradas en entorno elegido, o alcance MVP explícito con reconstrucción ensayada tras reinicio. No afirmar almacenamiento AAS duradero mientras tanto. |
| TD-07 · P1 antes de operación continuada | Robustez / abierto, confirmado | Sin política robusta de reintentos/recuperación AAS; errores se registran en logs y estado global sin detalle suficiente para el operador. | `backend/app/services/aas_builder.py`, endpoint `/sync`, README. | Fallos parciales identificables, política acotada de recuperación y comprobación de indisponibilidad/reintento sin duplicar o degradar el estado canónico. |
| TD-08 · P1 para entorno reproducible | Dependencias / abierto, confirmado | Aviso de compatibilidad Requests/urllib3/chardet y deprecación Starlette/BlockingPortal. Suites verdes no demuestran compatibilidad futura. | Salida de la suite integrada y `backend/requirements.txt`; no se diagnostica vulnerabilidad por estos avisos. | Entorno compatible reproducible, avisos eliminados mediante versiones compatibles y comprobación de rutas relevantes; registrar versiones efectivas. |
| TD-09 · P1 antes de congelación final | Reproducibilidad / abierto, confirmado | Frontend sin lockfile versionado y usa `npm install`; Compose usa Metabase `latest`; imágenes base con tags móviles. | `frontend/package.json`, `frontend/Dockerfile`, `.github/workflows/ci.yml`, `docker-compose.yml`. Último build usa dependencias cacheadas, no instalación limpia. | Lockfile y estrategia de instalación definida; versiones/digests registrados para el ensayo; build limpio y verificación de compatibilidad. No es necesario inmovilizar toda actualización futura. |
| TD-10 · P1 para repetición E2E | Automatización / abierto, confirmado | El ensayo integrado utiliza probes de sesión con IDs/rutas efímeros; sus hashes quedan registrados, pero no hay un nuevo runner portable de ese recorrido completo. | [Informe integrado](verification/integrated-2026-11-02.md). Los runners EXP individuales sí existen. | Recorrido seleccionado reproducible desde checkout limpio, con fixtures/guardas de aislamiento, informe y limpieza de recursos propios; errores conservados sin omitir pasos. |
| TD-11 · P2 | Dependencia heredada / abierto, confirmado | Herramienta AASX v2 requiere SDK 0.2.2 y pip 24.0 por metadatos antiguos. Está aislada de producción. | `experiments/aasx/requirements.txt`, Dockerfile y [EXP-06](experiments/exp06-aasx.md). | Mantener entorno aislado verificable y ruta de mantenimiento documentada; una futura migración debe preservar perfil y referencias mediante round-trip, sin cambiar versión AAS silenciosamente. |

## Revisiones pendientes: no son defectos demostrados

| ID / prioridad | Estado | Qué comprobar | Evidencia actual y condición de cierre |
| --- | --- | --- | --- |
| REV-01 · P1 según despliegue | Por verificar, sin asignar | Durabilidad de RAW y restauración coherente con PostgreSQL al recrear contenedores/desplegar. | El ensayo no demostró conservación de RAW a través de recreaciones. Revisar configuración elegida y probar restauración/lectura con hashes; no afirmar pérdida en el entorno de Pau sin comprobarlo. |
| REV-02 · P1 según concurrencia | Por verificar, sin asignar | Aceptación simultánea del mismo documento y atomicidad de la protección de materialización. | Existe guarda `R-DUP-ACCEPT`; repetición secuencial devuelve 409 y no duplica en ensayo. Concurrencia no probada. Si aplica, demostrar una sola materialización bajo concurrencia y definir contrato de repetición; no registrar «sin protección» como hecho. |
| REV-03 · P1 antes de piloto UI | Por verificar, sin asignar | Accesibilidad y responsive del recorrido completo. | Hay comprobaciones de pantallas a 1280/390 px, no auditoría completa. Verificar teclado, foco, etiquetas, contraste y tablas/errores en tareas; enlazar UI-07. |

## Fuera de este registro

- **Validación/investigación:** [preparación EXP-01…07](experiments/final-execution-readiness.md), criterios, muestra independiente, calibración de probabilidades y sesiones humanas. No son bugs por estar pendientes. Los datos reales son opcionales; sintéticos explícitos no bloquean el cierre acordado.
- **Producto/diseño:** el [backlog frontend](frontend-usability-backlog.md) detalla UI-06/08 y el resto de propuestas. No toda preferencia visual ni nueva acción es deuda técnica; priorizar con el equipo.
- **Evolución de alcance:** circularidad, nuevos modelos, nuevas plantillas AAS estandarizadas y funciones futuras. La semántica específica MVP se documenta como límite de interoperabilidad, sin prometer certificación.
- **Memoria y defensa:** [plan de cierre](project-closeout.md) e [índice metodológico](thesis/methodology-evidence-index.md). Son entregables, no deuda de implementación.

## Historial de implementación y comprobaciones

Las notas siguientes conservan los checkpoints anteriores. Estado actual: TD-01…04 integrados en main tras #33; no equivale a validación académica final. El candidato pasa 324 backend/BI y build frontend; [informe](verification/reviewed-documents-integration-2026-11-02.md).

- TD-01/UI-01: PR #29, código `541c2a3`, endpoint original con hash y visor/descarga. 282 backend/BI pasan (12 nuevos), build correcto y siete controles Chromium. [Contrato y límites en la rama de implementación](https://github.com/projects-i40-ap/passporttwin/blob/feature/document-original/docs/architecture/document-original.md). No se marca cerrado hasta integrar; TD-02/03 siguen su estado en las filas del registro; TD-04 se sigue en PR #32, pendiente de integración. No se asigna responsable de revisión por inferencia.

- TD-02/UI-02: PR #30 apilada sobre #29, código `fa5ebe0`, incorporación explícita con auditoría y aviso de proyección fallida. 292 backend/BI y build correctos; nueve controles Chromium, incluida caída real de AAS. No se declara cerrado ni se extiende ese resultado a concurrencia, TD-04 o política de edición canónica posterior; TD-03 se sigue en su propia PR.

- TD-03/UI-03: PR #31 apilada sobre #30, código `aacd523`. Estados por comprobaciones realmente aplicadas, evidencia/no evaluado y conservación de históricos/borradores; 301 backend/BI, build y siete controles de navegador. Nueve tests nuevos y 13 focales tras metadatos de auditoría. Pendiente integración; no amplía reglas, ni corrige TD-04.

- TD-04/DOC-01: PR #32 independiente desde main, código `e280f8e`, reconoce etiqueta completa sin identidades Number/Calibration por campos vacíos. 293 backend/BI; composición #29–31 + corrección: 324 en `test/document-ui-and-label` (`2f6615e`). Pendiente integración; valores solo en otra línea se abstienen y no se reprocesan históricos.

- TD-05 / UI-04/05: [PR #34](https://github.com/projects-i40-ap/passporttwin/pull/34) implementa inicio por tareas, selección por nombres, enlaces con contexto de URL y textos comunes de auditoría. Pruebas: 332 backend/BI, build y 12 controles de navegador. Pendiente revisión/integración y piloto; carga/procesado en UI, catálogo completo de textos y diseño visual común siguen fuera de este alcance.

## Mantenimiento del registro

Por cada fila conservar ID, prioridad, estado, responsable, evidencia y criterio. Añadir enlace a PR al iniciar y commit integrado al cerrar; fecha y resultado de comprobación obligatorios. Si cambia una hipótesis tras inspección, corregirla y preservar qué evidencia motivó el cambio. Vincular desde Notion cuando se actualice, sin afirmar que el plan externo se ha sincronizado por editar este archivo.
