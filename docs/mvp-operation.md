# MVP operations and environment separation

Documentation status: 24 November 2026. This guide accompanies the [README](../README.md). It does not itself execute migrations, seed data or restore operations.

## Shared code, independent configuration and data

The main local copy, rehearsal environment and GitHub should identify the same commit when comparing their behavior. Identical code does not imply identical databases, PDFs, snapshots, local models or Metabase configuration.

Before updating each copy:

```powershell
git status --short --branch
git fetch origin
git log -1 --oneline origin/main
git merge --ff-only origin/main
git rev-parse HEAD
```

Review and preserve local changes before integration. If fast-forward is not possible, resolve the divergence on a branch; do not use a destructive reset to align copies. Preserve `.env`, originals and volumes. After code changes, rebuild affected services if the installation uses images without source mounts; matching commits do not prove that containers are running the current image.

## Isolated rehearsal environment

The rehearsal environment used for the demonstration has the Compose project name `ptwin-ensayo`. A local `compose.ensayo.yml` file separates its ports from the main installation:

| Service | Main installation defaults | Rehearsal environment used |
| --- | --- | --- |
| Frontend | 5173 | 15173 |
| Backend | 8000 | 18000 |
| PostgreSQL | 5433 | 15433 |
| BaSyx | 4001 | 14001 |
| Metabase | 3003 | 13003 |

The override must remove fixed `container_name` values and replace, rather than append to, port mappings. This file is local and is not versioned. Changing only the frontend port is insufficient: also check projects, volumes and backend, QR and passport URLs.

If the override is already configured, set Compose variables in the rehearsal PowerShell terminal so that `tools/dev.py` also uses them:

```powershell
$env:COMPOSE_PROJECT_NAME = 'ptwin-ensayo'
$env:COMPOSE_PATH_SEPARATOR = ';'
$env:COMPOSE_FILE = 'docker-compose.yml;compose.ensayo.yml'
docker compose ps
```

These variables affect that terminal. Use a different terminal for the main installation or remove them when switching environments. Check the override and `.env` before running commands that write to the database.

## Preparing the 16-instrument pilot

This procedure is for an isolated environment prepared for synthetic data. It does not need to be repeated to open an installation that already contains the pilot.

1. Start with `py tools/dev.py start`.
2. Install analytical tables/views without generating the four minimal-demo cases. In PowerShell, using the default local database user and name:

```powershell
Get-Content -Raw infra/postgres/analytics_snapshot.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U passporttwin -d passporttwin
Get-Content -Raw bi/sql/fleet_overview.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U passporttwin -d passporttwin
Get-Content -Raw bi/sql/fleet_analytics.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U passporttwin -d passporttwin
```

Check that each step completes without errors; adapt the user/database if the configuration uses different values. Do not install application views in Metabase's internal database.

3. Create the pilot with an explicit date. This example reproduces the historical reference point of 10 November; it does not imply that all statuses remain unchanged as time passes:

```powershell
docker compose run --rm backend python -m scripts.seed_pilot_fleet --as-of 2026-11-10 --confirm-isolated
```

The generator preserves existing instruments and prints their URLs. `--confirm-isolated` expresses operator confirmation: it does not replace checking the database connection. Do not run `py tools/dev.py demo` if the inventory must remain at 16 instruments: that command adds the four `PTWIN-DEMO-*` cases.

4. Configure Metabase and provision its cards following [bi/README.md](../bi/README.md). Dashboards and their identifiers belong to each instance.

## Refreshing saved analytical results

The passport queries current data; the fleet dashboard may contain results saved on an earlier date. To generate fleet-wide snapshots using the process's current date:

```powershell
docker compose run --rm backend python -m scripts.refresh_analytics_snapshots --all
```

For one instrument, use `--instrument-id ID`, obtaining the ID from that installation. `--as-of YYYY-MM-DD` sets an explicit reference date. Refresh dashboard queries afterwards. An up-to-date snapshot does not replace validation of its input data.

## Demonstrating review and ingestion

1. Check the instrument's state, history and indicators before starting.
2. Upload and process a synthetic certificate with an intentional discrepancy.
3. Compare the original with the case's identity reference; correct the reviewed value, save and revalidate.
4. Ingest it into the history and verify that only one new calibration is created.
5. Inspect the passport and audit trail; the original and its hash are preserved.

If the document's identity cannot be justified, do not correct it merely to pass a rule. In a demonstration, identify simulated evidence as such. In real operation, resolve the discrepancy using authorized evidence.

A complete test changes the case's state. To repeat it, use a separate backed-up copy or a different test instrument; do not delete the audit trail or alter dates to make it look like a first run.

## Preservation and limitations

Back up PostgreSQL together with the original files and configuration needed to restore them. A table export alone does not contain the PDFs or Metabase configuration. Preserve the commit and image versions for each delivery.

Starting the application does not regenerate historical experiments or their results. Automated tests run in disposable databases. Do not reinitialize a volume or regenerate cases as part of a routine code update.
