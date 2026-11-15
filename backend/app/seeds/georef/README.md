# Georef: provincias, departamentos y localidades de Argentina

Datos de referencia geográficos de **todo el país**, del dataset oficial Georef (Datos Argentina, datos.gob.ar).
Licencia de los datos: Creative Commons Attribution 4.0.

| Archivo | Qué es |
|---|---|
| `provincias.csv`, `departamentos.csv`, `localidades.csv` | El dataset, normalizado. **Los genera `make georef`; no se editan a mano.** |
| `FUENTE.json` | URLs de origen, fecha de descarga, cantidad de filas y sha256 de cada CSV |
| `cargar.sql` | Carga idempotente en `app.geo_areas` (clave: código oficial). La ejecuta `seed-base` |

## Estado

**Los CSV todavía no están en el repo.** La sesión que armó esto no tenía salida a `apis.datos.gob.ar`.
Mientras falten, `seed-base` usa la lista mínima anterior (24 jurisdicciones + departamentos de Mendoza, San Juan y San Luis)
y lo avisa en el log (`georef_dataset_missing`).

## Cómo cargarlo

```bash
make georef                 # descarga y escribe los 3 CSV + FUENTE.json (solo biblioteca estándar de Python)
git add backend/app/seeds/georef && git commit -m "Georef: dataset oficial"
make reset-dev-db           # o: docker compose exec api python -m app.cli seed-base
```

El descargador corta sin escribir nada si la respuesta no tiene la forma esperada o si las cantidades no son plausibles
(24 provincias, 500–600 departamentos, 3.000–20.000 localidades). Las localidades sin departamento conocido se omiten y se
cuentan en `FUENTE.json`: la vista pública arma “Localidad, Provincia” con la cadena localidad → departamento → provincia.

Actualizar el dataset es repetir los mismos pasos: la carga no duplica, actualiza nombre, centroide y padre por código,
conserva los `id` existentes y nunca borra.
