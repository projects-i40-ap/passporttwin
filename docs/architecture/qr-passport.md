# QR y ficha de pasaporte

## Recorrido

`QR → API /api/v1/instruments/passport/{public_id} → React /passport/{public_id}`.

El QR mantiene un resolvedor por UUID estable, sin ID de pregunta de Metabase.
Cambiar la vista no requiere reimprimir etiquetas mientras se mantenga la URL
pública del resolvedor. Las etiquetas antiguas que incluyen localhost necesitan
regenerarse para acceso desde otro dispositivo o futuro dominio.

La vista React consulta `/api/v1/instruments/by-public-id/{public_id}` para resolver
el ID interno y usa los endpoints existentes de calibración, score y riesgo. No
modifica documentos ni crea registros. Fallos en analítica no ocultan identidad;
se muestran estados de carga, error y ausencia de datos. El Health Score y el
riesgo siguen separados y etiquetados como indicadores experimentales.

## Desarrollo local

No existe todavía URL compartida, según el equipo. Valores de `.env`:

```dotenv
PUBLIC_API_BASE_URL=http://localhost:8000
PASSPORT_FRONTEND_BASE_URL=http://localhost:5173
VITE_API_BASE_URL=http://localhost:8000
```

Recrear backend/frontend tras cambios. Con Vite dev, las variables se leen al
arrancar; en un build estático VITE_API_BASE_URL se incorpora durante el build.
Abrir `http://localhost:5173/passport/<public_id>` en el mismo ordenador.

Para probar con móvil en la misma red, sustituir localhost en las tres URLs por
la IP LAN del ordenador, publicar puertos y permitir acceso en el firewall local.
localhost en un móvil apunta al móvil, no al servidor. CORS incorpora el origen
configurado en PASSPORT_FRONTEND_BASE_URL, además de los orígenes locales existentes.

## Despliegue futuro

Configurar URLs HTTP/HTTPS accesibles desde el navegador; no nombres internos de
Docker. En producción usar HTTPS. Las bases no admiten credenciales, query ni
fragmento. El proxy/hosting del frontend debe servir index.html al abrir o recargar
`/passport/*` (fallback SPA). No se ha desplegado en un dominio compartido.

No se añade autenticación ni se publica el sistema en Internet con este cambio.
La política de acceso existente de la API sigue aplicando; un UUID no es un permiso.

## Límites

Primera ficha de lectura: identidad/estado, calibraciones, Health Score y riesgo.
No muestra aún documentos completos, mantenimiento ni historial de auditoría.
Metabase conserva el dashboard de flota. No se altera ningún cálculo analítico.

Por ahora servir el frontend desde la raíz del origen; no se configura un basename
para alojarlo bajo un subdirectorio. La base pública de API puede incluir el prefijo
del proxy siempre que se publique también la ruta `/api/v1` bajo ese prefijo.

## Evidencia técnica 2026-10-26

- 120 pruebas backend correctas en la rama, Docker/Python 3.11 y PostgreSQL 17 aislado.
- Merge temporal con PR #11 (`e06e82d`): sin conflictos, 137 pruebas backend+BI correctas.
- Build de producción Vite correcto con la versión final del frontend.
- Chromium real contra API/React/PostgreSQL desechables: redirección desde el
  resolvedor, ficha por UUID, cuatro calibraciones, score y riesgo, recarga directa,
  ancho móvil 390px sin desbordamiento de página, instrumento inexistente,
  historial vacío y fallo parcial del endpoint de score. Sin errores JavaScript.
- Las pruebas backend verifican URL codificada en QR, redirección configurable,
  404/422 y rechazo de URLs inválidas. No se escaneó físicamente una etiqueta.
- No se hizo despliegue en una URL compartida ni se verificó exposición desde
  un teléfono real. Pendiente de revisión e integración por el equipo.
