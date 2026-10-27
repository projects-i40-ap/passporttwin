# Snapshots analíticos para Metabase

## Contrato

`POST /api/v1/instruments/{id}/analytics-snapshots?as_of=YYYY-MM-DD` crea un registro
nuevo y un evento de auditoría en la misma transacción. Fecha opcional: hoy en el
servidor; fechas futuras se rechazan con 422. Activo inexistente: 404.

No modifica los GET de score/riesgo ni sus fórmulas. No cambia el Health Score
para consumir la nueva probabilidad. El score del snapshot usa su método histórico
con observaciones hasta `as_of`; el riesgo usa su servicio independiente. La
familia B1 no interviene en el score; no se almacena como si fuera su origen.
El score conserva horizontes desde la última calibración; el riesgo los calcula
desde `as_of`. Guardar ambos no convierte sus escalas ni fechas de proyección
en equivalentes.

Se guardan: instrumento, referencia, fecha de cálculo, versiones de métodos,
pesos, manifiesto de entradas, SHA-256 del manifiesto, resultados completos y
columnas numéricas para BI. El manifiesto incluye estado operativo y las
calibraciones utilizadas (ID, fecha, error y tolerancia). No se consulta el futuro.
El estado operativo es el capturado al calcular: no reconstruye el estado histórico
ni el momento de ingesta/corrección. No se presenta como un backtest histórico exacto.

Los registros se añaden, no se sobrescriben. Repetir una actualización crea otro
registro con distinto ID, aunque los datos y el hash sean iguales. No hay endpoint
de edición/borrado. La política de retención y permisos SQL son responsabilidad
del despliegue; no se garantiza inmutabilidad frente a un administrador de BD.

Sin calibraciones, BI guarda health_score NULL y NOT_CALCULATED; el payload
original conserva el fallback 50 para trazabilidad. Datos metrológicos inválidos
no producen score numérico. Riesgo no estimable o sin dispersión conserva NULL
en las probabilidades; NULL nunca se convierte a cero.

## Vigencia para BI

`passporttwin_bi.fleet_analytics` conserva una fila por activo no retirado y elige
el snapshot por referencia más reciente, después fecha de cálculo e ID. Añade:

- `MISSING`: no existe snapshot.
- `STALE_DATE`: referencia anterior al día actual en PostgreSQL.
- `STALE_INPUTS`: cambió el estado o el conjunto/valores de calibraciones utilizadas.
- `CURRENT`: misma fecha y mismas entradas. No significa validación científica.

Las columnas `snapshot_*` conservan el último resultado histórico; las columnas
`current_*` son NULL cuando está desactualizado. El dashboard usa estas últimas
para score y probabilidades. Estado de cálculo, motivos, referencia y método
permiten distinguir resultados vigentes pero no estimables.

La comparación de origen usa JSONB, detecta altas, borrados y correcciones sin
depender únicamente de timestamps. Ignora calibraciones posteriores a la referencia.
No detecta por sí sola cambios en la configuración del proceso o versiones de
código no reflejadas en el registro: actualizar snapshots después de cambiar pesos
o desplegar un nuevo método. El resumen de score se agrupa por versión y pesos
para evitar mezclar configuraciones. Las fechas de API y BD deben compartir zona
horaria para que «hoy» coincida; se recomienda UTC en ambos servicios.

## Instalación y actualización explícita

Para una base existente, aplicar en orden a la base de aplicación:

```sh
docker compose exec -T postgres psql -U passporttwin -d passporttwin < infra/postgres/analytics_snapshot.sql
docker compose exec -T postgres psql -U passporttwin -d passporttwin < bi/sql/fleet_overview.sql
docker compose exec -T postgres psql -U passporttwin -d passporttwin < bi/sql/fleet_analytics.sql
```

Ajustar usuario/base al entorno. La primera instrucción es una migración aditiva
e idempotente; no elimina datos. La inicialización SQL nueva y el ORM incluyen la
tabla, pero volúmenes existentes no vuelven a ejecutar el init SQL automáticamente.
No se introduce Alembic sin una infraestructura de migraciones existente.

Para generar resultados de la flota activa, de forma deliberada:

```sh
docker compose run --rm backend python -m scripts.refresh_analytics_snapshots --all
# O seleccionar instrumentos:
docker compose run --rm backend python -m scripts.refresh_analytics_snapshots --instrument-id 1 --instrument-id 2
```

El CLI confirma una transacción por instrumento: un error posterior no revierte
los anteriores. Validar previamente los IDs; errores se propagan y no se afirma
éxito. No se instala un cron ni se ejecuta automáticamente desde una consulta.
Actualizar al menos cada día y tras aceptar/corregir calibraciones o cambiar pesos.

Dar lectura de la nueva vista al usuario BI y ejecutar el aprovisionamiento de
`bi/metabase/provision_fleet.py` como indica `bi/README.md`. Crea una copia con diez
tarjetas; no modifica silenciosamente el dashboard ya instalado. Las tres nuevas
muestran cobertura/vigencia, score por versión/pesos y riesgo a 30/60/90 días.

## Límites

Los indicadores siguen siendo experimentales. No se ha desplegado en un entorno
compartido ni se ha validado rendimiento en flotas grandes. La vista compara el
historial por activo; medir planes SQL antes de usarla a escala industrial. No se
añade autenticación: el POST debe protegerse conforme a la política del despliegue.

## Evidencia técnica 2026-10-27

- **142 pruebas backend+BI correctas**, Docker/Python 3.11 y PostgreSQL 17 aislado.
- POST: histórico de filas, auditoría, pesos/versiones y paridad de resultados con
  los GET existentes; ausencia de historial, errores, fechas futuras y 404.
- SQL: MISSING/CURRENT/STALE_DATE/STALE_INPUTS, ocultación de score y probabilidad
  cuando dejan de estar vigentes. Probabilidades persistidas contrastadas con payload.
- CLI de refresco ejecutado sobre flota sintética, sin cambios en datos compartidos.
- Diez tarjetas creadas y consultadas realmente en Metabase v0.64.3.4, con y sin
  filtro de ubicación. Un activo sin historial no aporta score y una corrección de
  origen marca el snapshot como desactualizado. La visualización no cambia el
  estado científico EXPERIMENTAL_UNCALIBRATED del riesgo.
