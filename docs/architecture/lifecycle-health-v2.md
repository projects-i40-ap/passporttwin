# Health Score de ciclo de vida v2 — alcance original del backlog

El equipo confirmó el 27/10/2026 que se completan los cuatro factores originales,
sin reducir la tarjeta al indicador metrológico v1. Nuevo contrato:
`GET /api/v1/instruments/{id}/health-score?as_of=YYYY-MM-DD`.

## Política explícita del MVP

`score = round(clamp(100 - sum(peso * penalización * 100), 0, 100), 1)`.

| Componente | Peso por defecto | Penalización |
| --- | ---: | --- |
| calibration_status | 0.30 | 1 si fuera de tolerancia, bloqueado, calibración fallida o vencida; 0.5 si vence en 0–30 días; 0 sin alerta |
| predicted_risk | 0.30 | Máxima probabilidad de excedencia entre 30/60/90 días del estimador independiente |
| recent_incidents | 0.20 | Suma acotada a 1: LOW=0.25, MEDIUM=0.5, HIGH/CRITICAL=1, para incidencias no resueltas en los últimos 90 días |
| data_quality | 0.20 | Proporción de seis comprobaciones no satisfechas: serial, fabricante, modelo y ubicación no vacíos; metrología válida; documentación vinculada existente y toda aceptada |

Las fechas de calibración/vencimiento deben ser coherentes. No basta con un dato
vacío para asumir buen estado: si falta calibración utilizable, vencimiento,
probabilidad o severidad reconocida, el componente es desconocido. Si su peso es
positivo, el score completo es NULL/NOT_CALCULATED y se enumeran los componentes
pendientes. Un peso cero excluye deliberadamente ese componente; no se renormalizan
los pesos restantes ni se inventa un fallback 50.

Los pesos son **hipótesis de diseño**, no coeficientes óptimos demostrados. Validación
`DESIGN_POLICY_SYNTHETIC_ONLY`. Un score alto no invalida el semáforo rojo basado en
una alerta observada ni certifica conformidad metrológica. No se fijan umbrales de
acción automática por score en este cambio.

Configurar `LIFECYCLE_HEALTH_WEIGHTS` con JSON de estos cuatro nombres, valores
finitos en [0,1] y suma 1. Se rechazan claves desconocidas. `HEALTH_SCORE_WEIGHTS`
permanece reservado al v1 de `/predictions`, que se conserva compatible. La ficha
React y los snapshots utilizan ahora v2, con versión diferenciada.

## Mantenimiento y estimación de riesgo

`/tolerance-risk`, v2 y snapshots usan la política
`rebaseline_after_any_maintenance_v1`. Solo utilizan calibraciones posteriores
al último mantenimiento conocido hasta la referencia; no se conoce orden intradía.
Si no quedan tres fechas distintas: `INSUFFICIENT_POST_MAINTENANCE_HISTORY`.

Es conservadora porque el modelo de eventos actual no distingue una inspección
de un ajuste con efecto metrológico. No se atribuye causalidad por descripción
libre. Una vez tipificados los eventos se podrá afinar esta política. No anticipa
mantenimiento o cambios bruscos futuros desconocidos.

El núcleo OLS sigue siendo experimental y no calibrado para industria real.
La evaluación independiente muestra mala cobertura bajo curvatura y cambios de
régimen; no se ocultan esos escenarios ni se presentan como validados.

## Compatibilidad e instalación

Esta rama está basada en la PR #13: integrar primero snapshots, después este cambio.
No requiere otra tabla. Reaplicar `bi/sql/fleet_analytics.sql` y regenerar snapshots:
el manifiesto de entradas pasa a versión 2 e incluye identidad, calibraciones con
resultado/vencimiento, estado documental, incidencias/resolución y mantenimiento.
Los cambios en cualquiera de esos datos invalidan el resultado para BI.

Los snapshots v1 quedan históricos y desactualizados por incompatibilidad de
manifiesto. El resumen Metabase separa métodos y pesos; no mezcla scores v1/v2.
No reconstruye disponibilidad histórica real de documentos o correcciones: captura
el contexto conocido al calcular y lo documenta. La fecha por sí sola no crea un
backtest histórico del estado completo.

## Evidencia para aceptación

- Tests unitarios de los cuatro factores, severidades, resolución, antigüedad,
  desconocidos, rebaseline y configuración inválida.
- Evaluación reproducible `python experiments/acceptance_health_v2.py`: 1.000
  casos sintéticos, 12.000 comprobaciones de rango/reconstrucción, sensibilidad
  acotada y monotonicidad de severidad. Variación máxima observada: 10 puntos
  entre las tres configuraciones ensayadas. No demuestra pesos óptimos.
- Integración API/snapshot/vista: incidentes, documentos y mantenimiento cambian
  la vigencia; el refresco coincide con la ficha y preserva el historial.
- Aceptación Metabase en `experiments/acceptance_lifecycle_dashboard.py`, que solo
  permite fixtures en una base *_test vacía y una instancia Metabase nueva.

Pendientes antes de Done: revisión del equipo de esta política y resultados,
integración de PR y aplicación de vistas/refresh en el entorno de demostración.
