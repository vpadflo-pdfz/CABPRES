"""Lectura y escritura del formato de intercambio FIEBDC-3 (.bc3)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from . import calculo
from .modelo import (
    CAPITULO, NATURALEZA_DESDE_TIPO, OTRO, PARTIDA, RAIZ, TIPO_BC3,
    Certificacion, Concepto, Descomposicion, LineaMedicion, Medicion, Obra,
)

JUEGOS_CARACTERES = {"ANSI": "cp1252", "850": "cp850", "437": "cp437"}
TIPO_INFO_CERTIFICACION = "3"


class ErrorBC3(Exception):
    pass


# --- lectura -------------------------------------------------------------------

def _num(texto: str) -> float | None:
    texto = texto.strip()
    if not texto:
        return None
    try:
        return float(texto.replace(",", "."))
    except ValueError:
        return None


def _codigo(texto: str) -> tuple[str, int]:
    """Devuelve el código sin marcas y el número de '#' que llevaba."""
    texto = texto.strip()
    sin = texto.rstrip("#")
    return sin, len(texto) - len(sin)


def _subcampos(campo: str) -> list[str]:
    return campo.split("\\")


def _decodificar(datos: bytes) -> str:
    # El juego de caracteres va en el registro ~V; los separadores son ASCII.
    provisional = datos.decode("latin-1")
    codificacion = "cp1252"
    inicio = provisional.find("~V|")
    if inicio >= 0:
        campos = provisional[inicio:].split("~", 2)[1].split("|")
        if len(campos) > 5:
            codificacion = JUEGOS_CARACTERES.get(campos[5].strip().upper(), "cp1252")
    return datos.decode(codificacion, errors="replace")


def registros(texto: str) -> list[list[str]]:
    """Separa el fichero en registros; cada uno es la lista de sus campos."""
    resultado = []
    for bloque in texto.split("~")[1:]:
        bloque = bloque.rstrip("\r\n\x1a")
        if not bloque:
            continue
        campos = bloque.split("|")
        resultado.append(campos)
    return resultado


def leer(ruta: str | Path) -> tuple[Obra, dict]:
    """Lee un .bc3. Devuelve la obra y la cabecera (~V) como diccionario."""
    return parsear(Path(ruta).read_bytes())


def parsear(datos: bytes) -> tuple[Obra, dict]:
    regs = registros(_decodificar(datos))
    obra = Obra()
    cabecera: dict = {}
    raices: list[str] = []
    mediciones_m: list[list[str]] = []

    for campos in regs:
        tipo = campos[0].strip().upper()
        f = campos + [""] * 12
        if tipo == "V":
            fecha_cert = f[9].strip()
            cabecera = {
                "propiedad": f[1].strip(),
                "programa": f[3].strip(),
                "cabecera": _subcampos(f[4])[0].strip(),
                "tipo_informacion": f[7].strip(),
                "numero_certificacion": int(f[8]) if f[8].strip().isdigit() else None,
                "fecha_certificacion": _fecha(fecha_cert),
            }
            obra.propiedad = cabecera["propiedad"]
        elif tipo == "K":
            # ~K|DN\DD\DS\DR\DI\DP\DC\DM\DIVISA|CI|GG|BI|BAJA|IVA|...
            sub = _subcampos(f[1])
            if len(sub) > 8 and sub[8].strip():
                obra.parametros.divisa = sub[8].strip()
            for atributo, indice in (("gastos_generales", 3), ("beneficio_industrial", 4),
                                     ("baja", 5), ("iva", 6)):
                v = _num(f[indice])
                if v is not None:
                    setattr(obra.parametros, atributo, v)
        elif tipo == "C":
            codigos = [c for c in _subcampos(f[1]) if c.strip()]
            if not codigos:
                continue
            codigo, marcas = _codigo(codigos[0])
            precios = [p for p in _subcampos(f[4]) if p.strip()]
            fechas = [p for p in _subcampos(f[5]) if p.strip()]
            tipo_c = f[6].strip()
            if marcas >= 2:
                naturaleza = RAIZ
                raices.append(codigo)
            elif marcas == 1:
                naturaleza = CAPITULO
            else:
                naturaleza = NATURALEZA_DESDE_TIPO.get(tipo_c, PARTIDA if tipo_c in ("", "0") else OTRO)
            existente = obra.conceptos.get(codigo)
            concepto = Concepto(
                codigo=codigo,
                resumen=f[3].strip(),
                unidad=f[2].strip(),
                precio=_num(precios[0]) or 0.0 if precios else 0.0,
                naturaleza=naturaleza,
                fecha=fechas[0].strip() if fechas else "",
            )
            if existente is not None:  # ~D o ~T pudieron llegar antes que ~C
                concepto.hijos, concepto.texto = existente.hijos, existente.texto
            obra.conceptos[codigo] = concepto
        elif tipo in ("D", "Y"):
            padre, _ = _codigo(f[1])
            concepto = obra.conceptos.setdefault(padre, Concepto(padre))
            if tipo == "D":
                concepto.hijos = []
            sub = _subcampos(f[2])
            for i in range(0, len(sub) - 2, 3):
                hijo, _ = _codigo(sub[i])
                if not hijo:
                    continue
                factor = _num(sub[i + 1])
                rendimiento = _num(sub[i + 2])
                concepto.hijos.append(Descomposicion(
                    hijo, 1.0 if factor is None else factor, 1.0 if rendimiento is None else rendimiento))
        elif tipo == "T":
            codigo, _ = _codigo(f[1])
            obra.conceptos.setdefault(codigo, Concepto(codigo)).texto = f[2].strip()
        elif tipo == "M":
            mediciones_m.append(f)

    if not raices:
        raise ErrorBC3("El fichero no tiene concepto raíz (código terminado en ##).")
    obra.raiz = raices[0]

    # Los conceptos referenciados en ~D pero sin ~C se crean vacíos.
    for c in list(obra.conceptos.values()):
        for d in c.hijos:
            obra.conceptos.setdefault(d.codigo, Concepto(d.codigo))

    for f in mediciones_m:
        sub = _subcampos(f[1])
        if len(sub) < 2:
            continue
        padre, _ = _codigo(sub[0])
        hijo, _ = _codigo(sub[1])
        obra.mediciones[(padre, hijo)] = _leer_medicion(f)

    return obra, cabecera


def _leer_medicion(f: list[str]) -> Medicion:
    med = Medicion(total_directo=_num(f[3]) or 0.0)
    sub = _subcampos(f[4])
    for i in range(0, len(sub) - 5, 6):
        tipo, comentario = sub[i].strip(), sub[i + 1].strip()
        dims = [_num(v) for v in sub[i + 2:i + 6]]
        med.lineas.append(LineaMedicion(comentario, *dims, tipo=tipo))
    if med.lineas and abs(med.total() - med.total_directo) > 0.0005 and all(
            l.tipo == "" for l in med.lineas) and not any(l.parcial() for l in med.lineas):
        # Líneas solo de comentario: manda el total del registro
        med.lineas.append(LineaMedicion("(total del fichero)", med.total_directo))
    return med


def _fecha(texto: str) -> date | None:
    texto = texto.strip()
    if len(texto) not in (6, 8) or not texto.isdigit():
        return None
    dia, mes, anio = int(texto[:2]), int(texto[2:4]), int(texto[4:])
    if len(texto) == 6:
        anio += 2000 if anio < 80 else 1900
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def importar_certificacion(obra: Obra, ruta: str | Path) -> Certificacion:
    """Añade a `obra` una certificación leída de un .bc3 de certificación.

    Las mediciones del fichero se interpretan como cantidades a origen; se guarda
    la diferencia con lo ya certificado.
    """
    datos, cabecera = leer(ruta)
    numero = cabecera.get("numero_certificacion") or (
        max((c.numero for c in obra.certificaciones), default=0) + 1)
    if obra.certificacion(numero):
        raise ErrorBC3(f"La obra ya tiene la certificación n.º {numero}.")
    cert = Certificacion(numero, cabecera.get("fecha_certificacion") or date.today())
    for (padre, hijo), med in datos.mediciones.items():
        c = obra.conceptos.get(padre)
        if c is None or not any(d.codigo == hijo for d in c.hijos):
            continue
        anterior = sum(m.total() for x in obra.certificaciones if x.numero < numero
                       for k, m in x.mediciones.items() if k == (padre, hijo))
        parcial = med.total() - anterior
        if abs(parcial) > 1e-9:
            cert.mediciones[(padre, hijo)] = Medicion(
                [LineaMedicion(f"Importado de certificación a origen ({med.total():g})", parcial)])
    obra.certificaciones.append(cert)
    obra.certificaciones.sort(key=lambda x: x.numero)
    return cert


# --- escritura -----------------------------------------------------------------

def _limpio(texto: str) -> str:
    return texto.replace("~", "-").replace("|", "/").replace("\\", "/")


def _n(valor: float | None, decimales: int = 6) -> str:
    if valor is None:
        return ""
    texto = f"{valor:.{decimales}f}".rstrip("0").rstrip(".")
    return "0" if texto in ("", "-0") else texto


def _codigo_bc3(obra: Obra, codigo: str) -> str:
    c = obra.conceptos[codigo]
    return codigo + ("##" if c.naturaleza == RAIZ else "#" if c.naturaleza == CAPITULO else "")


def _fecha_bc3(d: date) -> str:
    return d.strftime("%d%m%Y")


def escribir(obra: Obra, ruta: str | Path, certificacion: int | None = None) -> None:
    """Escribe la obra en .bc3. Con `certificacion`, escribe esa certificación a origen."""
    Path(ruta).write_bytes(generar(obra, certificacion))


def generar(obra: Obra, certificacion: int | None = None) -> bytes:
    p = obra.parametros
    lineas: list[str] = []
    cert = obra.certificacion(certificacion) if certificacion is not None else None
    if certificacion is not None and cert is None:
        raise ErrorBC3(f"No existe la certificación n.º {certificacion}.")
    raiz = obra.conceptos[obra.raiz]
    tipo_info = TIPO_INFO_CERTIFICACION if cert else "2"
    lineas.append("~V|{}|FIEBDC-3/2020\\{}|Cimiento|{}\\|ANSI||{}|{}|{}||".format(
        _limpio(obra.propiedad), _fecha_bc3(date.today()), _limpio(raiz.resumen), tipo_info,
        cert.numero if cert else "", _fecha_bc3(cert.fecha) if cert else ""))
    lineas.append("~K|{d}\\{d}\\{d}\\{r}\\{i}\\{pr}\\{i}\\{i}\\{div}\\|0|{gg}|{bi}|{baja}|{iva}|".format(
        d=p.decimales_importe, r=p.decimales_rendimiento, i=p.decimales_importe, pr=p.decimales_precio,
        div=p.divisa, gg=_n(p.gastos_generales), bi=_n(p.beneficio_industrial), baja=_n(p.baja),
        iva=_n(p.iva)))

    orden = _recorrido(obra)
    for codigo in orden:
        c = obra.conceptos[codigo]
        tipo = TIPO_BC3.get(c.naturaleza, "0")
        lineas.append("~C|{}|{}|{}|{}|{}|{}|".format(
            _codigo_bc3(obra, codigo), _limpio(c.unidad), _limpio(c.resumen),
            _n(calculo.precio(obra, codigo), p.decimales_precio), c.fecha, tipo))
        if c.texto:
            lineas.append("~T|{}|{}|".format(codigo, c.texto.replace("~", "-").replace("|", "/")))
    for codigo in orden:
        c = obra.conceptos[codigo]
        if not c.hijos:
            continue
        partes = []
        for i, d in enumerate(c.hijos):
            rend = calculo.cantidad(obra, codigo, i) if c.es_agrupador else d.rendimiento
            partes.append(f"{_codigo_bc3(obra, d.codigo)}\\{_n(d.factor)}\\{_n(rend)}\\")
        lineas.append("~D|{}|{}|".format(_codigo_bc3(obra, codigo), "".join(partes)))

    for padre, hijo, posicion in _posiciones(obra):
        if cert:
            # medición a origen: todas las certificaciones hasta la indicada
            lineas_med: list[LineaMedicion] = []
            for x in obra.certificaciones:
                if x.numero <= cert.numero and (padre, hijo) in x.mediciones:
                    m = x.mediciones[(padre, hijo)]
                    lineas_med += m.lineas or [LineaMedicion(f"Certificación {x.numero}", m.total())]
            med = Medicion(lineas_med)
            if not lineas_med:
                continue
        else:
            med = obra.mediciones.get((padre, hijo))
            if med is None or med.vacia():
                continue
        detalle = "".join("{}\\{}\\{}\\{}\\{}\\{}\\".format(
            l.tipo, _limpio(l.comentario), _n(l.unidades), _n(l.longitud), _n(l.anchura), _n(l.altura))
            for l in med.lineas)
        lineas.append("~M|{}\\{}|{}|{}|{}||".format(
            padre, hijo, "".join(f"{x}\\" for x in posicion), _n(med.total()), detalle))

    return ("\r\n".join(lineas) + "\r\n").encode("cp1252", errors="replace")


def _recorrido(obra: Obra) -> list[str]:
    vistos: list[str] = []
    pendientes = [obra.raiz]
    conjunto: set[str] = set()
    while pendientes:
        cod = pendientes.pop(0)
        if cod in conjunto or cod not in obra.conceptos:
            continue
        conjunto.add(cod)
        vistos.append(cod)
        pendientes.extend(d.codigo for d in obra.conceptos[cod].hijos)
    return vistos


def _posiciones(obra: Obra):
    """Genera (padre, hijo, posición) de cada partida del árbol de presupuesto."""
    def visitar(codigo: str, ruta: list[int], visitando: frozenset[str]):
        c = obra.conceptos[codigo]
        for i, d in enumerate(c.hijos, start=1):
            hijo = obra.conceptos.get(d.codigo)
            if hijo is None or d.codigo in visitando:
                continue
            if hijo.es_agrupador:
                yield from visitar(d.codigo, ruta + [i], visitando | {d.codigo})
            else:
                yield codigo, d.codigo, ruta + [i]
    if obra.raiz in obra.conceptos:
        yield from visitar(obra.raiz, [], frozenset({obra.raiz}))
