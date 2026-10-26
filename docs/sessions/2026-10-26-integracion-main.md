# Sesión: 2026-10-26 · Pau/Codex · Integración tras PR #7–#10

## Inicio

- Objetivo autorizado: comprobar el sistema integrado antes de nuevas funcionalidades.
- Base comprobada: `origin/main` en `2a65a43`, con las cuatro PR fusionadas.
- Rama de corrección: `fix/bi-test-schema-isolation`.
- Fuentes: repositorio/ejecución; plan de Notion según ZIP vigente. No se actualizó Notion.
- Servicios aislados de prueba; no se tocó el Metabase ni la base compartidos.

## SESSION END STATUS

- Frontend del main integrado: build Vite correcto en contenedor desechable.
- Suite conjunta sobre base nueva: inicialmente 128 correctas y un fallo por
  tolerancia NULL. La importación del backend crea tablas ORM con NOT NULL;
  los tests BI esperaban el esquema SQL, más permisivo. Las comprobaciones
  anteriores con el esquema SQL preinstalado no detectaban esa diferencia.
- Corrección: fixture BI crea tablas y vista en esquemas propios y hace rollback.
  No se relajan restricciones ni se alteran tablas operativas. La CI BI pasa ahora
  backend y BI en un mismo proceso para cubrir la regresión.
- Con la corrección: **129 pruebas correctas** en Docker/Python 3.11/PostgreSQL 17.
- Dashboard creado desde main en Metabase v0.64.3.4 desechable: siete preguntas
  ejecutadas correctamente, sin filtros y con ubicación (cuatro activos → dos).
- API HTTP real sobre la misma muestra: consulta de instrumento, Health Score,
  riesgo con fecha explícita, QR PNG y redirección de pasaporte correctos.
- La muestra insertada por SQL requirió completar campos obligatorios que el ORM
  normalmente genera en Python. No se considera una prueba de alta vía API/AAS.
- Muestra con errores 0.10, 0.23, 0.29, 0.47 cada 30 días, tolerancia 1:
  Health Score 43.5; probabilidad experimental a 90 días ~0.00613. Son métodos
  distintos: el score usa la proyección histórica de dos puntos, el nuevo riesgo
  OLS usa el historial completo. No interpretar sus resultados como equivalentes.
- QR resuelve, pero la redirección visual está fijada a
  `http://localhost:3003/question/1?public_id=...`. La pregunta de pasaporte no la
  crea el dashboard de flota. Falta configurar y probar destino real del despliegue.
- No se validó ingesta documental end-to-end, sincronización BaSyx ni experimento
  final. Los avisos de dependencias Starlette/Requests no impidieron las pruebas.

## Pendientes y reentrada

1. Revisar/integrar esta corrección de pruebas y confirmar CI.
2. Instalar vista y dashboard en el Metabase compartido siguiendo `bi/README.md`.
3. Resolver URL pública del QR y destino de pasaporte como trabajo acotado.
4. Acordar persistencia de snapshots/versiones de score y riesgo para Metabase,
   y decidir explícitamente si el Health Score debe usar el nuevo riesgo.
5. Actualizar tarjetas con evidencia: cambios integrados/probados técnicamente,
   pero validación experimental y demo final pendientes. No marcar todo como Done.

Sin mensajes enviados al compañero. Servicios y datos desechables retirados al
terminar. Consultar la PR de esta rama para el commit y la publicación definitivos.
