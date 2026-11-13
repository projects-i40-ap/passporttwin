# One-off utility scripts: database seeding, backups, deployment helpers, data migration one-timers.

## `generate_sample_certificates.py`

Genera un certificado de calibración de ejemplo por cada instrumento cargado en
PostgreSQL, con las etiquetas que reconoce el extractor determinista y un QR al
pasaporte digital del activo. Sirve para comprobar el recorrido completo
(revisión documental → validación → incorporación → pasaporte) sin depender de
certificados reales.

```bash
docker compose run --rm -e PYTHONPATH=/app \
  -v "$PWD/generators:/generators" \
  -v "C:\Users\<usuario>\Desktop:/desktop" \
  backend python /generators/generate_sample_certificates.py \
    --output /desktop/PassportTwin-Certificados --out-of-tolerance
```

`--out-of-tolerance` añade en `variantes/` una versión NO CONFORME por instrumento
para demostrar el estado fuera de tolerancia. Los PDFs son documentos de
demostración: no tienen validez metrológica.
