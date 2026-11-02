# Revisión de documentos con varias series — 02/11/2026

## Problema y comportamiento corregido

La preparación de EXP-02 detectó dos PDFs con dos series canónicas distintas. El extractor tomaba la primera y el matching exacto vinculaba el documento sin revisión; cambiar el orden de las líneas cambiaba el activo elegido.

Ahora se recogen todas las series distintas que reconocen los patrones de texto existentes (`Serial`, `S/N`, `Número de Serie`). Una única serie, aunque aparezca repetida, sigue el flujo habitual. Si hay varias:

1. `serial_number` queda vacío, sin candidata preseleccionada.
2. `serial_candidates` conserva la lista ordenada en JSON en staging, como evidencia de solo lectura. El PDF RAW/hash y el texto extraído se conservan por el flujo existente.
3. Matching devuelve ningún activo y R-ID-AMBIGUOUS; el documento queda REVIEW_REQUIRED. Reprocesar descarta un vínculo anterior antes de decidir otra vez.
4. La UI muestra las series detectadas y permite elegir una en «Serie para vincular», guardar y volver a validar. La selección debe pertenecer a las candidatas y corresponder a un activo canónico; elegir una desconocida no permite vincularlo.
5. Guardar una corrección deja el documento pendiente de revalidación. Cambiar la serie elimina el vínculo anterior. No basta con guardar para materializar información canónica.

La lista de candidatas y el texto original no se pueden alterar mediante PATCH. La corrección humana modifica solo el valor normalizado y se conserva en la auditoría existente. Una revalidación exitosa puede establecer el vínculo; este cambio no ejecuta la aceptación canónica ni la sincronización AAS por el usuario.

## LLM y evidencia

El modo híbrido no puede elegir automáticamente entre varias series detectadas en el texto: se conserva la evidencia determinista y se deja la selección vacía, aunque el LLM devuelva una candidata. Si el LLM contradice una única serie determinista, también se exige revisión de ambas propuestas. Una respuesta de identidad con tipo inválido no reemplaza una serie determinista válida.

No se presenta esto como detección universal de ambigüedades: utiliza los patrones de texto que admite el extractor actual. No incorpora OCR de imágenes, resolución semántica de todas las referencias ni soporte automático de certificados multiinstrumento.

## Contrato y compatibilidad

- Sin migraciones, tablas nuevas, dependencias ni cambios de modelos analíticos.
- Nuevo campo de staging `serial_candidates`: cadena JSON; `GET /documents/{id}/fields` añade `read_only` y mantiene las propiedades anteriores.
- `serial_number` sigue siendo el campo corregible. Una selección ajena a las candidatas, metadatos corruptos o candidatas inconsistentes mantienen el documento en revisión sin vínculo.
- La API normal conserva su reloj habitual. El cambio es compatible con la inyección de fecha de la PR #20.
- Los documentos existentes no se reprocesan en bloque. Un documento histórico con identidad dudosa necesita revisión/reprocesamiento explícitos. No se trasladan ni revierten calibraciones ya materializadas.
- El estado persistido de validación de campos de staging mantiene el comportamiento previo; esta entrega no resuelve la discrepancia visual histórica entre ese estado y la validación global del documento.

## Evidencia y coordinación

[Regresión registrada](../../experiments/results/document_identity_regression.json), sobre los **mismos 28 casos, etiquetas y bytes PDF** de la PR #23:

| Resultado | Antes | Después |
| --- | ---: | ---: |
| Decisiones vínculo/abstención correctas | 26/28 | 28/28 |
| Vínculos asignados incorrectamente | 2 | 0 |
| Revisiones de identidad omitidas | 2 | 0 |
| Abstenciones correctas | 7 | 9 |

Las dos series del PDF ambiguo quedan sin seleccionar y sin vínculo, con revisión requerida, independientemente de su orden. Los 19 casos con destino esperado mantienen vínculos correctos. El baseline exacto comparte el preprocesamiento: este resultado no demuestra superioridad de un algoritmo nuevo.

Esto es **regresión conocida utilizada para desarrollar la corrección**, no validación final independiente ni un resultado industrial. Hace falta otra muestra para el test final.

Comprobaciones realizadas:

- 177 tests backend+BI correctos en Docker/Python 3.11/PostgreSQL 17 desechable sobre la rama de corrección.
- Composición local de PR #19–23 y esta corrección, sin conflictos tras ajustar la ubicación de una importación: **253 tests correctos**. La composición queda reproducible en la rama de prueba `test/ambiguity-pending-prs`; no fusiona ninguna PR en main ni sustituye su revisión.
- Build frontend correcto. Chromium sobre API/PostgreSQL reales: sin serie preseleccionada, evidencia sin controles de edición, selección PT-B, guardar/revalidar y documento ACCEPTED vinculado al activo correcto. Escritorio 1280 px y móvil 390 px sin desbordamiento horizontal ni errores JavaScript.
- Tests HTTP de impedir edición de evidencia, aceptar antes de revalidar, selección externa a candidatas y vínculo obsoleto tras corrección/reproceso. Guardas de LLM y metadatos inválidos.
- Persisten los avisos anteriores Requests/Starlette, sin fallos. No se tocó el entorno local de Pau ni se ejecutó AAS.

Al ampliar el dataset de EXP-03 habrá que incluir la nueva regla de identidad en su alcance/anotaciones. Los informes previos siguen siendo evidencia histórica con sus versiones, sin sobrescribirlos ni recalificarlos como un test independiente.
