from datetime import date
from pathlib import Path

import pytest

from cabpres import bc3, calculo, proyecto
from cabpres.modelo import CAPITULO, MANO_OBRA, RAIZ, LineaMedicion, Medicion

EJEMPLO = Path(__file__).parent / "datos" / "ejemplo.bc3"


def linea(obra, padre, hijo):
    return next(d for d in obra.concepto(padre).hijos if d.codigo == hijo)


@pytest.fixture
def obra():
    return bc3.leer(EJEMPLO)[0]


def test_lectura_estructura(obra):
    assert obra.raiz == "EJ"
    assert obra.concepto("EJ").naturaleza == RAIZ
    assert obra.concepto("01").naturaleza == CAPITULO
    assert obra.concepto("MO01").naturaleza == MANO_OBRA
    assert obra.concepto("MO01").precio == 18.5
    assert obra.concepto("E01").texto.startswith("Excavación en zanja")
    assert obra.parametros.gastos_generales == 13
    assert obra.parametros.iva == 21


def test_mediciones(obra):
    med = linea(obra, "01", "E01").medicion
    assert len(med.lineas) == 2
    assert med.total() == pytest.approx(2 * 20 * 0.6 * 1.5 + 4 * 10 * 0.5 * 1.2)  # 60
    assert linea(obra, "02", "E02").medicion.total() == pytest.approx(33.75 + 2.75)


def test_precios(obra):
    # E01 = 0.1 * 18.50 + 0.05 * 45 = 1.85 + 2.25
    assert calculo.precio(obra, "E01") == pytest.approx(4.10)
    # E02 = 0.8 * 18.50 + 1.05 * 78.20 = 14.80 + 82.11
    assert calculo.precio(obra, "E02") == pytest.approx(96.91)
    # capítulo 01 = 60 m3 * 4.10
    assert calculo.precio(obra, "01") == pytest.approx(246.0)
    assert calculo.precio(obra, "02") == pytest.approx(3537.22)  # 3537.215 redondeado hacia arriba
    assert calculo.precio(obra, "EJ") == pytest.approx(246.0 + 3537.22)


def test_resumen(obra):
    r = calculo.resumen(obra, 1000)
    assert (r.gastos_generales, r.beneficio_industrial, r.base, r.iva, r.total) == (130, 60, 1190, 249.9, 1439.9)


def test_certificaciones(obra):
    obra.nueva_certificacion(date(2026, 9, 30))
    obra.nueva_certificacion(date(2026, 10, 31))
    linea(obra, "01", "E01").certificado[1] = Medicion([LineaMedicion("Zanja A", 2, 20, 0.6, 1.5)])  # 36
    linea(obra, "01", "E01").certificado[2] = Medicion(total_directo=24)
    linea(obra, "02", "E02").certificado[2] = Medicion(total_directo=10)

    e01 = calculo.certificado(obra, "01", 0, 2)
    assert (e01.anterior, e01.actual, e01.origen) == (36, 24, 60)
    assert e01.importe_anterior == pytest.approx(147.6)
    assert e01.importe_actual == pytest.approx(98.4)

    cap = calculo.certificado(obra, "EJ", 0, 2)
    assert cap.importe_origen == pytest.approx(246.0)

    total = calculo.certificado_obra(obra, 2)
    assert total.importe_actual == pytest.approx(98.4 + 969.1)
    assert calculo.medicion_pendiente(obra, "01", 0, 2) == pytest.approx(24)


def test_ida_y_vuelta_bc3(obra, tmp_path):
    ruta = tmp_path / "salida.bc3"
    bc3.escribir(obra, ruta)
    otra, cabecera = bc3.leer(ruta)
    assert cabecera["programa"] == "CABPRES"
    assert set(otra.conceptos) == set(obra.conceptos)
    assert calculo.precio(otra, "EJ") == pytest.approx(calculo.precio(obra, "EJ"))
    assert linea(otra, "01", "E01").medicion.total() == pytest.approx(60)
    assert otra.parametros.iva == 21 and otra.parametros.gastos_generales == 13
    assert "camión" in otra.concepto("E01").texto


def test_exportar_e_importar_certificacion(obra, tmp_path):
    obra.nueva_certificacion(date(2026, 9, 30))
    obra.nueva_certificacion(date(2026, 10, 31))
    linea(obra, "01", "E01").certificado[1] = Medicion(total_directo=36)
    linea(obra, "01", "E01").certificado[2] = Medicion(total_directo=24)
    ruta = tmp_path / "cert2.bc3"
    bc3.escribir(obra, ruta, certificacion=2)

    _, cabecera = bc3.leer(ruta)
    assert cabecera["tipo_informacion"] == "3"
    assert cabecera["numero_certificacion"] == 2
    assert cabecera["fecha_certificacion"] == date(2026, 10, 31)

    # Importar en una obra que solo tiene la certificación 1
    obra.borrar_certificacion(2)
    cert = bc3.importar_certificacion(obra, ruta)
    assert cert.numero == 2
    assert linea(obra, "01", "E01").certificado[2].total() == pytest.approx(24)  # 60 a origen - 36


def test_proyecto(obra, tmp_path):
    obra.nueva_certificacion(date(2026, 9, 30))
    linea(obra, "01", "E01").certificado[1] = Medicion(total_directo=5)
    ruta = tmp_path / "obra.obra"
    proyecto.guardar(obra, ruta)
    otra = proyecto.abrir(ruta)
    assert calculo.precio(otra, "EJ") == pytest.approx(calculo.precio(obra, "EJ"))
    assert otra.certificaciones[0].fecha == date(2026, 9, 30)
    assert calculo.certificado_obra(otra, 1).importe_actual == pytest.approx(20.5)


def test_quitar_hijo_purga(obra):
    obra.quitar_hijo("EJ", 1)  # capítulo 02
    assert "02" not in obra.conceptos and "E02" not in obra.conceptos and "MT01" not in obra.conceptos
    assert "MO01" in obra.conceptos  # sigue usado por E01


def test_renombrar(obra):
    obra.nueva_certificacion(date(2026, 9, 30))
    linea(obra, "01", "E01").certificado[1] = Medicion(total_directo=5)
    obra.renombrar("E01", "EXC")
    assert linea(obra, "01", "EXC").certificado[1].total() == 5
    assert calculo.precio(obra, "EXC") == pytest.approx(4.10)
    with pytest.raises(ValueError):
        obra.renombrar("EXC", "E02")


def test_informes(obra):
    from cabpres import informes
    obra.nueva_certificacion(date(2026, 9, 30))
    linea(obra, "01", "E01").certificado[1] = Medicion(total_directo=60)
    html = informes.certificacion(obra, 1)
    assert "Certificación n.º 1" in html and "246,00" in html
    assert "3.783,22" in informes.presupuesto(obra)


# Casos reales encontrados en un BC3 de Arquímedes (CYPE)
ARQUIMEDES = """~V|CYPE INGENIEROS, S.A.|FIEBDC-3/2004|ARQUIMEDES||ANSI|Presupuesto|2|
~K|2\\2\\2\\3\\2\\2\\2\\2\\2\\|0\\13\\6\\\\7|\\2\\\\\\3\\\\2\\2\\2\\2\\2\\2\\2\\||
~C|OB##||Obra|0|250304|0|
~C|CAP#||Capitulo|0|250304|0|
~C|A01|m3|Mortero|86.04|100321|0|
~C|MO|h|Peon|16.5|100321|1|
~C|T1|t|Cemento|26.5|100321|3|
~C|%0.03CI|%|Costes indirectos|0|280121|4|
~D|OB##
|CAP#\\1\\1
\\|
~D|CAP#
|A01\\\\54
\\A01\\\\2
\\|
~D|A01
|MO\\\\4.5
\\T1\\\\0.35
\\%0.03CI\\\\0.03
\\|
~M|CAP#\\A01|1\\1\\|54|
\\PLANTA +0\\25\\\\\\\\
\\PLANTA +1\\29\\\\\\\\|
~M|CAP#\\A01|1\\2\\|2|
\\PLANTA BAJA\\2\\\\\\\\|
"""


@pytest.fixture
def arquimedes():
    return bc3.parsear(ARQUIMEDES.replace("\n", "\r\n").encode("cp1252"))


def test_k_con_subcampos(arquimedes):
    obra, _ = arquimedes
    p = obra.parametros
    assert (p.gastos_generales, p.beneficio_industrial, p.iva, p.divisa) == (13, 6, 7, "EUR")
    assert p.decimales_medicion == 2


def test_porcentajes(arquimedes):
    obra, _ = arquimedes
    assert obra.concepto("%0.03CI").es_porcentaje
    # 4.5 * 16.5 = 74.25 ; 0.35 * 26.5 = 9.275 -> 9.28 ; base 83.53 ; 3 % = 2.5059 -> 2.51
    assert calculo.precio(obra, "A01") == pytest.approx(86.04)
    assert calculo.lineas(obra, "A01")[2] == (pytest.approx(83.53), pytest.approx(2.51))


def test_partida_repetida_en_capitulo(arquimedes):
    obra, _ = arquimedes
    a, b = obra.concepto("CAP").hijos
    assert a.medicion.total() == 54 and b.medicion.total() == 2
    assert calculo.precio(obra, "CAP") == pytest.approx(56 * 86.04)


def test_precio_de_contrato_se_conserva(tmp_path):
    texto = ARQUIMEDES.replace("|A01|m3|Mortero|86.04|", "|A01|m3|Mortero|86.05|")
    obra, cabecera = bc3.parsear(texto.replace("\n", "\r\n").encode("cp1252"))
    assert cabecera["precios_fijados"] == 1
    assert calculo.precio(obra, "A01") == 86.05
    otra = proyecto.desde_dict(proyecto.a_dict(obra))
    assert calculo.precio(otra, "A01") == 86.05


def test_capitulo_descuadrado_en_fichero(arquimedes):
    obra, cabecera = arquimedes
    assert cabecera["capitulos_descuadrados"] == []
    texto = ARQUIMEDES.replace("|CAP#||Capitulo|0|", "|CAP#||Capitulo|9999|")
    _, cabecera = bc3.parsear(texto.replace("\n", "\r\n").encode("cp1252"))
    assert [c for c, *_ in cabecera["capitulos_descuadrados"]] == ["CAP"]


def test_certificar_partida_repetida(arquimedes, tmp_path):
    obra, _ = arquimedes
    obra.nueva_certificacion(date(2026, 9, 30))
    obra.concepto("CAP").hijos[1].certificado[1] = Medicion(total_directo=2)
    assert calculo.certificado(obra, "CAP", 0, 1).actual == 0
    assert calculo.certificado(obra, "CAP", 1, 1).actual == 2
    # ida y vuelta por BC3 de certificación sin mezclar las dos apariciones
    ruta = tmp_path / "c1.bc3"
    bc3.escribir(obra, ruta, certificacion=1)
    obra.borrar_certificacion(1)
    bc3.importar_certificacion(obra, ruta)
    assert 1 not in obra.concepto("CAP").hijos[0].certificado
    assert obra.concepto("CAP").hijos[1].certificado[1].total() == 2


def test_redondeo_sin_error_binario():
    assert calculo.redondear(26.5 * 0.35, 2) == 9.28
    assert calculo.redondear(2.675, 2) == 2.68


def test_migracion_obra_v1():
    datos = {"version": 1, "raiz": "R", "conceptos": [
        {"codigo": "R", "naturaleza": "raiz", "hijos": [{"codigo": "C", "factor": 1, "rendimiento": 1}]},
        {"codigo": "C", "naturaleza": "capitulo", "hijos": [{"codigo": "P", "factor": 1, "rendimiento": 3}]},
        {"codigo": "P", "precio": 10.0}],
        "mediciones": [{"padre": "C", "hijo": "P", "lineas": [], "total_directo": 4}],
        "certificaciones": [{"numero": 1, "fecha": "2026-09-30", "mediciones": [
            {"padre": "C", "hijo": "P", "lineas": [], "total_directo": 1.5}]}]}
    obra = proyecto.desde_dict(datos)
    assert calculo.precio(obra, "R") == 40
    assert calculo.certificado_obra(obra, 1).importe_actual == 15
