# Plan operativo de cierre · 02/11/2026

> Historical planning status. The completed scope and limitations of the MVP as of 24 November 2026 are described in the [README](../README.md) and [evaluation closeout](experiments/mvp-final-results.md).

Encargo de Pau: comenzar la comprobación integrada y preparación del cierre; incluir mejoras de frontend/usabilidad, experimentos, memoria, metodología y defensa. **Los datos reales son opcionales y no bloquean**. Por defecto se trabaja con sintéticos identificados como tales. Encontrar datos reales no los convierte automáticamente en una muestra suficiente para todos los EXP.

Este es un plan de trabajo derivado de la conversación; no sustituye estados oficiales de Notion. Fuente histórica: exportación del backlog indicada por Pau. No se ha editado Notion. Las PR #19–27 están integradas en `main` `823a4bb`; la evidencia técnica actual se registra en [comprobación integrada](verification/integrated-2026-11-02.md).

La deuda de implementación y las revisiones de robustez se centralizan en el [registro técnico](technical-debt.md), separado de validación académica y alcance futuro.

## Orden y condiciones

| Orden | Acción | Necesitamos | Condición para avanzar |
| --- | --- | --- | --- |
| 1 · ahora | Comprobar `main`: backend/BI, build, API/AAS, navegador y dashboard | Entorno desechable, commit e imágenes identificados | Evidencia fechada y fallos visibles; no confundir test verde con recorrido completo disponible en UI |
| 2 · siguiente | Resolver bloqueos de tareas y acordar diseño frontend | [Backlog observado](frontend-usability-backlog.md), tareas de consulta/revisión, feedback Pau/Alexander | Abrir certificado, revisar, revalidar y materializar correctamente sin recurrir a Swagger; estados inequívocos |
| 3 · en paralelo | Preparar dataset y baseline sintéticos de evaluación | [Matriz de preparación](experiments/final-execution-readiness.md), catálogo, ground truth y manifiestos | Separación desarrollo/piloto/evaluación; equivalencia de carpeta/tabla y UI; sin reutilizar pruebas conocidas como test independiente |
| 4 · antes de congelar | Contrastar los siete EXP y preparar el guion final | Objetivos TFM, baselines/métricas/criterios por EXP, limitaciones actuales | Decisiones documentadas antes de ver nuevos resultados; informes anteriores intactos |
| 5 | Mejoras visuales/usabilidad y piloto separado | Bloqueos funcionales resueltos, prototipo visual, escritorio/móvil, guion y personas si están disponibles | Interfaz estable para las tareas; registrar fallos del piloto y excluirlo de la muestra final |
| 6 | Congelar versión/datos/protocolo | Commit limpio, hashes de artefactos, reloj, semillas, versiones, clave revisada | Congelación anterior a ejecución final; cambios posteriores generan nueva versión y desviación explícita |
| 7 | Ejecutar EXP-01…07 | Entornos aislados e informes nuevos; participantes para estudio humano EXP-07 | Contabilizar todas las muestras, errores, abstenciones y pares incompletos; revisión de resultados |
| 8 | Cerrar objetivos, memoria y defensa | Evidencia final y rúbrica/plantilla/fechas oficiales | Cada conclusión vinculada a una evidencia; demo ensayada y alternativa grabada |

Los pasos 3 y 4 son preparación ahora; **no se congela todavía la versión UI del estudio**. El piloto puede obligar a mejorar interfaz o protocolo. Tampoco se ejecuta un estudio humano ficticio: sin participantes, EXP-07 solo puede aportar un recorrido técnico, declarado como tal.

## Trabajo paralelo desde ahora

- Memoria: contexto/objetivos, requisitos, arquitectura, implementación y método pueden redactarse antes del ensayo. Resultados y discusión se completan después. No esperar al final para reconstruir el proceso.
- Metodología: reconstruir decisiones, reparto humano–IA, revisiones, pruebas, errores y cambios de alcance con [el índice de evidencia](thesis/methodology-evidence-index.md). Las conversaciones son contexto; Git, PR e informes demuestran hechos concretos.
- Defensa: preparar narrativa de problema → caso → solución → evidencia → límites. Usar un caso sintético rotulado si no hay real; no presentarlo como validación industrial.
- Casos reales: búsqueda opcional y acotada, sin dependencia crítica. Si aparecen, comprobar procedencia, campos disponibles y adecuación; separarlos de los sintéticos en los informes.

## Información externa que hará falta

No impide comenzar los pasos 1–4: fecha de entrega/defensa, duración de presentación, plantilla/rúbrica, material de memoria existente, preferencias visuales y disponibilidad de participantes. No inventar estos datos ni comprometer un calendario antes de conocerlos.

## Próxima entrega funcional recomendada

Una PR acotada para cerrar consulta de documentos originales y transición validación → materialización, con sus estados y evidencias. Separar la ampliación de etiquetas del extractor (`Serial Number:`) de la renovación visual general para revisar y medir sus efectos. El aspecto visual definitivo debe revisarse con Pau/Alexander antes de congelar EXP-07.
