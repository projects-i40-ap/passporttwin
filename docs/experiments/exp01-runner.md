# EXP-01: preparación de evaluación de extracción por campo

`experiments/run_extraction_exp01.py` evalúa directamente el extractor determinista de certificados que usa la aplicación. No modifica el extractor, documentos, base de datos, catálogo ni resultados históricos. No ejecuta matching, reglas, aceptación canónica, LLM ni OCR de imágenes.

Esta entrega es una **comprobación de preparación sobre datos sintéticos conocidos**, no el protocolo final aprobado ni validación con certificados industriales.

## Qué se compara

El manifiesto indica para cada PDF su `certificate_id`, `filename` y `ground_truth`. Solo se puntúan los campos explícitamente anotados:

- Clave omitida: **no anotada**, excluida del denominador y de los verdaderos negativos.
- Clave con `null` o texto vacío: ausencia explícitamente anotada.
- Clave con valor: contenido esperado del documento, aunque sea una fecha futura o un serial que no exista en el catálogo. Transcribir correctamente una inconsistencia no significa validarla o aceptarla.

Campos soportados: `serial_number`, `calibration_date`, `next_due_date`, `error_value`, `tolerance`, `unit`, `operating_range`. El corpus actual solo anota los cinco primeros: 20 documentos × 5 = 100 celdas. Los dos restantes quedan con soporte cero y métricas no disponibles, no con una supuesta evaluación correcta.

La extracción no se sustituye por el ground truth ni se aplican correcciones humanas antes de puntuar. Las predicciones sobre campos sin anotar se registran aparte y no se califican como acierto o error.

## Comparación y métricas

Contrato `exp01_preparation_v1`, explícito en cada informe:

- Texto: recorte de espacios exteriores; conserva mayúsculas, signos e identidad. No convierte unidades ni corrige series.
- Fechas: comparación tras normalizar fechas válidas ISO o DD/MM/YYYY a ISO. No aplica restricciones cronológicas del motor de reglas. Un ground truth con fecha inválida se rechaza antes del ensayo; para evaluar transcripción literal de fechas inválidas se necesitaría otra política.
- Números: igualdad Decimal exacta y finita, aceptando coma decimal. Sin tolerancia numérica implícita; los valores truncados no se consideran equivalentes.
- Valor correcto presente: TP. Valor incorrecto presente cuando se esperaba otro: **un FP y un FN**. Campo esperado ausente: FN. Campo espurio donde se anotó ausencia: FP. Ausencia correcta explícita: TN.
- Accuracy: celdas exactamente correctas / celdas anotadas. No se obtiene sumando TP/FP/FN/TN, porque una sustitución aporta FP y FN.
- Precision/recall/F1 por campo y microagregados de extracción de valores. Denominadores indefinidos quedan en `null`; un campo sin anotaciones no se presenta como validado.
- `potential_review_fraction`: proporción de celdas anotadas discrepantes. Es un indicador de revisión potencial, **no porcentaje de correcciones humanas medido**. `human_corrections_measured` queda nulo.

El extractor determinista actual es el método evaluado. No se inventa una comparación con entrada manual, otro modelo o LLM: `baseline_comparison.status` queda NOT_EVALUATED. No hay umbrales de aceptación final ni selección automática.

## Integridad y errores

Un PDF válido pero vacío se puntúa como extracción sin campos; no cuenta como éxito de contenido. Un PDF ausente/corrupto o una excepción se registra como ERROR, conservando la fila y su etapa. Si falla alguna muestra, la corrida tiene estado FAILED, salida 2 y métricas finales nulas; las métricas parciales solo aparecen como diagnóstico.

COMPLETE indica que se pudieron puntuar todas las muestras, no que se hayan alcanzado objetivos científicos. SETUP_FAILED describe un problema previo de manifiesto/entorno. Un informe existente no se sobrescribe.

Se registran hashes de PDFs/manifiesto y fuentes, versiones, commit y política de comparación. Los hashes de entrada se contrastan al terminar; un cambio invalida las métricas finales. Si no hay Git en la imagen, el SHA completo se declara desde el host y se etiqueta como no verificado dentro del contenedor, con estado del árbol desconocido. Contrastar árbol limpio y hashes antes de una corrida final.

## Ejecución desde PowerShell

Disponible en la rama que incluye el runner. Requiere Docker y la imagen backend con sus dependencias (`docker compose build backend` si falta). No necesita arrancar servicios ni claves de Metabase. Ejecutar cada línea por separado desde la raíz:

```powershell
New-Item -ItemType Directory -Force data/generator/output | Out-Null
```

```powershell
git status --short
```

```powershell
$commitExp01 = git rev-parse HEAD
```

```powershell
docker run --rm --network none -v "$($PWD.Path):/repo:ro" -v "$($PWD.Path)/data/generator/output:/runs" -w /tmp passporttwin-backend:latest python /repo/experiments/run_extraction_exp01.py --code-commit $commitExp01 --output /runs/exp01-preparation-01.json
```

El manifiesto predeterminado es `generators/test_certificates_batch/ground_truth.json`. Para otro corpus, indicar `--manifest` con una ruta dentro del contenedor. La repetición debe usar un nombre nuevo de informe; los PDFs y el manifiesto permanecen intactos. Las salidas locales bajo `data/generator/output/` ya están excluidas por `.gitignore`.

## Evidencia de preparación — 01/11/2026

- **188 tests backend+BI correctos** en Docker/Python 3.11/PostgreSQL 17 desechable. Rama independiente de las otras preparaciones, basada en main tras PR #18; no incluye sus tests pendientes de integrar.
- CLI sin red: 20/20 PDFs evaluados, cero errores, 100/100 celdas anotadas coincidentes. Soporte 20 por cada uno de los cinco campos anotados; cero para unidad/rango. El porcentaje potencial de revisión de estas celdas es cero; no se midieron correcciones humanas.
- Los controles cubren normalización, serial/case y unidades no reparados, sustituciones FP+FN, ausencias/no anotados, PDFs vacíos/corruptos/ausentes, fallos de extractor, valores no finitos, informes protegidos y separación entre extracción y reglas cronológicas.
- [Informe completo](../../experiments/results/exp01_runner_preparation.json), con hashes de fuentes contrastados contra el commit registrado. Avisos previos de dependencias Requests/Starlette sin fallos; no se modifican dependencias.

## Pendiente para el EXP-01 final

El corpus usa una plantilla digital sintética estrecha y conocida. Los errores inyectados para EXP-03 no sustituyen una muestra diversa de extracción. Ampliar formatos/campos anotados y casos de ausencia/ambigüedad; decidir si imágenes/OCR están dentro del alcance; recoger baseline manual o alternativo y correcciones humanas solo si se van a comparar. Acordar criterios y congelar datos/protocolo independientes antes del ensayo final. El 100/100 observado aquí no acredita rendimiento general ni cierra la tarjeta de siete experimentos.
