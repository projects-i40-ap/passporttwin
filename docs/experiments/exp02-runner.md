# EXP-02: preparación de evaluación de matching

Entrega independiente de preparación de EXP-02, basada en el matching productivo actual. Usa el extractor real y `validate_document_fields` con consultas SQL reales sobre un catálogo sintético explícito en una base nueva PostgreSQL `*_test`. No cambia el comportamiento de extracción, matching, reglas o UI; no materializa documentos, calibraciones ni AAS.

La definición de ambigüedad y sus etiquetas son una **expectativa de diseño de preparación pendiente de confirmar con el equipo**, no un nuevo criterio final aprobado.

## Datos y referencia

[Protocolo/catálogo/casos](../../experiments/fixtures/exp02-preparation.json): siete instrumentos con series únicas y tres familias. Las expectativas están escritas en el fixture antes de ejecutar el matching, no se deducen de sus respuestas.

- 20 PDFs históricos compartidos con EXP-01/03, con vínculo esperado anotado respecto del catálogo de referencia.
- Ocho controles digitales: serie conocida, desconocida, ausente, vecina no exacta, cambio de mayúsculas, espacios exteriores y dos documentos con dos series canónicas distintas en órdenes opuestos.
- Los controles se renderizan con ReportLab `invariant=1`, sin aleatoriedad, en un directorio temporal retirado al terminar. Sus bytes son regenerables desde el fixture. Los PDFs históricos permanecen intactos.
- El esquema canónico impone unicidad de serie. No se simula un catálogo con duplicados que no podría cargarse en PostgreSQL; la ambigüedad evaluada consiste en **varias identidades dentro de un documento**.

Para los documentos ambiguos se etiqueta `expected_target: null` y revisión requerida, porque el MVP vincula un documento a un solo activo. La política debe ratificarse antes del EXP-02 final; no se implementa aquí un algoritmo nuevo de resolución de ambigüedades.

## Separación entre extracción, vínculo y revisión

El extractor obtiene la serie que el servicio recibe. Se registra `extracted_serial`, el destino devuelto y las reglas fallidas.

- **Matching/revisión de identidad:** ausencia de serie o R-ID-01. Una serie desconocida correctamente transcrita no es un error de extracción, pero no debe dar un vínculo canónico.
- **Revisión documental completa:** cualquier regla fallida, incluidas fechas/unidades. Un vínculo correcto puede convivir con revisión por otro motivo.
- Las reglas temporales usan el reloj UTC actual del servicio; el informe lo declara y fecha la ejecución. La métrica de matching no depende de la fecha, pero la tasa de revisión documental completa sí puede variar. Esta entrega no congela el reloj de las reglas ni depende de la PR #20.

El baseline de referencia es búsqueda exacta en el catálogo. Es la **misma política** que usa el matching actual: no se presenta como competidor independiente ni se afirma mejora frente a él. El informe registra también si ambas salidas coinciden.

## Métricas y fallos

- Exactitud de decisión: vínculo exacto o abstención esperada correctos / casos evaluados.
- Precisión de vínculo: vínculos correctos / vínculos asignados.
- Recall de vínculo: vínculos correctos / casos con destino esperado.
- Falsos vínculos: destino asignado incorrecto o asignación cuando la referencia exige abstenerse. Se informa su fracción respecto de las asignaciones.
- Abstenciones, tasas de revisión de matching y de todas las reglas, revisiones de identidad omitidas y resultados por escenario.
- Denominadores vacíos producen nulos. Un resultado incorrecto queda en el informe, no se elimina.

COMPLETE significa que la corrida evaluó todas las muestras, **no que todas las decisiones sean correctas ni que el MVP supere aceptación**. Un error técnico conserva una fila ERROR y anula métricas finales, separando diagnósticos parciales. Un fallo de preparación produce SETUP_FAILED. No se reutilizan bases con tablas ni se sobrescriben informes.

Se registran versiones, hashes de código, catálogo/etiquetas y PDFs y comprobación de entradas invariables. Si Git no existe en la imagen, el SHA del host queda identificado como declarado/no verificado y el estado del árbol desconocido; los hashes describen el código efectivo. Antes del ensayo final comprobar árbol limpio y correspondencia con el commit.

## Resultado de preparación — 01/11/2026

**Hay un límite funcional visible, no un resultado perfecto de matching.**

| Medida | Resultado |
| --- | --- |
| Casos evaluados / previstos | 28 / 28, cero errores técnicos |
| Decisiones vínculo/abstención correctas | 26 / 28 (92,86 %) |
| Vínculos correctos / asignados | 19 / 21 (90,48 %) |
| Recall sobre los 19 casos con vínculo esperado | 100 % |
| Abstenciones correctas | 7 |
| Vínculos no deseados según las etiquetas de preparación | 2 |
| Revisiones de matching omitidas | 2 |

Los dos documentos con series múltiples reciben el primer serial extraído y se vinculan sin reglas fallidas. Al invertir las líneas cambia el destino. El baseline exacto presenta el mismo comportamiento. Este resultado no justifica afirmar que se resuelve ambigüedad; el recall elevado por sí solo oculta ese problema.

[Informe completo de preparación](../../experiments/results/exp02_runner_preparation.json), con hashes cotejados contra el commit ejecutado y el fixture. No se corrige el producto ni se cambian etiquetas después de ver las métricas.

Verificación técnica: **179 tests backend+BI** correctos en Docker/Python 3.11/PostgreSQL 17 desechable, más 15 tests focales tras desacoplar el test diagnóstico de la implementación actual del extractor. La rama es independiente y no incluye los nuevos tests de las PR pendientes #20/#21/#22. Una corrida contra la base ya usada se rechazó antes de escribir; los PDFs controlados se comprobaron deterministas. Persisten avisos previos Requests/Starlette sin fallos.

## Uso desde PowerShell

Requiere la rama integrada y la imagen `passporttwin-backend:latest` con dependencias (`docker compose build backend` si falta). Desde la raíz, ejecutar cada línea por separado. Crear un entorno dedicado, sin usar la base habitual:

```powershell
docker network create ptwin-exp02
```

```powershell
docker run -d --name ptwin-exp02-db --network ptwin-exp02 -e POSTGRES_DB=ptwin_exp02_test -e POSTGRES_USER=passporttwin -e POSTGRES_PASSWORD=test-only postgres:17
```

Esperar a que esta comprobación indique «accepting connections»:

```powershell
docker exec ptwin-exp02-db pg_isready -U passporttwin -d ptwin_exp02_test
```

```powershell
New-Item -ItemType Directory -Force data/generator/output | Out-Null
```

```powershell
git status --short
```

```powershell
$commitExp02 = git rev-parse HEAD
```

```powershell
docker run --rm --network ptwin-exp02 -v "$($PWD.Path):/repo:ro" -v "$($PWD.Path)/data/generator/output:/runs" -w /tmp -e DATABASE_URL=postgresql://passporttwin:test-only@ptwin-exp02-db:5432/ptwin_exp02_test passporttwin-backend:latest python /repo/experiments/run_matching_exp02.py --code-commit $commitExp02 --output /runs/exp02-preparation-01.json
```

La repetición necesita otra base nueva y otro nombre de informe. No resetear la base habitual. La salida queda en una carpeta ya excluida de Git y no se necesitan credenciales de Metabase.

## Pendiente antes de cerrar EXP-02

Ratificar política y umbrales, ampliar casos/datos independientes y decidir cómo detectar varias identidades en un documento antes de vincularlo. Si se corrige el producto con estos casos, pasan a ser regresiones conocidas y hará falta otro test final independiente. Mantener la distinción entre evaluación del núcleo SQL y recorrido HTTP completo; esta entrega no demuestra aceptación canónica ni seguridad del flujo completo. La tarjeta global de siete experimentos sigue en curso.
