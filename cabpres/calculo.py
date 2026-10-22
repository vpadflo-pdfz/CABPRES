"""Cálculo de precios, importes y certificaciones."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

from .modelo import Medicion, Obra


def redondear(valor: float, decimales: int) -> float:
    # round() de Python redondea al par; en presupuestos se redondea "hacia arriba" desde .5
    from decimal import ROUND_HALF_UP, Decimal
    # round(…, 9) quita el error binario: 26.5 * 0.35 da 9.274999… y debe redondear a 9.28
    return float(Decimal(repr(round(valor, 9))).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP))


def cantidad(obra: Obra, padre: str, indice: int) -> float:
    """Cantidad del hijo `indice` de `padre`: su medición si la tiene, si no el rendimiento."""
    d = obra.conceptos[padre].hijos[indice]
    if d.medicion is not None and not d.medicion.vacia():
        return redondear(d.medicion.total(), obra.parametros.decimales_medicion)
    return d.rendimiento


_cache: dict[str, float] | None = None


@contextmanager
def sin_cambios():
    """Bloque en el que la obra no se modifica: los precios calculados se reutilizan."""
    global _cache
    anterior = _cache
    _cache = {} if anterior is None else anterior
    try:
        yield
    finally:
        _cache = anterior


def precio(obra: Obra, codigo: str, _visitando: frozenset[str] = frozenset()) -> float:
    """Precio unitario del concepto (para capítulos y raíz, su importe total)."""
    c = obra.conceptos.get(codigo)
    if c is None or codigo in _visitando:
        return 0.0
    if not c.hijos or (c.precio_fijo and not c.es_agrupador):
        return c.precio
    if _cache is not None and codigo in _cache:
        return _cache[codigo]
    total = sum(imp for _, imp in lineas(obra, codigo, _visitando))
    resultado = redondear(total, obra.parametros.decimales_precio)
    if _cache is not None:
        _cache[codigo] = resultado
    return resultado


def lineas(obra: Obra, codigo: str, _visitando: frozenset[str] = frozenset()) -> list[tuple[float, float]]:
    """(precio unitario, importe) de cada línea de la descomposición de `codigo`.

    En las líneas de porcentaje el "precio" es la base: la suma de las líneas anteriores.
    """
    c = obra.conceptos[codigo]
    dec = obra.parametros.decimales_importe
    visitando = _visitando | {codigo}
    resultado = []
    total = 0.0
    for i, d in enumerate(c.hijos):
        hijo = obra.conceptos.get(d.codigo)
        if hijo is not None and hijo.es_porcentaje:
            # porcentaje (rendimiento en tanto por uno) sobre la suma de lo anterior
            pu, imp = total, redondear(total * d.factor * d.rendimiento, dec)
        else:
            pu = precio(obra, d.codigo, visitando)
            q = cantidad(obra, codigo, i) if c.es_agrupador else d.factor * d.rendimiento
            imp = redondear(pu * q, dec)
        total += imp
        resultado.append((pu, imp))
    return resultado


def importe(obra: Obra, padre: str, indice: int) -> float:
    d = obra.conceptos[padre].hijos[indice]
    return redondear(precio(obra, d.codigo) * cantidad(obra, padre, indice), obra.parametros.decimales_importe)


# --- certificaciones ---------------------------------------------------------

@dataclass
class Certificado:
    """Cantidades e importes certificados de un nodo respecto a la certificación n."""
    anterior: float = 0.0  # a origen hasta n-1
    actual: float = 0.0  # en la certificación n
    importe_anterior: float = 0.0
    importe_actual: float = 0.0

    @property
    def origen(self) -> float:
        return self.anterior + self.actual

    @property
    def importe_origen(self) -> float:
        return self.importe_anterior + self.importe_actual


def _cantidad_certificada(obra: Obra, padre: str, indice: int, desde: int, hasta: int) -> float:
    """Suma de lo certificado en las certificaciones con desde <= numero <= hasta."""
    d = obra.conceptos[padre].hijos[indice]
    dec = obra.parametros.decimales_medicion
    return sum(redondear(m.total(), dec) for n, m in d.certificado.items() if desde <= n <= hasta)


def certificado(obra: Obra, padre: str, indice: int, numero: int) -> Certificado:
    """Certificado del hijo `indice` de `padre` en la certificación `numero`.

    Para partidas devuelve cantidades; para capítulos solo importes (sumados de sus hijos).
    """
    d = obra.conceptos[padre].hijos[indice]
    c = obra.conceptos.get(d.codigo)
    dec = obra.parametros.decimales_importe
    if c is not None and c.es_agrupador:
        r = Certificado()
        for j in range(len(c.hijos)):
            h = certificado(obra, d.codigo, j, numero)
            r.importe_anterior += h.importe_anterior
            r.importe_actual += h.importe_actual
        r.importe_anterior = redondear(r.importe_anterior, dec)
        r.importe_actual = redondear(r.importe_actual, dec)
        return r
    pu = precio(obra, d.codigo)
    anterior = _cantidad_certificada(obra, padre, indice, 1, numero - 1)
    actual = _cantidad_certificada(obra, padre, indice, numero, numero)
    importe_anterior = redondear(anterior * pu, dec)
    importe_origen = redondear((anterior + actual) * pu, dec)
    # el importe actual se obtiene por diferencia para que anterior + actual == origen
    return Certificado(anterior, actual, importe_anterior, redondear(importe_origen - importe_anterior, dec))


def certificado_obra(obra: Obra, numero: int) -> Certificado:
    r = Certificado()
    for i in range(len(obra.conceptos[obra.raiz].hijos)):
        h = certificado(obra, obra.raiz, i, numero)
        r.importe_anterior += h.importe_anterior
        r.importe_actual += h.importe_actual
    dec = obra.parametros.decimales_importe
    r.importe_anterior = redondear(r.importe_anterior, dec)
    r.importe_actual = redondear(r.importe_actual, dec)
    return r


@dataclass
class Resumen:
    """Desglose desde el PEM hasta el total con IVA."""
    pem: float
    gastos_generales: float
    beneficio_industrial: float
    baja: float
    base: float
    iva: float
    total: float


def resumen(obra: Obra, pem: float) -> Resumen:
    p = obra.parametros
    dec = p.decimales_importe
    gg = redondear(pem * p.gastos_generales / 100, dec)
    bi = redondear(pem * p.beneficio_industrial / 100, dec)
    bruto = pem + gg + bi
    baja = redondear(bruto * p.baja / 100, dec)
    base = redondear(bruto - baja, dec)
    iva = redondear(base * p.iva / 100, dec)
    return Resumen(pem, gg, bi, baja, base, iva, redondear(base + iva, dec))


def medicion_pendiente(obra: Obra, padre: str, indice: int, numero: int) -> float:
    """Cantidad de presupuesto que queda por certificar antes de la certificación `numero`."""
    return cantidad(obra, padre, indice) - _cantidad_certificada(obra, padre, indice, 1, numero - 1)


def medicion_de(obra: Obra, padre: str, indice: int) -> Medicion:
    d = obra.conceptos[padre].hijos[indice]
    if d.medicion is None:
        d.medicion = Medicion()
    return d.medicion


def certificado_de(obra: Obra, padre: str, indice: int, numero: int) -> Medicion:
    return obra.conceptos[padre].hijos[indice].certificado.setdefault(numero, Medicion())
