# Sesión: 2026-10-26 · Pau/Codex · QR a ficha de pasaporte

- Encargo: resolver destino fijo localhost/question/1 y comprobar ficha utilizable.
- El equipo confirma que todavía no hay URL compartida. Configuración local y
  futura parametrización, sin publicación en Internet.
- Base: `main` en `2a65a43`; rama `feature/qr-passport-route`.
- Cambios: URLs de API/frontend configurables y validadas, CORS del origen previsto,
  consulta por UUID público y ruta React de lectura. Se conservan revisión documental
  y auditoría en la vista inicial de la aplicación.
- Evidencia: 120 pruebas backend en rama; 137 backend+BI con PR #11 combinada sin
  conflictos; build frontend y recorrido en Chromium correctos. Ver detalle en
  `docs/architecture/qr-passport.md`.
- Muestra sintética, servicios y base aislados; sin datos ni servicios compartidos
  modificados. No se prueba sincronización BaSyx ni ingesta end-to-end.
- No se modifica lógica de score/riesgo; quedan separados en la ficha. Documentos,
  mantenimiento y auditoría dentro del pasaporte son ampliaciones pendientes.
- Cierre: cambios preparados para commit/push/PR; consultar la PR de esta rama para
  su estado de publicación. No se fusiona automáticamente.
- Notion no actualizado; registrar avance como implementado/probado técnicamente,
  pendiente de revisión, integración y demostración en entorno del equipo.
- Reentrada: revisar PR #11 y esta rama, actualizar copia local tras merge y probar
  URLs con la IP LAN si se escanea desde móvil; localhost no identifica al ordenador
  cuando se abre desde otro dispositivo.
