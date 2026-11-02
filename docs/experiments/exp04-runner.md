# EXP-04: preparación reproducible de deriva B0/B1/M1

Esta entrega prepara la ejecución de EXP-04. Trabaja sobre datos sintéticos conocidos de desarrollo, **no es el test final independiente ni determina aceptación o selección del modelo**. No requiere base de datos, Metabase, AAS o conexión de red.

## Generación e identificación de datos

`experiments/run_drift_exp04.py prepare` reutiliza el generador histórico sin modificarlo. Aísla su RNG para no alterar el estado aleatorio del proceso y serializa UTF-8 con finales de línea LF. Crea un directorio nuevo con `dataset.csv` y `manifest.json`, nunca sobrescribe un paquete existente.

El manifiesto registra semilla, parámetros, unidades, hash del generador, SHA-256 del CSV y contrato de preparación. Con los valores predeterminados: seed 42, tres familias, 20 instrumentos por familia, ocho calibraciones por activo a intervalos de 90 días, primeras seis para entrenamiento y últimas dos para evaluación.

La evaluación verifica el checksum **y regenera los bytes desde la semilla/parámetros declarados**. Rechaza cambios de datos, fuente del generador o contrato, registros perdidos, campos no finitos, fechas duplicadas, tolerancia inválida, unidades incoherentes y tiempo transcurrido que no concuerda con las fechas. Al terminar vuelve a comprobar hashes para detectar cambios durante la ejecución.

No se modifica `ai/datasets/drift_synthetic.csv`, el benchmark histórico ni `results_exp04.json`. El paquete generado puede permanecer fuera de Git; el manifiesto y el código identifican cómo regenerarlo exactamente en la versión Python registrada.

## Corte temporal

Cada activo tiene un origen fijo: su sexta calibración. Se pronostican sus dos observaciones posteriores sin incorporar la primera de test para predecir la segunda. Los horizontes predeterminados son **90 y 180 días**, no los 30/60/90 del experimento de riesgo EXP-05.

- **B0:** último error observado del activo.
- **B1:** pendiente media de extremos históricos de la familia. Su pool solo contiene los prefijos de entrenamiento de cada activo y, dentro de ellos, las fechas **anteriores o iguales al origen del pronóstico objetivo**. Incluye el activo objetivo. Un vecino con menos de dos observaciones elegibles no aporta una pendiente; el activo objetivo sí tiene historial suficiente.
- **M1:** OLS del historial de entrenamiento del activo.

No se utilizan las columnas del simulador `true_offset` o `true_drift_rate_per_day` como features. El error del objetivo se usa únicamente como etiqueta para puntuar.

El informe conserva por pronóstico origen, fecha objetivo, máxima fecha familiar usada y número de observaciones familiares posteriores excluidas. La fecha de calibración es un **supuesto de disponibilidad**: no demuestra disponibilidad histórica de ingesta o correcciones en un sistema real.

## Relación con el código desplegado

B1 y M1 invocan directamente los kernels de `DriftAnalyticsService`, no otra regresión copiada en el benchmark. B0 y las proyecciones siguen el redondeo a cuatro decimales del servicio. Un test contrasta los tres resultados con `calculate_drift_and_risk` a 90 días.

La API actual publica 30/60/90; el benchmark aplica los mismos kernels también a 180 días. Este ensayo no demuestra una ruta HTTP a 180 días ni cambia los modelos o el filtrado de la API. Tampoco modifica el cálculo de Health Score o riesgo.

## Métricas e informe

- MAE/RMSE **por familia y horizonte**, con unidad física explícita: bar, °C o pH.
- Error normalizado: `(predicción - etiqueta) / tolerancia en el origen`. La tolerancia positiva debe ser constante en el historial de cada activo.
- Agregados de flota solo de errores normalizados, globales y por horizonte, con ponderación por pronóstico (micro). No se promedian errores físicos de magnitudes distintas.
- COMPLETE significa ejecución completa de los pronósticos previstos. No significa que se haya superado un umbral académico: el contrato de preparación tiene `acceptance_thresholds: null`.
- Fallos generan informe FAILED, métricas nulas y salida 2. Los informes previos no se sobrescriben. Un directorio de paquete existente tampoco se reutiliza silenciosamente.
- Se registran commit, versiones, hashes de fuentes/datos/manifiesto y detalles de las predicciones. Sin Git en la imagen, el SHA se declara desde el host, queda etiquetado como no verificado dentro del contenedor y el estado del árbol como desconocido. Los hashes identifican los archivos efectivos; comprobar árbol limpio y correspondencia con commit antes de la ejecución final.

## Uso en PowerShell con Docker

Disponible al integrar esta rama. Se necesita la imagen `passporttwin-backend:latest` con las dependencias del backend; si no existe, construirla desde la raíz con `docker compose build backend`. Los contenedores siguientes usan `--network none` y no arrancan ni consultan servicios habituales.

Ejecutar cada línea por separado desde la raíz del repositorio. El destino ya está excluido por `.gitignore`:

```powershell
New-Item -ItemType Directory -Force data/generator/output | Out-Null
```

```powershell
git status --short
```

```powershell
$commitExp04 = git rev-parse HEAD
```

Crear el paquete de preparación en un directorio nuevo:

```powershell
docker run --rm --network none -v "$($PWD.Path):/repo:ro" -v "$($PWD.Path)/data/generator/output:/runs" -w /tmp passporttwin-backend:latest python /repo/experiments/run_drift_exp04.py prepare --bundle /runs/exp04-preparation-a
```

Evaluar sin modificar el paquete:

```powershell
docker run --rm --network none -v "$($PWD.Path):/repo:ro" -v "$($PWD.Path)/data/generator/output:/runs" -w /tmp passporttwin-backend:latest python /repo/experiments/run_drift_exp04.py evaluate --bundle /runs/exp04-preparation-a --code-commit $commitExp04 --output /runs/exp04-preparation-a-report.json
```

Una repetición puede evaluar el mismo paquete en **otro archivo de informe**. Para comprobar la generación repetida, usar otro directorio de paquete. Los archivos locales de salida quedan bajo `data/generator/output/`; no se necesitan claves de Metabase ni credenciales de PostgreSQL.

## Evidencia de preparación — 01/11/2026

- **181 tests backend+BI** correctos en Docker/Python 3.11/PostgreSQL 17 desechable. Esta rama parte de main y es independiente de las PR #19/#20; el recuento no incluye los tests nuevos de la PR #20 aún pendiente.
- Dos paquetes generados sin red producen CSV y manifiesto idénticos. SHA-256 del CSV: `182256822d9a2fd731beb88209207a23fe24c394e41b396fce55589999b2537d`.
- Recorrido CLI completo sin red: 60 activos, 480 observaciones, 120 pronósticos evaluados, seis grupos familia/horizonte. Regeneración exacta verificada.
- En 114 pronósticos se excluyó alguna observación del prefijo familiar posterior al origen. No es un resultado de precisión: evidencia que el corte por calendario afecta al pool de entrenamiento.
- Los tests perturban etiquetas futuras y observaciones de vecinos posteriores al origen y verifican invariancia de pronósticos previos. También verifican unidades/normalización, entradas inválidas, metadatos incoherentes, preservación de resultados y equivalencia con el servicio a 90 días.
- [Manifiesto registrado](../../experiments/results/exp04_preparation_manifest.json) e [informe completo de preparación](../../experiments/results/exp04_runner_preparation.json), con hashes contrastados contra el commit de código registrado. El CSV se regenera, no se añade como datos finales.
- Persisten los avisos previos de dependencias Requests/Starlette; no provocaron fallos. No se cambiaron dependencias ni fórmulas.

## Pendiente para el EXP-04 final

Reconciliar B1 con la descripción histórica de media/mediana del backlog; confirmar horizontes y criterios antes del ensayo final. Separar desarrollo y test independiente, congelar protocolo/datos en commit previo y registrar versiones/imágenes efectivas. La simulación es lineal y favorece las hipótesis de M1: incluir límites y resultados adversos sin ajustar sobre el test final. Este resultado no valida uso industrial ni una mejora universal y no cierra la tarjeta de siete experimentos.
