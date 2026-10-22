# Cimiento

Programa de escritorio para presupuestos, mediciones y **certificaciones** de obra.
Lee y escribe FIEBDC-3 (`.bc3`), así que intercambia obras con Presto, Arquímedes, TCQ, etc.

## Funciones

- Árbol de presupuesto: capítulos, subcapítulos y partidas con descomposición
  (mano de obra, maquinaria, materiales). Los precios se recalculan solos.
- Mediciones por líneas (uds × longitud × anchura × altura) o por cantidad directa.
- **Certificaciones**: cada certificación guarda lo ejecutado en ese periodo, medido
  por líneas o con una cantidad directa. El árbol muestra la cantidad anterior, la
  actual y la acumulada a origen, sus importes y el % ejecutado, y marca en rojo
  lo que supera el presupuesto.
  - Botones «Certificar todo lo pendiente» y «Copiar líneas de la medición».
  - Informe de certificación con relación valorada y resumen (PEM, GG, BI, baja,
    IVA, líquido de la certificación), exportable a PDF.
  - Exportación e importación de certificaciones en BC3 (tipo de información 3,
    cantidades a origen).
- Archivo de obra propio (`.obra`, JSON) que guarda el presupuesto y todas las certificaciones.

## Uso

```
pip install -r requirements.txt
python -m cimiento [archivo.obra | archivo.bc3]
```

En Windows basta con hacer doble clic en `Cimiento.pyw`. Para generar un `.exe`
ejecuta `construir_exe.bat`.

Atajos: F2 edita la celda, Ctrl+Mayús+N añade un capítulo, Ctrl+Mayús+P añade una
partida, Ctrl+↑/↓ mueve el elemento y Ctrl+I abre el informe de certificación.
En el árbol se editan con doble clic el código, la unidad, el resumen, el precio
(partidas sin descomposición), la cantidad y la cantidad certificada actual
(cuando no hay líneas de medición).

## Tests

```
pip install pytest
python -m pytest
```
