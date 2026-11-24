# Cierre de evaluación del MVP

Actualizado el 24/11/2026 a partir de los informes conservados para la memoria. La tarjeta de experimentos se cerró con los siete recorridos y el alcance acordado. No se han repetido esos experimentos al actualizar esta documentación.

## Resultados y conclusiones

| EXP | Evidencia | Interpretación y límite |
| --- | --- | --- |
| 01 | 168/168 coincidencias: 162 valores presentes y seis ausencias esperadas, en 24 PDF sintéticos de tres diseños. | Resultado del extractor determinista sobre el corpus ensayado. No mide OCR ni extracción asistida por LLM de documentos arbitrarios. |
| 02 | 27 casos: 18 vinculaciones y nueve abstenciones correctas; tres series ausentes, tres desconocidas y tres ambiguas. | Se preserva la decisión humana cuando no existe identidad inequívoca. Catálogo sintético de tres instrumentos. |
| 03 | Reglas esperadas en 24 PDF: 21 alertas y tres casos sin alerta. Dos comprobaciones complementarias superadas. | Mismo PDF con otro nombre rechazado con HTTP 409/R-DUP-01; aceptación de error −0,128 bar con tolerancia 0,1 bar registrada como fuera de tolerancia en calibración, instrumento y auditoría. No demuestra exclusión de duplicados bajo concurrencia. |
| 04 | 576 trayectorias; MAE normalizado global M1 0,285 frente a B0/B1 0,329. | A 30 días: 0,198 frente a 0,160. Mejora a 60/90 días, pero no cumple mejora comparativa en todos los horizontes. |
| 05 | Brier pareado 0,108 frente a 0,154 sobre 1.512 predicciones; 216 abstenciones y cobertura de estimación 87,5 %. | Precisión 55,7 %, sensibilidad 49,8 % y F1 0,526 al umbral 0,5. Intervalos nominales del 95 % con cobertura observada 77,7 %: no se presentan probabilidades calibradas para uso industrial. |
| 06 | Dos casos AASX: 129/129 y 43/43 entradas críticas preservadas en cada frontera evaluada. | Perfil controlado entre dos repositorios BaSyx vacíos. El resultado no certifica cualquier implementación AAS/IDTA ni cualquier contenido binario. |
| 07 | CERT y TRACE completadas; tiempos comunicados inferiores a 3 y 5 minutos. | Comprobación práctica del participante, sin cronometraje exacto. Se da por cerrada en ese alcance; no es un estudio comparativo AB/BA ni una demostración estadística de ahorro de tiempo. |

## Procedencia y versiones

Los informes documentales y AASX registran `f0978fbc77dfc346de79eeedd67c2afc094386ec`. En el informe AASX, el commit es un dato aportado por el ejecutor (`caller_supplied_not_verified`), no una verificación independiente del árbol de trabajo. Las pruebas complementarias de EXP-03 registran la misma revisión.

La síntesis pública de los informes automatizados se conserva en [el paquete de resultados](../../experiments/results/mvp-closeout-2026-11-24.json). Incluye métricas seleccionadas sin recalcularlas y el SHA-256 de cada informe fuente local. Es una publicación resumida, no el corpus completo ni una promesa de reproducción a partir de ese JSON. Los originales, corpus y capturas se archivaron para la memoria; no se publican aquí rutas personales, certificados reales ni credenciales.

EXP-04/05 utilizaron una cohorte sintética de tres familias y ocho escenarios, con 24 trayectorias por combinación, ocho observaciones históricas y tres futuras por trayectoria. Los horizontes de una trayectoria están correlacionados. EXP-04 ejecutó métodos numéricos extraídos del código; EXP-05 importó servicios de riesgo. No fueron pruebas de extremo a extremo de la aplicación desplegada.

EXP-07 se sustenta en el registro de tareas y el resultado comunicado por Pau. No se han inventado tiempos exactos, participantes adicionales ni observaciones de un estudio formal.

## Relación con los protocolos anteriores

Los documentos [de preparación](final-execution-readiness.md) y la [matriz histórica](final-experiments-matrix.md) reflejan el estado de planificación del 2 de noviembre y anteriores. Se conservan como antecedentes. El protocolo formal de [EXP-07](exp07-traceability-study.md) tiene un alcance mayor que la comprobación finalmente realizada; ese estudio comparativo sigue siendo una posible evaluación futura.

Los runners y sus guías permanecen disponibles para nuevas evaluaciones. Una nueva ejecución debe registrar su propio commit, datos, fecha, parámetros y desviaciones. No trasladar los resultados de esta cohorte a otros formatos, modelos, versiones o instalaciones sin comprobarlo.

## Qué queda fuera del cierre

La validación con flotas industriales, certificación metrológica, calibración de probabilidades en datos reales, evaluación completa de IA/OCR/RAG, concurrencia, restauración productiva y estudio formal de usabilidad quedan fuera de las conclusiones del MVP. El cierre académico tampoco acredita una patente ni un producto industrial certificado.
