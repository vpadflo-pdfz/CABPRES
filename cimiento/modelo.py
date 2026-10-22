"""Modelo de datos de una obra: presupuesto, mediciones y certificaciones.

Los códigos se guardan sin las marcas '#' del formato BC3; el tipo de nodo
(raíz, capítulo, partida...) se guarda aparte en `Concepto.naturaleza`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# Naturaleza del concepto
RAIZ = "raiz"
CAPITULO = "capitulo"
PARTIDA = "partida"
MANO_OBRA = "mano_obra"
MAQUINARIA = "maquinaria"
MATERIAL = "material"
OTRO = "otro"

# Tipo de concepto en BC3 (campo TIPO de ~C) <-> naturaleza
TIPO_BC3 = {MANO_OBRA: "1", MAQUINARIA: "2", MATERIAL: "3"}
NATURALEZA_DESDE_TIPO = {"1": MANO_OBRA, "2": MAQUINARIA, "3": MATERIAL}

# Tipos de línea de medición (BC3)
LINEA_NORMAL = ""
LINEA_SUBTOTAL_PARCIAL = "1"
LINEA_SUBTOTAL_ACUMULADO = "2"
LINEA_EXPRESION = "3"


@dataclass
class LineaMedicion:
    comentario: str = ""
    unidades: float | None = None
    longitud: float | None = None
    anchura: float | None = None
    altura: float | None = None
    tipo: str = LINEA_NORMAL

    def parcial(self) -> float:
        """Producto de las dimensiones rellenas; las de subtotal no suman."""
        if self.tipo in (LINEA_SUBTOTAL_PARCIAL, LINEA_SUBTOTAL_ACUMULADO):
            return 0.0
        valores = [v for v in (self.unidades, self.longitud, self.anchura, self.altura) if v is not None]
        if not valores:
            return 0.0
        resultado = 1.0
        for v in valores:
            resultado *= v
        return resultado


@dataclass
class Medicion:
    """Medición de un hijo dentro de un padre: por líneas o con total directo."""
    lineas: list[LineaMedicion] = field(default_factory=list)
    total_directo: float = 0.0

    def total(self) -> float:
        if self.lineas:
            return sum(l.parcial() for l in self.lineas)
        return self.total_directo

    def vacia(self) -> bool:
        return not self.lineas and self.total_directo == 0.0


@dataclass
class Descomposicion:
    codigo: str
    factor: float = 1.0
    rendimiento: float = 1.0


@dataclass
class Concepto:
    codigo: str
    resumen: str = ""
    unidad: str = ""
    precio: float = 0.0  # precio propio (solo cuenta si no tiene descomposición)
    naturaleza: str = PARTIDA
    texto: str = ""
    fecha: str = ""
    hijos: list[Descomposicion] = field(default_factory=list)

    @property
    def es_agrupador(self) -> bool:
        return self.naturaleza in (RAIZ, CAPITULO)


@dataclass
class Certificacion:
    """Certificación n: mediciones ejecutadas EN ESTE PERIODO (no a origen)."""
    numero: int
    fecha: date
    mediciones: dict[tuple[str, str], Medicion] = field(default_factory=dict)


@dataclass
class Parametros:
    gastos_generales: float = 13.0  # %
    beneficio_industrial: float = 6.0  # %
    baja: float = 0.0  # %
    iva: float = 21.0  # %
    decimales_precio: int = 2
    decimales_importe: int = 2
    decimales_rendimiento: int = 3
    divisa: str = "EUR"


@dataclass
class Obra:
    raiz: str = "OBRA"
    conceptos: dict[str, Concepto] = field(default_factory=dict)
    mediciones: dict[tuple[str, str], Medicion] = field(default_factory=dict)
    certificaciones: list[Certificacion] = field(default_factory=list)
    parametros: Parametros = field(default_factory=Parametros)
    propiedad: str = ""

    @classmethod
    def nueva(cls, resumen: str = "Nueva obra") -> Obra:
        obra = cls()
        obra.conceptos[obra.raiz] = Concepto(obra.raiz, resumen, naturaleza=RAIZ)
        return obra

    # --- navegación -------------------------------------------------------
    def concepto(self, codigo: str) -> Concepto:
        return self.conceptos[codigo]

    def hijos(self, codigo: str) -> list[Descomposicion]:
        c = self.conceptos.get(codigo)
        return c.hijos if c else []

    def padres_de(self, codigo: str) -> list[str]:
        return [c.codigo for c in self.conceptos.values() if any(d.codigo == codigo for d in c.hijos)]

    def certificacion(self, numero: int) -> Certificacion | None:
        for cert in self.certificaciones:
            if cert.numero == numero:
                return cert
        return None

    # --- edición ----------------------------------------------------------
    def codigo_libre(self, prefijo: str) -> str:
        n = 1
        while f"{prefijo}{n:02d}" in self.conceptos:
            n += 1
        return f"{prefijo}{n:02d}"

    def anadir_hijo(self, padre: str, concepto: Concepto, rendimiento: float = 1.0) -> Concepto:
        if concepto.codigo not in self.conceptos:
            self.conceptos[concepto.codigo] = concepto
        self.conceptos[padre].hijos.append(Descomposicion(concepto.codigo, 1.0, rendimiento))
        return self.conceptos[concepto.codigo]

    def quitar_hijo(self, padre: str, indice: int) -> None:
        d = self.conceptos[padre].hijos.pop(indice)
        clave = (padre, d.codigo)
        if not any(h.codigo == d.codigo for h in self.conceptos[padre].hijos):
            self.mediciones.pop(clave, None)
            for cert in self.certificaciones:
                cert.mediciones.pop(clave, None)
        self._purgar_huerfanos()

    def renombrar(self, viejo: str, nuevo: str) -> None:
        nuevo = nuevo.strip().rstrip("#")
        if not nuevo or nuevo == viejo:
            return
        if nuevo in self.conceptos:
            raise ValueError(f"Ya existe un concepto con código {nuevo}.")
        if any(ch in nuevo for ch in "|\\~"):
            raise ValueError("El código no puede contener los caracteres | \\ ~")
        c = self.conceptos.pop(viejo)
        c.codigo = nuevo
        self.conceptos[nuevo] = c
        if self.raiz == viejo:
            self.raiz = nuevo
        for otro in self.conceptos.values():
            for d in otro.hijos:
                if d.codigo == viejo:
                    d.codigo = nuevo

        def renombrar_claves(meds: dict[tuple[str, str], Medicion]) -> dict[tuple[str, str], Medicion]:
            return {(nuevo if p == viejo else p, nuevo if h == viejo else h): m for (p, h), m in meds.items()}

        self.mediciones = renombrar_claves(self.mediciones)
        for cert in self.certificaciones:
            cert.mediciones = renombrar_claves(cert.mediciones)

    def mover_hijo(self, padre: str, indice: int, desplazamiento: int) -> int:
        hijos = self.conceptos[padre].hijos
        destino = indice + desplazamiento
        if not 0 <= destino < len(hijos):
            return indice
        hijos[indice], hijos[destino] = hijos[destino], hijos[indice]
        return destino

    def _purgar_huerfanos(self) -> None:
        alcanzables: set[str] = set()
        pendientes = [self.raiz]
        while pendientes:
            cod = pendientes.pop()
            if cod in alcanzables or cod not in self.conceptos:
                continue
            alcanzables.add(cod)
            pendientes.extend(d.codigo for d in self.conceptos[cod].hijos)
        for cod in list(self.conceptos):
            if cod not in alcanzables:
                del self.conceptos[cod]

    def nueva_certificacion(self, fecha: date | None = None) -> Certificacion:
        numero = max((c.numero for c in self.certificaciones), default=0) + 1
        cert = Certificacion(numero, fecha or date.today())
        self.certificaciones.append(cert)
        return cert

    def borrar_certificacion(self, numero: int) -> None:
        self.certificaciones = [c for c in self.certificaciones if c.numero != numero]
