# Evaluación de aceptación sintética — 2026-10-27

El protocolo y el script se fijaron en `cd0610a` **antes** de ejecutar la evaluación.
Reproducir desde la raíz con dependencias backend:

```sh
python experiments/acceptance/evaluate.py --output experiments/acceptance/results.json
```

No se ajustaron el método ni los umbrales según estos resultados. Semilla,
protocolo, código y hash del dataset figuran en el JSON. Las observaciones futuras
no se pasan al servicio; tres horizontes por instrumento están correlacionados.
Las métricas son descriptivas, no intervalos de confianza sobre datos industriales.

## Resultado del riesgo

1.080 trayectorias sintéticas, tres familias, historiales de 8/16 calibraciones,
3.240 pronósticos y seis escenarios. No hay probabilidades fuera de [0,1].

| Escenario | Brier modelo | Brier persistencia de estado | Cobertura nominal 95 % |
| --- | ---: | ---: | ---: |
| Estable | 0.0752 | 0.1278 | 92.78 % |
| Lineal | 0.0499 | 0.0741 | 92.59 % |
| Curvatura | 0.0790 | 0.0981 | 51.85 % |
| Cambio brusco | 0.2604 | 0.2870 | 2.41 % |
| Colas pesadas | 0.0675 | 0.1111 | 91.85 % |
| Reinicio por mantenimiento | 0.3187 | 0.3056 | 20.93 % |

En estable+lineal: Brier **0.06256**, frente a **0.10093** de persistencia de estado
y **0.07308** de persistencia gaussiana; ECE de diez bins **0.02652**, cobertura
**92.69 %**. Cumple los umbrales sintéticos prefijados. No demuestra calibración
industrial; la cobertura es inferior al 95 % nominal.

**Conclusión:** aceptable como estimador experimental bajo las hipótesis lineales,
no como predictor general del ciclo de vida. Los cambios de régimen rompen las
hipótesis. Es necesario reestablecer historial tras mantenimiento conocido y no
presentar cambios futuros desconocidos como predecibles. M2 no se introduce solo
para mejorar este conjunto: requeriría desarrollo y otro test independiente.

La política de rebaseline tras mantenimiento se implementa en una rama funcional
separada. Este informe evalúa el núcleo OLS v1 sin ese contexto; no se reetiquetan
retroactivamente los resultados para ocultar fallos.

## Health Score metrológico v1

294 comprobaciones de rango, reconstrucción, monotonicidad en error estable y
sensibilidad a tres conjuntos de pesos: correctas, diferencia máxima 5 puntos en
estos escenarios. No demuestra pesos óptimos ni incorpora los componentes que
faltan del backlog. El equipo confirmó que se completará el alcance original:
calibración, riesgo previsto, incidencias recientes y calidad de datos.

## Matriz de cierre de las tres tarjetas

| Tarjeta | Evidencia disponible | Condición pendiente |
| --- | --- | --- |
| Riesgo 30/60/90 | Implementación, tests y evaluación temporal sintética con límites explícitos | Revisar política postmantenimiento y aceptar el alcance experimental |
| Health Score | v1 explicado/configurable y comprobado | Completar v2 de cuatro componentes y su aceptación |
| Dashboard | SQL operativo y comprobaciones Metabase; PR #13 añade snapshots | Integrar #13, conectar v2 y comprobar filtros, ranking, ausencia y caducidad |

No cambiar a Done solo por este informe. El cierre requiere los cambios funcionales,
PR revisadas/integradas y aceptación documentada del equipo. La instalación compartida
no existe todavía: las pruebas reproducibles locales no se describen como despliegue.
