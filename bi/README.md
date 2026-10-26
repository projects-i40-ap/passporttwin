# Dashboard de flota en Metabase

Primer bloque de la tarjeta «Construir dashboard de flota en Metabase con semáforo
y priorización». Usa datos canónicos actuales y es independiente de las PR #8 y #9.
No cambia backend, frontend, Health Score ni estimación de riesgo.

## Instalación explícita

1. Aplicar `bi/sql/fleet_overview.sql` a la base de aplicación con una cuenta que
   pueda crear esquema y vista. Ejemplo local:

   ```sh
   docker compose exec -T postgres psql -U passporttwin -d passporttwin < bi/sql/fleet_overview.sql
   ```

   Ajustar usuario y base si no se usan los valores locales. No ejecutarlo sobre
   la base interna `metabase`. La vista no se instala automáticamente al arrancar.
2. En Metabase, conectar PostgreSQL con un usuario de solo lectura al esquema
   `passporttwin_bi`, incluyendo `USAGE` del esquema y `SELECT` sobre la vista.
   El propietario de la vista necesita lectura de las tablas canónicas. La
   configuración exacta de roles corresponde al entorno de despliegue.
3. Crear o elegir una colección de destino y obtener sus IDs y el de la conexión.
4. En el entorno del comando, definir `METABASE_URL` y `METABASE_API_KEY` o
   `METABASE_SESSION_TOKEN`, sin guardarlos en Git. Ejecutar con las dependencias
   del backend instaladas:

   ```sh
   python bi/metabase/provision_fleet.py --database-id 2 --collection-id 3
   ```

El script crea un dashboard nuevo y siete preguntas guardadas; imprime su URL.
No modifica dashboards existentes. Repetirlo crea otra copia deliberadamente.
Si falla a mitad puede dejar objetos parciales: revisarlos en la colección antes
de reintentar. No envía credenciales por consola; usar HTTPS fuera de una red local.

## Contenido

- KPIs: instrumentos activos, calibraciones vencidas, vencimientos en 30 días y
  documentos vinculados que requieren revisión o han fallado extracción.
- Distribución por semáforo, primeras 50 prioridades y próximos vencimientos a 90 días.
- Filtros de texto por familia y ubicación, aplicados a todas las preguntas.
- Ratio observado `abs(error) / tolerancia`: no es probabilidad de fallo.

Se excluyen retirados. Una fila por activo; documentos agregados antes de unir
para evitar duplicar instrumentos. La última calibración no futura se elige por
fecha y, en empate, ID descendente. Los días se calculan con CURRENT_DATE de
PostgreSQL: documentar la zona horaria de la base al comparar con otras fuentes.

## Semáforo y prioridad

1. Rojo: bloqueo/fuera de tolerancia, último resultado fallido, error superior a
   tolerancia o calibración vencida.
2. Gris: no hay calibración, error/tolerancia no válidos o falta vencimiento.
3. Amarillo: vence en 0–30 días, documentos por revisar, ratio >= 0.8 o error AAS.
4. Verde: sin las alertas anteriores. No equivale a certificación de buen estado.

La causa principal usa esa precedencia. Se muestran también métricas auxiliares
para no ocultar alertas secundarias. Orden de intervención: rojo, amarillo, gris,
verde; dentro de cada grupo criticidad y vencimiento. Es una política de diseño
para revisión del equipo, no una priorización validada experimentalmente.

Los documentos sin activo asignado no entran en el KPI por instrumento. El Health
Score y la probabilidad predictiva de las PR #8/#9 no están materializados en la
base: integrarlos con Metabase requiere un contrato de persistencia o una carga
de snapshots posterior, sin inventar datos ni llamar APIs por cada fila SQL.

## Pruebas

`bi/tests/test_fleet_sql.py` ejecuta casos de frontera en PostgreSQL real con rollback
por caso. `test_provision_fleet.py` comprueba peticiones, filtros y fallo HTTP.
Usar DATABASE_URL de una base desechable y ejecutar `python -m pytest bi/tests -v`
desde la raíz con dependencias del backend. No utilizar una base operativa para tests.

La tarjeta permanece en curso hasta revisar la priorización, validar el dashboard
en el entorno compartido e incorporar la visualización predictiva acordada.

## Evidencia del checkpoint 2026-10-26

- 17 pruebas BI correctas con PostgreSQL 17 desechable (SQL y aprovisionamiento).
- Creación real del dashboard y sus siete preguntas en Metabase v0.64.3.4,
  imagen `metabase/metabase:latest` con digest
  `sha256:7804ce4edfa217dd08a896821f57b12a9a392d944bd3797a55520d51c76232e3`.
- Todas las preguntas ejecutadas sin filtros y con filtro de ubicación. KPI de
  prueba: cuatro activos totales, dos al seleccionar Lab A. La configuración de
  ambos filtros se comprueba además en las pruebas de aprovisionamiento.
- Merge temporal con PR #8 (`bc90870`) y PR #9 (`1980253`): sin conflictos,
  129 pruebas backend + BI correctas en Docker/Python 3.11. Ninguna PR fusionada.
- El Metabase y los datos usados son desechables, no vuestro entorno compartido.
  El procedimiento debe repetirse contra la versión de Metabase del despliegue.
- La CI nueva `BI checks` comprueba SQL/aprovisionamiento con PostgreSQL; no levanta
  Metabase. Los avisos de dependencias Starlette/Requests no provocaron fallos.
