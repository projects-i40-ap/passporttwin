# Dossier de cierre de las tres tarjetas — 27/10/2026

Estado: **candidatas a cierre tras revisión e integración**, no cerradas desde Codex.
El usuario confirmó mantener el alcance original de cuatro factores del Health
Score. No se sustituyen requisitos por pruebas del indicador anterior.

## 1. Health Score explicable y configurable

- Calibración, riesgo previsto, incidencias recientes y calidad de datos: implementados
  en `lifecycle_health_v2`, cada uno con peso, valor y penalización visibles.
- Configuración validada y política explícita. Score NULL si falta un componente
  de peso positivo; ningún 50 inventado ni renormalización silenciosa.
- Ficha, API y snapshot comparten cálculo; legacy `/predictions` conserva v1.
- 1.000 escenarios sintéticos y 12.000 comprobaciones de coherencia/sensibilidad;
  pesos documentados como hipótesis de diseño, sin afirmar optimalidad.

**Texto de cierre propuesto tras merge/revisión:**
Implementado el Health Score v2 con los cuatro factores del backlog, pesos
configurables y desglose explicable. Comprobados casos normales, vencidos,
incidencias, datos incompletos y ausencia de modelo fiable. Integrado con ficha
y snapshots versionados para Metabase. Aceptado como política de diseño del MVP,
con validación sintética y limitaciones documentadas; no certifica salud industrial.

## 2. Riesgo de salida de tolerancia 30/60/90 días

- Estimación temporal con fechas objetivo, incertidumbre, exclusión de futuro y
  estados no estimables, mostrados en ficha y dashboard.
- Protocolo fijado antes de ejecutar: 1.080 trayectorias, 3.240 predicciones,
  tres familias, dos longitudes de historial y seis escenarios.
- En estable+lineal: Brier 0.06256 vs 0.10093 de persistencia de estado y 0.07308
  de persistencia gaussiana; ECE 0.02652, cobertura nominal 95% observada 92.69%.
- Curvatura y cambios de régimen degradan el modelo: resultados adversos publicados.
  Tras mantenimiento conocido se exige rebaseline; no se predicen cambios futuros
  desconocidos. M2 no se añade sin un protocolo de mejora independiente.

**Texto de cierre propuesto tras merge/revisión:**
Implementada la estimación experimental a 30/60/90 días y evaluada temporalmente
frente a baselines en datos sintéticos. Se documentan sus hipótesis lineales,
calibración limitada y fallos ante cambios de régimen. La política posterior al
mantenimiento evita reutilizar automáticamente el historial anterior. Aceptada
como estimación experimental del MVP, sin afirmar validación con datos reales.

## 3. Dashboard de flota en Metabase

- KPIs, estados, vencimientos, inconsistencias, prioridades, top riesgo y filtros
  por familia/ubicación; diez tarjetas aprovisionadas reproduciblemente.
- Snapshots versionados: fechas, pesos, métodos, manifiesto, hash y auditoría.
- CURRENT/MISSING/STALE_DATE/STALE_INPUTS; valores antiguos ocultos en columnas
  vigentes y NULL diferenciado de cero. Cambios de incidencias/documentos/mantenimiento
  invalidan la vigencia y el refresco coincide con la ficha.
- Aceptación real en Metabase v0.64.3.4: 50 consultas, dos familias, filtros
  individuales/combinados/sin resultados, orden por riesgo y datos ausentes.

**Texto de cierre propuesto tras merge/revisión:**
Dashboard implementado con indicadores operativos y analíticos, filtros, semáforo
y priorización. Verificados datos ausentes, snapshots desactualizados, ranking y
refresco mediante aceptación reproducible en Metabase desechable. Scripts y guía
de instalación entregados. No se afirma despliegue en un entorno compartido que
todavía no existe; esa instalación se mantiene como actividad separada de despliegue.

## Evidencia conjunta y orden de revisión

1. PR #14: protocolo y resultados independientes de evaluación.
2. PR #13: infraestructura de snapshots pendiente; integrar antes de la rama v2.
3. Rama `feature/complete-health-score`: basada en #13 para revisar únicamente
   la ampliación funcional. Reaplicar vista de BI y refrescar snapshots tras merge.
4. Aceptación técnica: **158 tests backend+BI correctos**, build frontend correcto,
   Chromium con cuatro factores, móvil, falta de historial y rebaseline; sin errores JS.
5. Revisar las políticas y limitaciones con Alexander. Después registrar evidencia
   en Notion y cambiar estados. Codex no ha editado las tarjetas ni fusionado PR.

Las tareas de experimentos finales EXP-01…07, memoria y demo completa siguen
separadas: este dossier no las declara terminadas. Validación industrial real,
tipificación de intervenciones y evaluación con usuarios son límites/futuro trabajo,
no resultados obtenidos por estos ensayos.
