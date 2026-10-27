# Sesión: 2026-10-27 · Pau/Codex · Preparar cierre de tres tarjetas

- Encargo: completar criterios de Health Score, riesgo y dashboard con evidencia.
- Se contrastó el ZIP vigente: Health Score requiere cuatro factores. El usuario
  confirmó expresamente completar el alcance original, sin reducirlo a v1.
- Rama `feature/complete-health-score` basada en `feature/analytics-snapshots`
  (`cb91e08`, PR #13 pendiente). No se modifica la rama de Alexander ni se integra
  antes de su revisión. CI admite temporalmente PR con esa rama base.
- V2 integra calibración, nueva probabilidad, incidencias recientes y calidad;
  conserva v1 en `/predictions`. La ficha y los snapshots usan v2. Historial e
  invalidación incluyen los nuevos datos. Tras mantenimiento requiere rebaseline.
- **158 tests backend+BI correctos**, build frontend y Chromium reales correctos.
- Evaluación v2: 1.000 casos, 12.000 comprobaciones; cambios de pesos como hipótesis
  de diseño, no optimización. Metabase v0.64.3.4: 50 consultas correctas sobre diez
  tarjetas, dos familias, filtros, orden, falta de datos, caducidad y refresco.
- PR #14 independiente: protocolo de riesgo fijado antes de ejecutar, 3.240
  pronósticos; evidencia favorable bajo hipótesis lineales y fallos de régimen
  publicados. No son los siete experimentos finales completos.
- Dossier `docs/three-cards-closure.md`: criterios, textos para Notion y condiciones
  de cierre. No se actualizaron estados en Notion ni se enviaron mensajes al compañero.
- Pendientes: revisar políticas de pesos/calidad/incidencias y alcance experimental;
  integrar #13 y después retarget/revisar esta ampliación contra main, reaplicar
  vista y refrescar snapshots. La instalación compartida sigue separada.
- Cierre: preparado para commit/push/PR; ver la PR de la rama para estado definitivo.
  Servicios desechables retirados al terminar; datos operativos no modificados.
