"""Formato de proyecto propio (.obra): JSON con presupuesto y certificaciones."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .modelo import (
    Certificacion, Concepto, Descomposicion, LineaMedicion, Medicion, Obra, Parametros,
)

VERSION = 2


def _medicion_a_dict(m: Medicion | None) -> dict | None:
    if m is None:
        return None
    return {"lineas": [asdict(l) for l in m.lineas], "total_directo": m.total_directo}


def _medicion_desde_dict(d: dict | None) -> Medicion | None:
    if d is None:
        return None
    return Medicion([LineaMedicion(**l) for l in d.get("lineas", [])], d.get("total_directo", 0.0))


def _linea_a_dict(d: Descomposicion) -> dict:
    datos = {"codigo": d.codigo, "factor": d.factor, "rendimiento": d.rendimiento}
    if d.medicion is not None:
        datos["medicion"] = _medicion_a_dict(d.medicion)
    if d.certificado:
        datos["certificado"] = {str(n): _medicion_a_dict(m) for n, m in sorted(d.certificado.items())}
    return datos


def _linea_desde_dict(datos: dict) -> Descomposicion:
    return Descomposicion(
        datos["codigo"], datos.get("factor", 1.0), datos.get("rendimiento", 1.0),
        _medicion_desde_dict(datos.get("medicion")),
        {int(n): _medicion_desde_dict(m) for n, m in datos.get("certificado", {}).items()},
    )


def a_dict(obra: Obra) -> dict:
    return {
        "version": VERSION,
        "raiz": obra.raiz,
        "propiedad": obra.propiedad,
        "parametros": asdict(obra.parametros),
        "conceptos": [
            {**{k: v for k, v in asdict(c).items() if k != "hijos"},
             "hijos": [_linea_a_dict(d) for d in c.hijos]}
            for c in obra.conceptos.values()
        ],
        "certificaciones": [{"numero": c.numero, "fecha": c.fecha.isoformat()} for c in obra.certificaciones],
    }


def desde_dict(datos: dict) -> Obra:
    obra = Obra(raiz=datos["raiz"], propiedad=datos.get("propiedad", ""))
    obra.parametros = Parametros(**datos.get("parametros", {}))
    for c in datos["conceptos"]:
        hijos = [_linea_desde_dict(d) for d in c.pop("hijos", [])]
        obra.conceptos[c["codigo"]] = Concepto(**c, hijos=hijos)
    obra.certificaciones = [
        Certificacion(c["numero"], date.fromisoformat(c["fecha"])) for c in datos.get("certificaciones", [])
    ]
    if datos.get("version", 1) == 1:
        _migrar_v1(obra, datos)
    return obra


def _migrar_v1(obra: Obra, datos: dict) -> None:
    """La versión 1 guardaba las mediciones aparte, indexadas por (padre, hijo)."""
    def linea(padre: str, hijo: str) -> Descomposicion | None:
        c = obra.conceptos.get(padre)
        return next((d for d in c.hijos if d.codigo == hijo), None) if c else None

    for m in datos.get("mediciones", []):
        d = linea(m["padre"], m["hijo"])
        if d is not None:
            d.medicion = _medicion_desde_dict(m)
    for cert in datos.get("certificaciones", []):
        for m in cert.get("mediciones", []):
            d = linea(m["padre"], m["hijo"])
            if d is not None:
                d.certificado[cert["numero"]] = _medicion_desde_dict(m)


def guardar(obra: Obra, ruta: str | Path) -> None:
    ruta = Path(ruta)
    temporal = ruta.with_suffix(ruta.suffix + ".tmp")
    temporal.write_text(json.dumps(a_dict(obra), ensure_ascii=False, indent=1), encoding="utf-8")
    temporal.replace(ruta)


def abrir(ruta: str | Path) -> Obra:
    return desde_dict(json.loads(Path(ruta).read_text(encoding="utf-8")))
