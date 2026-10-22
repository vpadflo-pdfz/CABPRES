from datetime import date
from pathlib import Path

import pytest

from cabpres import bc3, calculo, proyecto
from cabpres.modelo import CAPITULO, MANO_OBRA, RAIZ, LineaMedicion, Medicion

EJEMPLO = Path(__file__).parent / "datos" / "ejemplo.bc3"


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
    med = obra.mediciones[("01", "E01")]
    assert len(med.lineas) == 2
    assert med.total() == pytest.approx(2 * 20 * 0.6 * 1.5 + 4 * 10 * 0.5 * 1.2)  # 60
    assert obra.mediciones[("02", "E02")].total() == pytest.approx(33.75 + 2.75)


def test_precios(obra):
    # E01 = 0.1 * 18.50 + 0.05 * 45 = 1.85 + 2.25
    assert calculo.precio(obra, "E01") == pytest.approx(4.10)
    # E02 = 0.8 * 18.50 + 1.05 * 78.20 = 14.80 + 82.11
    assert calculo.precio(obra, "E02") == pytest.approx(96.91)
    # capítulo 01 = 60 m3 * 4.10
    assert calculo.precio(obra, "01") == pytest.approx(246.0)
    assert calculo.precio(obra, "02") == pytest.approx(round(36.5 * 96.91, 2))
    assert calculo.precio(obra, "EJ") == pytest.approx(246.0 + round(36.5 * 96.91, 2))


def test_resumen(obra):
    r = calculo.resumen(obra, 1000)
    assert (r.gastos_generales, r.beneficio_industrial, r.base, r.iva, r.total) == (130, 60, 1190, 249.9, 1439.9)


def test_certificaciones(obra):
    c1 = obra.nueva_certificacion(date(2026, 9, 30))
    c1.mediciones[("01", "E01")] = Medicion([LineaMedicion("Zanja A", 2, 20, 0.6, 1.5)])  # 36
    c2 = obra.nueva_certificacion(date(2026, 10, 31))
    c2.mediciones[("01", "E01")] = Medicion(total_directo=24)
    c2.mediciones[("02", "E02")] = Medicion(total_directo=10)

    e01 = calculo.certificado(obra, "01", 0, 2)
    assert (e01.anterior, e01.actual, e01.origen) == (36, 24, 60)
    assert e01.importe_anterior == pytest.approx(147.6)
    assert e01.importe_actual == pytest.approx(98.4)

    cap = calculo.certificado(obra, "EJ", 0, 2)
    assert cap.importe_origen == pytest.approx(246.0)

    total = calculo.certificado_obra(obra, 2)
    assert total.importe_actual == pytest.approx(98.4 + 969.1)
    assert calculo.medicion_pendiente(obra, "01", "E01", 2) == pytest.approx(24)


def test_ida_y_vuelta_bc3(obra, tmp_path):
    ruta = tmp_path / "salida.bc3"
    bc3.escribir(obra, ruta)
    otra, cabecera = bc3.leer(ruta)
    assert cabecera["programa"] == "CABPRES"
    assert set(otra.conceptos) == set(obra.conceptos)
    assert calculo.precio(otra, "EJ") == pytest.approx(calculo.precio(obra, "EJ"))
    assert otra.mediciones[("01", "E01")].total() == pytest.approx(60)
    assert "camión" in otra.concepto("E01").texto


def test_exportar_e_importar_certificacion(obra, tmp_path):
    c1 = obra.nueva_certificacion(date(2026, 9, 30))
    c1.mediciones[("01", "E01")] = Medicion(total_directo=36)
    c2 = obra.nueva_certificacion(date(2026, 10, 31))
    c2.mediciones[("01", "E01")] = Medicion(total_directo=24)
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
    assert cert.mediciones[("01", "E01")].total() == pytest.approx(24)  # 60 a origen - 36


def test_proyecto(obra, tmp_path):
    obra.nueva_certificacion(date(2026, 9, 30)).mediciones[("01", "E01")] = Medicion(total_directo=5)
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
    obra.nueva_certificacion(date(2026, 9, 30)).mediciones[("01", "E01")] = Medicion(total_directo=5)
    obra.renombrar("E01", "EXC")
    assert ("01", "EXC") in obra.mediciones
    assert ("01", "EXC") in obra.certificaciones[0].mediciones
    assert calculo.precio(obra, "EXC") == pytest.approx(4.10)
    with pytest.raises(ValueError):
        obra.renombrar("EXC", "E02")


def test_informes(obra):
    from cabpres import informes
    obra.nueva_certificacion(date(2026, 9, 30)).mediciones[("01", "E01")] = Medicion(total_directo=60)
    html = informes.certificacion(obra, 1)
    assert "Certificación n.º 1" in html and "246,00" in html
    assert "3.783,21" in informes.presupuesto(obra)
