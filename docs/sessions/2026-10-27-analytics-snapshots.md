# Sesión: 2026-10-27 · Pau/Codex · Indicadores analíticos en Metabase

- Objetivo autorizado: guardar resultados con referencia, versión y pesos y
  mostrarlos en Metabase distinguiendo ausencia y caducidad.
- Base: `main` en `1560bfc`; rama `feature/analytics-snapshots`.
- Fuentes del plan: backlog exportado confirmado vigente y actualizaciones de
  tarjetas realizadas por el usuario. Notion no actualizado desde Codex.
- Cambios: tabla aditiva, refresco explícito POST/CLI con auditoría, manifiesto/hash,
  vista de vigencia y tres tarjetas adicionales. No cambia frontend ni fórmulas.
- Pruebas: 142 correctas en Docker/PostgreSQL; diez tarjetas consultadas en Metabase
  desechable y CLI ejecutado sobre muestras. Ver contrato técnico para detalle.
- Se comprobó el caso con datos preexistentes; las aserciones se limitan al activo
  del test para no depender de una base vacía. Ningún dato operativo modificado.
- Pendientes: revisión/merge, instalar migración y vista en entorno del equipo,
  generar snapshots y crear una copia nueva del dashboard. No se instala cron.
- Limitaciones: CURRENT verifica fecha y datos, no configuración actual del proceso;
  refrescar tras cambiar pesos o método. Validación científica y rendimiento a
  escala pendientes. Mantener tarjetas en curso hasta sus criterios completos.
- Cierre: preparado para commit/push/PR; consultar la PR de esta rama para estado
  definitivo. Sin mensajes al compañero ni publicación en entorno compartido.
- Reentrada: revisar contrato `docs/architecture/analytics-snapshots.md`, aplicar
  instalación explícita y verificar resultados con los datos de demostración del equipo.
