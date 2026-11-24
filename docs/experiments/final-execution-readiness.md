# Preparación del ensayo final · 02/11/2026

> Documento histórico de preparación. Para los resultados y el alcance final acordado, consultar el [cierre de evaluación del MVP](mvp-final-results.md), actualizado el 24/11/2026. Las tareas pendientes descritas abajo corresponden a este checkpoint.

Política confirmada por Pau: **sintéticos como ruta de trabajo; reales si se consiguen, sin bloquear**. Los reales se presentan como una cohorte separada con alcance explícito. Datos reales sin historial suficiente no validan deriva ni probabilidad futura. Esta entrega prepara decisiones y condiciones; no declara un nuevo dataset congelado, nuevos umbrales aprobados ni experimentos finales completados.

La [matriz histórica](final-experiments-matrix.md) es una auditoría previa a PR #20–27. Sus carencias de runners ya tienen herramientas integradas; conservarla como antecedente, no como estado actual de implementación.

| EXP | Disponible en main | Preparación pendiente / necesidad | Salida final |
| --- | --- | --- | --- |
| 01 · extracción | `run_extraction_exp01.py`, métricas por campo | PDFs/anotaciones independientes, varias etiquetas/formatos, campos realmente soportados. Corregir DOC-01 antes de congelar. No sumar unidad/rango al denominador sin etiquetas/capacidad explícitas; declarar límites OCR. | Por campo y agregado, soporte, errores y campos sin evaluar; corpus y código identificados |
| 02 · matching | `run_matching_exp02.py`, abstención ante múltiples series | Catálogo congelado; conocidos/desconocidos/ausentes/ambiguos, expectativas independientes. Baseline exacto comparte lógica: no atribuir mejora inexistente. | Vínculos correctos/incorrectos, revisiones y abstenciones, por escenario |
| 03 · reglas | `run_rules_exp03.py`, reloj explícito y métricas por regla | Casos positivos/negativos por regla, nueva ambigüedad, duplicados y aceptación fuera de tolerancia fuera del alcance actual del runner. Distinguir reglas de process/revalidate de las de upload/accept. | Matriz por regla, soporte, cobertura y fallos de ejecución sin omitir muestras |
| 04 · deriva | `run_drift_exp04.py`, prepare/evaluate y cortes temporales | Muestra sintética independiente y escenarios no lineales; ratificar B1 y horizontes (API 30/60/90, benchmark también 180). | MAE/RMSE por familia/horizonte y agregados normalizados; baselines e hipótesis visibles |
| 05 · riesgo | `run_risk_exp05.py`, manifest y escenarios adversos | Prefijar clasificación, abstenciones y criterios; no ajustar sobre el nuevo test. Preservar malos resultados de curvatura/saltos/resets. | Brier/calibración/clasificación según protocolo, coberturas y abstenciones; sin garantías industriales |
| 06 · AASX | `run_aasx_exp06.py`, dos casos controlados que preservan campos | Aprobar perfil crítico y repetir sobre proyección final. Dos repositorios vacíos; no ampliar la afirmación a binarios PDF, UUID/unidad no proyectados ni certificación IDTA. | Informe de cada frontera, conteos, diferencias y hashes de paquetes |
| 07 · trazabilidad/UI | Protocolo AB/BA, templates vacíos, `analyze_exp07.py` | Resolver UI-01/02/03; variantes A/B equivalentes, baseline manual, clave revisada, piloto separado y participantes. | Éxito/errores/ayudas/tiempos con denominadores y pares excluidos; sin personas, solo prueba técnica |

## Paquete de datos y control de independencia

Preparar tres conjuntos identificados: desarrollo (ya conocido), piloto (para comprobar guion/entorno), evaluación (sin usar para ajustar). Cambiar semilla de un generador idéntico no demuestra diversidad de formato ni independencia de hipótesis: documentar plantillas, mecanismos y límites.

Cada paquete final incluirá manifiesto con ID/version, condición sintético/real, generación/semilla cuando proceda, fecha de referencia, catálogo, anotaciones/clave, particiones temporales, rutas relativas y SHA-256 de bytes. Añadir versiones de herramientas/imágenes y commit limpio antes de ejecutar. El protocolo debe identificar preguntas, métricas, baselines, criterios y tratamiento de errores/abstenciones. Una persona distinta del implementador revisa la clave cuando sea posible; declarar si no se consigue.

No se exige encontrar datos reales para producir estos paquetes. Si aparece material real durante el proceso, valorar incorporación sin contaminar el test ya observado; los nuevos resultados llevan otro ID y su propio alcance.

## Preparación del baseline manual de EXP-07

1. Usar el mismo snapshot canónico para ambas representaciones, con archivos originales accesibles también desde la UI tras UI-01.
2. Crear para A/B carpeta `certificates/`, `instruments.csv` y `audit.csv` con el mismo contenido factual. Preservar hash, fechas y procedencia; actor ausente no se inventa.
3. Preparar por variante dos tareas sobre activos distintos: CERT (certificado vigente) y TRACE (corrección y aceptación). La clave incluye qué evidencia demuestra cada respuesta; resolver empates antes del piloto.
4. Verificar en UI y carpeta que las tareas tienen solución con herramientas equivalentes. Igualar volumen/distractores/historial entre variantes; identificadores/respuestas diferentes reducen recuerdo.
5. Registrar manifest/hash de dataset, baseline, snapshot y clave en el template de sesión. No rellenar participantes ni observaciones hasta tener sesiones reales.

Este baseline se prepara después de cerrar los accesos y estados pendientes, antes de congelar. No sería válido afirmar hoy que CERT está comprobado de extremo a extremo en UI.

## Guion transversal de una corrida final

- Identificar paquete, protocolo y commit; comprobar manifiestos y entorno desechable. Guardar comandos reales y versiones, no credenciales.
- Ejecutar en directorios nuevos. Si falla, conservar informe/logs y diagnosticar antes de repetir con otro ID; no borrar la desviación.
- Reconciliar recuento de inputs, evaluados, fallidos y abstenciones; métricas finales solo cuando se cumplen las condiciones del protocolo.
- Comparar con baseline y criterios previamente fijados; conservar valores negativos. Revisar diferencias entre regresión conocida, control sintético y test independiente.
- Incorporar informe, limitaciones y trazabilidad objetivo→evidencia a memoria/defensa. No cerrar la tarjeta global con solo runners verdes.

Los comandos concretos por EXP están en las guías `exp01-runner.md` a `exp07-traceability-study.md` de esta carpeta. Adaptar nombres de directorio y entorno; no ejecutar sin revisar sus guardas de aislamiento. No se han ejecutado nuevos ensayos finales en esta entrega.

