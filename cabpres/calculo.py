"""Cálculo de precios, importes y certificaciones."""
from __future__ import annotations

from dataclasses import dataclass

from .modelo import Medicion, Obra


def redondear(valor: float, decimales: int) -> float:
    # round() de Python redondea al par; en presupuestos se redondea "hacia arriba" desde .5
    from decimal import ROUND_HALF_UP, Decimal
    return float(Decimal(repr(valor)).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP))


def cantidad(obra: Obra, padre: str, indice: int) -> float:
    """Cantidad del hijo `indice` de `padre`: su medición si la tiene, si no el rendimiento."""
    d = obra.conceptos[padre].hijos[indice]
    med = obra.mediciones.get((padre, d.codigo))
    if med is not None and not med.vacia():
        return med.total()
    return d.rendimiento


def precio(obra: Obra, codigo: str, _visitando: frozenset[str] = frozenset()) -> float:
    """Precio unitario del concepto (para capítulos y raíz, su importe total)."""
    c = obra.conceptos.get(codigo)
    if c is None or codigo in _visitando:
        return 0.0
    if not c.hijos:
        return c.precio
    p = obra.parametros
    visitando = _visitando | {codigo}
    total = 0.0
    for i, d in enumerate(c.hijos):
        pu = precio(obra, d.codigo, visitando)
        if c.es_agrupador:
            total += redondear(pu * cantidad(obra, codigo, i), p.decimales_importe)
        else:
            total += redondear(pu * d.factor * d.rendimiento, p.decimales_importe)
    return redondear(total, p.decimales_precio)


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


def _cantidad_certificada(obra: Obra, padre: str, hijo: str, desde: int, hasta: int) -> float:
    """Suma de lo certificado en las certificaciones con desde <= numero <= hasta."""
    total = 0.0
    for cert in obra.certificaciones:
        if desde <= cert.numero <= hasta:
            med = cert.mediciones.get((padre, hijo))
            if med is not None:
                total += med.total()
    return total


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
    anterior = _cantidad_certificada(obra, padre, d.codigo, 1, numero - 1)
    actual = _cantidad_certificada(obra, padre, d.codigo, numero, numero)
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


def medicion_pendiente(obra: Obra, padre: str, hijo: str, numero: int) -> float:
    """Cantidad de presupuesto que queda por certificar antes de la certificación `numero`."""
    indice = next(i for i, d in enumerate(obra.conceptos[padre].hijos) if d.codigo == hijo)
    return cantidad(obra, padre, indice) - _cantidad_certificada(obra, padre, hijo, 1, numero - 1)


def medicion_de(obra: Obra, padre: str, hijo: str) -> Medicion:
    return obra.mediciones.setdefault((padre, hijo), Medicion())
