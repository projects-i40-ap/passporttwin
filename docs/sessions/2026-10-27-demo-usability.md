# Sesión: 2026-10-27 · Pau/Codex · Usabilidad antes del ensayo

- Encargo: completar seis mejoras: fechas, estados legibles, acciones de datos
  insuficientes, navegación, comandos reproducibles y unidades.
- Base `main` en `b32d22b`; rama `feature/demo-usability`.
- Tarjeta propuesta «Mejorar usabilidad y preparar demo reproducible», Pau,
  High/In Progress; el usuario pasará el enlace de Notion después. No se ha editado Notion.
- Nuevos datos de presentación y timestamp UTC del cálculo vivo. Resultado BI
  guardado separado y comparado con el mismo manifiesto utilizado al persistir.
- Ficha/revisión/Metabase traducen estados; unidades del catálogo sin conversiones.
  Búsqueda y enlaces a ficha/documentos/auditoría, con regreso al pasaporte.
- `python tools/dev.py start` y `python tools/dev.py demo`: configuración local,
  vistas transaccionales y cuatro fixtures etiquetados. No borran datos ni resetean
  correcciones existentes. La demo no demuestra ingesta ni sincronización AAS.
- Verificación: 164 pruebas correctas, build frontend y Compose válido. Seeder
  repetido y conservación de correcciones comprobados. Metabase real, 50 consultas;
  Chromium con rutas, datos, acciones, unidades y móvil, sin errores JS.
- En el caso de coexistencia se detectó y corrigió la colisión de hash entre
  certificados sintéticos de revisión: el PDF identifica ahora su activo también
  en metadatos. No se alteran los documentos existentes.
- Pendientes: revisión/merge, añadir enlace de tarjeta a PR y ejecutar comandos
  en el ordenador del equipo con las URLs apropiadas. Instalar copia actualizada
  del dashboard y definir su URL opcional antes del ensayo.
- Cierre: preparado para commit/push/PR; consultar la PR de la rama para publicación.
  Servicios desechables retirados al terminar, sin tocar la base compartida.
