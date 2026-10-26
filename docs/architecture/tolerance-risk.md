# Riesgo de salida de tolerancia a 30/60/90 días

## Contrato y alcance

`GET /api/v1/instruments/{id}/tolerance-risk?as_of=2026-10-26`

`as_of` es opcional; por defecto se usa la fecha del servidor. Se recomienda
enviarla explícitamente para reproducibilidad. Los objetivos son `as_of + 30/60/90`
días, no la última calibración más esos días. Solo se ajustan observaciones con
fecha de calibración menor o igual a `as_of`. Esto simula disponibilidad por fecha
de calibración; no reconstruye el momento histórico de ingesta o correcciones.

El método `ols_gaussian_predictive_v1` ajusta error frente a días mediante mínimos
cuadrados por activo. La varianza residual usa n−2 grados de libertad. La desviación
predictiva incluye ruido y error de estimación de la media:

`sqrt(residual_variance * (1 + 1/n + (target_day - mean_day)^2 / Sxx))`.

Se estima `P(error < -tolerancia) + P(error > tolerancia)` con aproximación normal.
Es probabilidad en la fecha objetivo, no de cualquier cruce durante el intervalo.
No fuerza crecimiento monótono del riesgo. Se usa la tolerancia vigente del último
registro; historiales con tolerancia cambiante se rechazan hasta definir conversión.

Cada horizonte incluye fecha objetivo, error previsto, desviación predictiva,
probabilidad y señal de superación según el valor central. El resultado lleva
`validation_status=EXPERIMENTAL_UNCALIBRATED`, versión, fecha e historial utilizado.

Requiere al menos tres calibraciones con fechas distintas, errores finitos y
tolerancias positivas y finitas. Datos insuficientes, duplicados o inválidos
devuelven `NOT_ESTIMABLE` con motivo y horizontes vacíos. Una recta perfecta devuelve
proyección, pero probabilidad nula (`null`) con `ZERO_RESIDUAL_VARIANCE`: ausencia de
residuos no demuestra certeza. Activo inexistente: 404; fecha mal formada: 422.

## Coordinación con Health Score / PR #8

Esta rama parte de `main` y no modifica `analytics.py`, configuración de Health
Score, su esquema ni sus pruebas. Añade servicio, router y registro en `main.py`.
El endpoint `/predictions` mantiene su contrato y su riesgo anterior. El nuevo
riesgo todavía no alimenta el Health Score: esa conexión requiere una decisión
explícita y nuevos ensayos. Las PR pueden revisarse e integrarse independientemente.

## Comprobación sintética reproducible

Desde la raíz: `python experiments/benchmark_tolerance_risk.py`.

Usa el generador existente con semilla 42, 60 instrumentos y 19 calibraciones
espaciadas 30 días. Entrena con las primeras 16 y reserva las tres siguientes.
El informe incluye hash del dataset y Brier por horizonte frente a persistencia
del último estado fuera de tolerancia. Menor Brier es mejor.

| Horizonte | Casos positivos / total | Brier modelo | Brier persistencia |
| --- | --- | --- | --- |
| 30 días | 22 / 60 | 0.0280 | 0.1333 |
| 60 días | 26 / 60 | 0.0102 | 0.1667 |
| 90 días | 27 / 60 | 0.0038 | 0.1833 |

Se exploró primero un historial corto sin positivos; se alargó para comprobar
ambas clases. Por ello es un smoke benchmark de desarrollo, no un test final
congelado ni evidencia de selección imparcial. Ver `results_tolerance_risk_smoke.json`.

## Límites para la tarjeta y el TFM

La distribución normal, independencia, varianza estable y tendencia lineal son
hipótesis; no se ha demostrado calibración de probabilidades. Con pocos puntos,
la aproximación normal puede infravalorar incertidumbre. El generador comparte
estructura lineal con el modelo y no representa cambios de régimen o ajustes tras
mantenimiento. No se añadió M2 porque no se ha justificado complejidad adicional.

Pendientes: protocolo final congelado, calibración y sensibilidad por familia,
datos con intervenciones, revisión del equipo, UI y decisión sobre integración
con Health Score. No marcar la tarjeta como validada solo por estas pruebas.

## Checkpoint técnico 2026-10-26

- Rama `feature/tolerance-risk` sobre `main` (`29def6e`): 96 pruebas backend
  correctas en Docker/Python 3.11 con PostgreSQL 17 desechable.
- Combinación temporal con la PR #8 (`bc90870`): merge automático sin conflictos,
  112 pruebas correctas en el mismo entorno aislado. No se fusionó ninguna PR.
- El ensayo conserva ambos endpoints y las pruebas de Health Score. Esta evidencia
  corresponde a esos commits; cambios posteriores requerirán nueva comprobación.
- Benchmark sintético reproducido; configuración de pesos y código de la PR #8
  no se modificaron. La tarjeta continúa en curso, pendiente de revisión y validación.
