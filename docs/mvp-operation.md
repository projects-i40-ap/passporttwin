# Operación del MVP y separación de entornos

Estado documental: 24/11/2026. Esta guía acompaña al [README](../README.md). No ejecuta migraciones, siembras ni restauraciones por sí misma.

## Un código, configuraciones y datos independientes

La copia principal, el ensayo y GitHub deben identificar el mismo commit cuando se quiera comparar su comportamiento. Tener el mismo código no implica tener las mismas bases de datos, PDFs, snapshots, modelos locales ni configuración de Metabase.

Antes de actualizar cada copia:

```powershell
git status --short --branch
git fetch origin
git log -1 --oneline origin/main
git merge --ff-only origin/main
git rev-parse HEAD
```

Si hay cambios locales, revisarlos y preservarlos antes de integrar. Si no es posible el avance directo, resolver la divergencia en una rama; no usar un reset destructivo para igualar copias. Conservar `.env`, originales y volúmenes. Tras un cambio de código, reconstruir los servicios afectados si la instalación usa imágenes sin montaje de fuentes; un commit sincronizado no acredita que los contenedores estén usando la imagen actual.

## Ensayo aislado

En el entorno de ensayo utilizado para la demostración, el proyecto Compose se llama `ptwin-ensayo`. Un archivo local `compose.ensayo.yml` separa puertos de la instalación principal:

| Servicio | Principal por defecto | Ensayo utilizado |
| --- | --- | --- |
| Frontend | 5173 | 15173 |
| Backend | 8000 | 18000 |
| PostgreSQL | 5433 | 15433 |
| BaSyx | 4001 | 14001 |
| Metabase | 3003 | 13003 |

El override debe retirar los `container_name` fijos y sustituir, no añadir, los mapeos de puertos. El archivo es local y no se versiona. No basta cambiar el puerto del frontend: comprobar también proyectos, volúmenes y URLs del backend, QR y pasaporte.

Si el override ya está configurado, en la terminal PowerShell del ensayo se pueden fijar las variables de Compose para que también las utilice `tools/dev.py`:

```powershell
$env:COMPOSE_PROJECT_NAME = 'ptwin-ensayo'
$env:COMPOSE_PATH_SEPARATOR = ';'
$env:COMPOSE_FILE = 'docker-compose.yml;compose.ensayo.yml'
docker compose ps
```

Estas variables afectan a esa terminal. Usar otra terminal para la instalación principal o retirarlas al cambiar de entorno. El estado del override y de `.env` debe verificarse antes de ejecutar comandos que escriban en la base de datos.

## Preparar el piloto de 16 instrumentos

Este procedimiento es para un entorno aislado preparado para datos sintéticos. No es necesario repetirlo para abrir una instalación que ya contiene el piloto.

1. Arrancar con `py tools/dev.py start`.
2. Instalar las tablas/vistas analíticas sin generar los cuatro casos de la demo mínima. En PowerShell, con el usuario y base locales por defecto:

```powershell
Get-Content -Raw infra/postgres/analytics_snapshot.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U passporttwin -d passporttwin
Get-Content -Raw bi/sql/fleet_overview.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U passporttwin -d passporttwin
Get-Content -Raw bi/sql/fleet_analytics.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U passporttwin -d passporttwin
```

Ejecutar cada paso comprobando que termina sin errores; adaptar usuario/base si la configuración no usa esos valores. No instalar vistas de aplicación en la base interna de Metabase.

3. Crear el piloto con una fecha explícita. Este ejemplo reproduce el punto de referencia histórico del 10 de noviembre; no pretende que todos los estados permanezcan iguales al avanzar el calendario:

```powershell
docker compose run --rm backend python -m scripts.seed_pilot_fleet --as-of 2026-11-10 --confirm-isolated
```

El generador conserva los instrumentos existentes y muestra sus URLs. El parámetro `--confirm-isolated` expresa una confirmación del operador: no sustituye comprobar a qué base se conecta. No usar `py tools/dev.py demo` si se quiere conservar un inventario de solo 16: ese comando añade los cuatro `PTWIN-DEMO-*`.

4. Configurar Metabase y provisionar las tarjetas según [bi/README.md](../bi/README.md). Los dashboards y sus identificadores pertenecen a cada instancia.

## Actualizar resultados analíticos guardados

El pasaporte consulta datos actuales; el panel de flota puede tener resultados guardados con fecha anterior. Para generar snapshots de toda la flota a la fecha actual del proceso:

```powershell
docker compose run --rm backend python -m scripts.refresh_analytics_snapshots --all
```

Para un instrumento usar `--instrument-id ID`, obteniendo el ID en esa instalación. `--as-of AAAA-MM-DD` permite declarar una referencia explícita. Refrescar las consultas del dashboard después. Un snapshot actualizado no sustituye la validación de los datos que lo alimentan.

## Demostración de revisión e incorporación

1. Comprobar estado, historial e indicadores del instrumento antes de empezar.
2. Subir un certificado sintético con una discrepancia intencionada y procesarlo.
3. Comparar el original con la referencia de identidad del caso; corregir el valor revisado, guardar y revalidar.
4. Incorporar al historial y verificar que solo se crea una nueva calibración.
5. Consultar el pasaporte y la auditoría; el original y su hash se conservan.

Si la identidad del documento no puede justificarse, no corregirla solo para que supere la regla. En una demostración, declarar la evidencia simulada. En operación real, resolver la discrepancia con evidencia autorizada.

Una prueba completa modifica el estado del caso. Para repetirla, usar una copia independiente respaldada o un instrumento de prueba distinto; no borrar la auditoría ni alterar fechas para aparentar una primera ejecución.

## Conservación y límites

Respaldar la base PostgreSQL junto con los archivos originales y la configuración necesaria para restaurarlos. Una exportación de tablas por sí sola no contiene los PDFs ni la configuración de Metabase. Conservar el commit y las versiones de las imágenes de cada entrega.

Los ensayos históricos y sus resultados no se regeneran por arrancar la aplicación. Las pruebas automatizadas se ejecutan en bases desechables. No se debe reinicializar un volumen ni regenerar casos como parte de una actualización ordinaria del código.
