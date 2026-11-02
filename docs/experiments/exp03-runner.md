# EXP-03: ejecutor aislado y fecha controlada

Entrega de preparación de la tarjeta de siete experimentos. No constituye el protocolo final aprobado ni una evaluación industrial. Complementa la [matriz de preparación de la PR #19](https://github.com/projects-i40-ap/passporttwin/pull/19), sin depender de que esté integrada.

## Qué cambia

`experiments/run_rules_exp03.py` utiliza las rutas reales de subida y procesamiento en una instancia FastAPI propia con TestClient. Exige un PostgreSQL explícito cuyo nombre termine en `_test` y que no tenga tablas públicas. Carga el catálogo de `experiments/fixtures/exp03-catalog.json`; no infiere la identidad canónica de las respuestas del modelo.

El reloj se fija mediante `--reference-date`. La dependencia `validation_reference_date` conserva UTC por defecto en la aplicación normal. No hay parámetro HTTP ni variable de entorno que permita al cliente cambiar la fecha de validación. La aplicación aislada sustituye esa dependencia en memoria; se aplica tanto a procesamiento como a revalidación.

Se fuerza el extractor determinista. No se invoca una API externa, LLM, aceptación canónica ni AAS/BaSyx. El runner escribe en su base desechable y en un RAW temporal que se retira al terminar. No borra tablas ni limpia una base usada: para repetir, crear otra base nueva.

El benchmark histórico `benchmark_rules_exp03.py` y `results_exp03.json` se conservan intactos.

## Contrato del informe

- Una fila por certificado: EVALUATED o ERROR, etapa y tipo de error. Subidas duplicadas no se reutilizan y los fallos no desaparecen del denominador planificado.
- COMPLETE significa que todas las muestras pudieron evaluarse, **no que se hayan superado criterios de aceptación**. Una clasificación incorrecta es un resultado experimental válido, no un fallo de infraestructura.
- Si falla una muestra, estado FAILED, código de salida 2 y `metrics: null`. Solo se conservan diagnósticos parciales claramente separados. Un fallo de preparación genera SETUP_FAILED sin métricas. Los informes existentes no se sobrescriben.
- Precision, recall, F1, accuracy y soportes por regla; coincidencia exacta de estado y conjunto de reglas. Denominadores indefinidos producen `null`. Una regla sin positivos no queda validada por tener accuracy alta.
- Commit, identificación de árbol modificado cuando Git está disponible, hashes de fuentes, PDFs, catálogo/manifiesto, versiones Python/dependencias y fecha de referencia. Se verifica que los archivos de entrada no cambien durante la ejecución; si cambian, FAILED_INPUT_CHANGED sin métricas finales.
- Si la imagen no incluye Git, `--code-commit` recibe el SHA completo desde el host. Se etiqueta como identidad declarada y no verificada dentro del contenedor; el estado del árbol queda desconocido y los hashes describen los archivos efectivamente ejecutados. El operador debe comprobar árbol limpio y correspondencia con el commit antes del ensayo final.

R-DUP-01 pertenece a la subida y R-TOL-01 a la aceptación canónica: están excluidas explícitamente de la clasificación documental. Necesitan recorridos de evaluación propios para completar EXP-03.

## Ejecución con Docker desde PowerShell

Usar **solo datos sintéticos y una base nueva desechable**. Estos comandos son para la rama que contiene el runner, no para un `main` anterior a su integración. Docker debe estar arrancado. Ejecutar cada línea por separado desde la raíz.

Si no existe la imagen backend, construirla con `docker compose build backend`. Preparar red y PostgreSQL exclusivos para este ensayo:

```powershell
docker network create ptwin-exp03
```

```powershell
docker run -d --name ptwin-exp03-db --network ptwin-exp03 -e POSTGRES_DB=ptwin_exp03_test -e POSTGRES_USER=passporttwin -e POSTGRES_PASSWORD=test-only postgres:17
```

Comprobar que responde «accepting connections» antes de continuar:

```powershell
docker exec ptwin-exp03-db pg_isready -U passporttwin -d ptwin_exp03_test
```

Revisar el estado Git y obtener el commit; la imagen no necesita incluir Git:

```powershell
git status --short
```

```powershell
$commitExp03 = git rev-parse HEAD
```

Crear un destino local para resultados:

```powershell
New-Item -ItemType Directory -Force experiments/runs | Out-Null
```

Comprobación técnica del corpus histórico con referencia **01/10/2026**, no nueva evaluación final:

```powershell
docker run --rm --network ptwin-exp03 -v "$($PWD.Path):/repo:ro" -v "$($PWD.Path)/experiments/runs:/results" -w /repo -e DATABASE_URL=postgresql://passporttwin:test-only@ptwin-exp03-db:5432/ptwin_exp03_test -e AI_LEGO_ENABLED=false passporttwin-backend:latest python experiments/run_rules_exp03.py --reference-date 2026-10-01 --code-commit $commitExp03 --output /results/exp03-preparation-01.json
```

No apunta a la base local de PassportTwin ni necesita su API arrancada. No usa credenciales de Metabase. El corpus histórico tiene los dos casos FUTURE_DATE fechados 31/10/2026: la referencia debe declararse explícitamente. Cambiar la referencia cambia el significado de esas etiquetas, no se deben regenerar o reinterpretar silenciosamente para obtener mejores métricas.

Repetir requiere otro archivo de salida **y otra base vacía**. No ejecutar un reset de la base habitual para cumplir ese requisito.

## Verificación de esta entrega

- 184 tests backend+BI correctos en Docker, Python 3.11 y PostgreSQL 17 desechable. Se cubren fecha fija/predeterminada, ausencia de parámetro de fecha público, falsos positivos/negativos por regla, falta de PDF, duplicados, timeout, HTTP/JSON inválidos, protección de informes y fallos de setup.
- Rutas reales sobre los 20 PDFs históricos: con referencia 01/10/2026, 20 evaluados, cero errores, 8 TP y 12 TN. Con referencia 01/11/2026, 20 evaluados, 6 TP, 12 TN y 2 FN respecto de las etiquetas antiguas; demuestra la dependencia temporal que había que hacer explícita.
- Una nueva ejecución sobre una base ya utilizada es rechazada antes de importar el ORM o escribir datos. El informe de rechazo queda preservado.
- [Informe de preparación versionado](../../experiments/results/exp03_runner_preparation.json): ejecución del código identificado por commit y hashes, con corpus histórico. No sustituye al informe final.
- Persisten avisos de Requests/Starlette de dependencias en el entorno; no provocaron fallos. Esta entrega no modifica el conjunto de dependencias.

## Pendiente para el EXP-03 final

Acordar el protocolo y los criterios antes de ejecutar; ampliar la muestra y cobertura por regla; fijar reloj/catálogo/PDFs y hashes en un commit previo; evaluar también duplicados y aceptación fuera de tolerancia. Los 20 PDFs actuales no tienen casos positivos dedicados de unidad, rango o campos obligatorios ausentes. No presentar la comprobación técnica como evidencia suficiente de todas las reglas ni como una evaluación independiente tras ajustes.
