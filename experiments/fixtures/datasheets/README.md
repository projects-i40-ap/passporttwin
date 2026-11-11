# Datasheets sintéticos de demo

Cuatro fichas técnicas públicas de sensores industriales, descargadas el 11/11/2026
para ensayar la ingesta documental. Son documentos reales de fabricante, no datos
sintéticos: sirven como caso de prueba de extracción y de RAG.

| Archivo | Fabricante | Tipo | Páginas |
| --- | --- | --- | --- |
| `wika-s20-pressure-transmitter.pdf` | WIKA | Transmisor de presión S-20 | 18 |
| `wika-t38-temperature-transmitter.pdf` | WIKA | Transmisor de temperatura T38 | 20 |
| `endress-promag-d10-flowmeter.pdf` | Endress+Hauser | Caudalímetro electromagnético Promag D 10 | 92 |
| `endress-picomag-flowmeter.pdf` | Endress+Hauser | Caudalímetro electromagnético Picomag | 4 |

## Origen

- WIKA S-20 — https://www.wika.com/media/Data-sheets/Pressure/Pressure-sensors/ds_pe8161_en_co.pdf
- WIKA T38 — https://www.wika.com/media/Data-sheets/Temperature/Temperature-transmitters/ds_te3801_en_co.pdf
- Endress+Hauser Promag D 10 — https://bdih-download.endress.com/file/aefa5875625bcbdbc95900f48a414d20/TI01603DEN_0324-00.pdf
- Endress+Hauser Picomag — https://portal.endress.com/wa001/dla/5001097/0239/000/01/IN01088DEN_0217.pdf

## Uso

Los cuatro traen capa de texto (`pdfplumber` extrae entre 2.500 y 5.500 caracteres
en las tres primeras páginas), así que no requieren OCR. Son material de
demostración: la propiedad intelectual es de los fabricantes y no deben
redistribuirse fuera del repositorio del TFM.

El Promag D 10, con 92 páginas, es el caso límite: su texto completo no cabe en el
contexto de un modelo local y obliga a trocear antes de extraer o resumir.
