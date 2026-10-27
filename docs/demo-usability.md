# Mejoras de uso y preparación del ensayo

## Dos comandos desde la raíz

Requisitos: Python 3.10+ y Docker con Compose v2 (`up --wait`). No hacen falta
dependencias Python locales para el lanzador; los módulos del proyecto se ejecutan
en contenedores. En Windows también funciona desde PowerShell.

```sh
python tools/dev.py start
python tools/dev.py demo
```

`start` crea `.env` desde el ejemplo solo si no existe, espera a PostgreSQL,
asegura que exista la base interna de Metabase e inicia backend, frontend,
BaSyx y Metabase. No sobrescribe configuración, borra volúmenes ni hace despliegues.
Los servicios pueden necesitar unos segundos adicionales: comprobar `docker compose ps`.

`demo` aplica la migración/vistas de BI en una transacción y añade cuatro
instrumentos identificados con prefijo `PTWIN-DEMO-`. No elimina registros y no
reinicia los casos ya existentes; conserva correcciones hechas por el equipo.
Cada ejecución refresca sus snapshots y conserva el historial de cálculos.

| Serie | Caso preparado |
| --- | --- |
| PTWIN-DEMO-SANO | Calibración e información sin alertas |
| PTWIN-DEMO-VENCIDO | Última calibración vencida |
| PTWIN-DEMO-REVISION | Documento vinculado con serie pendiente de corregir |
| PTWIN-DEMO-SIN-HISTORIAL | Sin calibraciones, score y riesgo no calculables |

Se generan PDFs y campos sintéticos etiquetados para navegar y practicar revisión.
**No es evidencia de ingesta automática ni sincronización AAS**. La carga desde
cero y proyección al servidor se ensayan aparte. Un nuevo día no mueve las fechas
de fixtures existentes: si cambian sus estados por el paso del tiempo, es visible.
No usar este comando para resetear un ensayo ya corregido.

## URLs y navegación

Valores locales por defecto: aplicación `http://localhost:5173`, API en
`http://localhost:8000`, Metabase en `http://localhost:3003`.

- Inicio: buscar por serie o ubicación y abrir ficha sin conocer IDs.
- Ficha: abrir documento vinculado directamente en revisión y consultar auditoría
  del instrumento. Los parámetros precargan y consultan el registro correcto.
- Metabase: las tablas de prioridades y riesgo incluyen «Abrir pasaporte».
  Al aprovisionarlas, `PASSPORT_FRONTEND_BASE_URL` define el origen del enlace.
  Si se ejecuta el aprovisionador fuera de Docker, exportar esa variable en el
  entorno del comando o pasar `--passport-base-url http://localhost:5173`;
  el aprovisionador no lee automáticamente el `.env` del proyecto.
- Para volver de la ficha al dashboard instalado, configurar
  `VITE_METABASE_DASHBOARD_URL` con su URL real y recrear/recompilar frontend.
  Vacío oculta ese enlace; no se presupone un ID fijo.

El arranque no crea un administrador ni adivina credenciales de Metabase. Conectar
la base de aplicación y seleccionar colección según `bi/README.md`, y luego ejecutar
el aprovisionamiento. Los dashboards anteriores no se modifican automáticamente;
se crea una copia con los enlaces y las unidades nuevos.

Desde móvil, localhost apunta al móvil: configurar las URLs con la IP LAN del
ordenador y permitir los puertos. El QR mantiene la identidad pública estable.

## Fechas y significado

- «Último cálculo en esta consulta»: resultado vivo, hora del navegador.
- «Datos de calibración hasta»: fecha máxima de las calibraciones disponibles,
  no una promesa de actualización de todos los documentos o eventos.
- «Último resultado guardado»: snapshot de BI y su estado de vigencia.

Consultar no refresca snapshots. Si faltan o están desactualizados, ejecutar el
refresco explícito antes del ensayo. El manifiesto se comparte entre la creación
y la consulta de vigencia para evitar reglas distintas. No cambian los modelos.

## Estados, acciones y unidades

La ficha y revisión muestran estados legibles, como «En servicio», «Pendiente»,
«Requiere revisión» o «Conforme». Los códigos originales se conservan en la API.
Ante datos insuficientes se indica la acción: completar vencimiento, corregir
duplicados, registrar calibraciones posteriores al mantenimiento, revisar severidad
o completar identidad/documentación. Las recomendaciones no se ejecutan solas.

La unidad procede de `instrument_type.unit`, se muestra en historial, previsión y
tolerancia, y se incluye en las tablas de Metabase. Si falta, la ficha lo declara;
no convierte ni inventa unidades. El ratio error/tolerancia continúa siendo adimensional.

## Antes del ensayo

1. Actualizar código e iniciar servicios con el primer comando.
2. Preparar los cuatro casos con el segundo y guardar las URLs impresas.
3. Instalar la copia de dashboard, configurar su enlace y recrear frontend.
4. Buscar los casos desde inicio, abrir un documento y auditoría y volver a la ficha.
5. Comprobar unidades, fechas y estados; practicar la corrección del caso de revisión.
6. Refrescar snapshots tras cambios para observar la actualización en Metabase.

Estos pasos preparan el ensayo; no declaran la demo completa ni los experimentos
finales realizados. El entorno compartido sigue siendo una actividad separada.

## Evidencia de esta entrega — 27/10/2026

- 164 tests backend+BI correctos en Docker/Python 3.11/PostgreSQL 17; sin cambios
  en las fórmulas de score/riesgo ni en la política de vigencia.
- Build frontend y `docker compose config --quiet` correctos. Secuencia del
  lanzador y parada ante error de migración comprobadas sin tocar servicios existentes.
- Seeder ejecutado dos veces sobre base desechable; mismas identidades, sin
  duplicar calibraciones/documentos. Prueba adicional conserva correcciones manuales
  y comprueba coexistencia con otras muestras, con PDFs identificados de forma única.
- Metabase v0.64.3.4: 50 consultas sobre diez tarjetas con enlaces configurados y
  unidades; consultas finales con estados/criticidad traducidos ejecutadas en PostgreSQL.
- Chromium: búsqueda, fechas vivas/guardadas, estados españoles, unidades, enlaces
  directos a revisión/auditoría y regreso, acciones ante historial insuficiente,
  dashboard configurado y móvil 390px. Sin errores JavaScript.
- No se arrancó el Compose completo contra la base compartida ni se desplegó en
  un dominio. Los comandos se entregan para el entorno local y el ensayo posterior.
