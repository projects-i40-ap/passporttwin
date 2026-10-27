# Health Score metrológico v1 — compatibilidad

La ficha y snapshots utilizan el nuevo [Health Score de ciclo de vida v2](lifecycle-health-v2.md),
que completa los cuatro factores originales. Este documento conserva el contrato
histórico de `/predictions`; no debe confundirse con el indicador v2.

El endpoint existente `GET /api/v1/instruments/{id}/predictions` conserva
`health_score` y añade `health_score_details`. No requiere cambios de esquema.

## Cálculo MVP

`score = clamp(round(100 × (1 − suma(peso × valor)), 1), 0, 100)`.

| Componente | Valor utilizado | Peso por defecto |
| --- | --- | --- |
| `risk_90_days` | Cociente acotado de error proyectado absoluto / tolerancia a 90 días, redondeado a dos decimales | 0.40 |
| `current_error` | Cociente acotado de error actual absoluto / tolerancia | 0.35 |
| `out_of_tolerance` | 1 si el estado del instrumento es `out_of_tolerance`, 0 en otro caso | 0.25 |

Se conserva la proyección histórica de los dos últimos puntos y el comportamiento
de tolerancia del servicio actual; no se sustituye por B1 o M1 en este cambio.
Los pesos por defecto reproducen el cálculo previo.

`health_score_details` expone versión del método, pesos, valor y penalización en
puntos de cada componente, penalización total y puntuación final. Las contribuciones
no se redondean antes de sumar; redondear la puntuación reconstruida a un decimal.

Sin calibraciones se conserva `health_score=50` por compatibilidad, con
`status=NOT_CALCULATED`, `fallback=true`, componentes vacíos y penalización total
nula. Ese 50 no es evidencia de salud media del activo.

## Configuración

Añadir a `.env` (backend Compose ya lo carga) o al entorno del proceso:

```dotenv
HEALTH_SCORE_WEIGHTS='{"risk_90_days":0.5,"current_error":0.3,"out_of_tolerance":0.2}'
```

Recrear el backend para aplicar cambios de entorno. La configuración se lee al
iniciar el proceso; no es un endpoint de edición. Los pesos deben ser finitos,
estar entre 0 y 1 y sumar 1 (tolerancia numérica 1e-9). Se rechazan claves
desconocidas. Una configuración inválida impide iniciar el backend.

## Límites y evidencia

Es un indicador heurístico del MVP: los pesos son decisiones de diseño pendientes
de validación experimental. El cociente denominado riesgo no es una probabilidad
calibrada. Todavía no incorpora completitud documental, vigencia o incidentes.

Pruebas: `docker compose run --rm backend python -m pytest tests/test_drift_analytics.py tests/test_health_score.py -v`.

Checkpoint 2026-10-26: suite backend completa ejecutada con Python 3.11 en
`passporttwin-backend:latest`, montando el código de la rama y usando PostgreSQL
17 desechable en una red aislada: **98 passed**. Incluye comprobación del contrato
HTTP, configuración por entorno, rechazo de pesos inválidos y casos sin historial.
Se observaron avisos de dependencias de Starlette/Requests; no fallos de pruebas.
No equivale a validación experimental de los pesos ni a una prueba de la UI.
