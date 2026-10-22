"""Formato de proyecto propio (.obra): JSON con presupuesto y certificaciones."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .modelo import (
    Certificacion, Concepto, Descomposicion, LineaMedicion, Medicion, Obra, Parametros,
)

VERSION = 1


def _medicion_a_dict(m: Medicion) -> dict:
    return {"lineas": [asdict(l) for l in m.lineas], "total_directo": m.total_directo}


def _medicion_desde_dict(d: dict) -> Medicion:
    return Medicion([LineaMedicion(**l) for l in d.get("lineas", [])], d.get("total_directo", 0.0))


def _mediciones_a_lista(meds: dict[tuple[str, str], Medicion]) -> list[dict]:
    return [{"padre": p, "hijo": h, **_medicion_a_dict(m)} for (p, h), m in meds.items()]


def _mediciones_desde_lista(lista: list[dict]) -> dict[tuple[str, str], Medicion]:
    return {(d["padre"], d["hijo"]): _medicion_desde_dict(d) for d in lista}


def a_dict(obra: Obra) -> dict:
    return {
        "version": VERSION,
        "raiz": obra.raiz,
        "propiedad": obra.propiedad,
        "parametros": asdict(obra.parametros),
        "conceptos": [
            {**{k: v for k, v in asdict(c).items() if k != "hijos"},
             "hijos": [asdict(d) for d in c.hijos]}
            for c in obra.conceptos.values()
        ],
        "mediciones": _mediciones_a_lista(obra.mediciones),
        "certificaciones": [
            {"numero": c.numero, "fecha": c.fecha.isoformat(),
             "mediciones": _mediciones_a_lista(c.mediciones)}
            for c in obra.certificaciones
        ],
    }


def desde_dict(datos: dict) -> Obra:
    obra = Obra(raiz=datos["raiz"], propiedad=datos.get("propiedad", ""))
    obra.parametros = Parametros(**datos.get("parametros", {}))
    for c in datos["conceptos"]:
        hijos = [Descomposicion(**d) for d in c.pop("hijos", [])]
        obra.conceptos[c["codigo"]] = Concepto(**c, hijos=hijos)
    obra.mediciones = _mediciones_desde_lista(datos.get("mediciones", []))
    obra.certificaciones = [
        Certificacion(c["numero"], date.fromisoformat(c["fecha"]), _mediciones_desde_lista(c["mediciones"]))
        for c in datos.get("certificaciones", [])
    ]
    return obra


def guardar(obra: Obra, ruta: str | Path) -> None:
    ruta = Path(ruta)
    temporal = ruta.with_suffix(ruta.suffix + ".tmp")
    temporal.write_text(json.dumps(a_dict(obra), ensure_ascii=False, indent=1), encoding="utf-8")
    temporal.replace(ruta)


def abrir(ruta: str | Path) -> Obra:
    return desde_dict(json.loads(Path(ruta).read_text(encoding="utf-8")))
