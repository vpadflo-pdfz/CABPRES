"""Informes en HTML (para ver, imprimir o exportar a PDF)."""
from __future__ import annotations

from html import escape

from . import calculo
from .modelo import Obra


def numero(valor: float, decimales: int = 2) -> str:
    """Formato español: 1.234,56"""
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


ESTILO = """
<style>
 body { font-family: Arial, sans-serif; font-size: 9pt; }
 h1 { font-size: 14pt; margin-bottom: 2px; }
 h2 { font-size: 11pt; margin-top: 14px; }
 table { border-collapse: collapse; width: 100%; }
 th { background: #dde3ea; border-bottom: 1px solid #555; text-align: left; padding: 3px; }
 td { padding: 2px 3px; vertical-align: top; }
 td.n, th.n { text-align: right; white-space: nowrap; }
 tr.cap td { font-weight: bold; background: #f0f2f5; }
 tr.sub td { font-weight: bold; border-top: 1px solid #999; }
 table.resumen { width: 70%; margin-top: 8px; }
 table.resumen td { border-bottom: 1px solid #ddd; }
 tr.total td { font-weight: bold; border-top: 2px solid #333; }
</style>
"""


def certificacion(obra: Obra, n: int) -> str:
    cert = obra.certificacion(n)
    if cert is None:
        raise ValueError(f"No existe la certificación n.º {n}")
    raiz = obra.conceptos[obra.raiz]
    dp = obra.parametros.decimales_precio
    filas: list[str] = []

    def visitar(codigo: str, nivel: int, visitando: frozenset[str]):
        c = obra.conceptos[codigo]
        for i, d in enumerate(c.hijos):
            hijo = obra.conceptos.get(d.codigo)
            if hijo is None or d.codigo in visitando:
                continue
            cer = calculo.certificado(obra, codigo, i, n)
            sangria = "&nbsp;" * 4 * nivel
            if hijo.es_agrupador:
                filas.append(f'<tr class="cap"><td>{sangria}{escape(d.codigo)}</td><td></td>'
                             f'<td colspan="5">{escape(hijo.resumen)}</td><td></td><td></td><td></td></tr>')
                visitar(d.codigo, nivel + 1, visitando | {d.codigo})
                filas.append(f'<tr class="sub"><td></td><td></td><td colspan="5">Total {escape(d.codigo)}</td>'
                             f'<td class="n">{numero(cer.importe_anterior)}</td>'
                             f'<td class="n">{numero(cer.importe_actual)}</td>'
                             f'<td class="n">{numero(cer.importe_origen)}</td></tr>')
            elif cer.origen or cer.importe_origen:
                filas.append(
                    f'<tr><td>{sangria}{escape(d.codigo)}</td><td>{escape(hijo.unidad)}</td>'
                    f'<td>{escape(hijo.resumen)}</td>'
                    f'<td class="n">{numero(calculo.precio(obra, d.codigo), dp)}</td>'
                    f'<td class="n">{numero(cer.anterior, 3)}</td><td class="n">{numero(cer.actual, 3)}</td>'
                    f'<td class="n">{numero(cer.origen, 3)}</td>'
                    f'<td class="n">{numero(cer.importe_anterior)}</td>'
                    f'<td class="n">{numero(cer.importe_actual)}</td>'
                    f'<td class="n">{numero(cer.importe_origen)}</td></tr>')

    visitar(obra.raiz, 0, frozenset({obra.raiz}))
    total = calculo.certificado_obra(obra, n)
    r_ant = calculo.resumen(obra, total.importe_anterior)
    r_ori = calculo.resumen(obra, total.importe_origen)
    pem_presupuesto = calculo.precio(obra, obra.raiz)
    porcentaje = 100 * total.importe_origen / pem_presupuesto if pem_presupuesto else 0
    p = obra.parametros

    def fila_resumen(etiqueta: str, a: float, o: float, clase: str = "") -> str:
        return (f'<tr class="{clase}"><td>{etiqueta}</td><td class="n">{numero(o)}</td>'
                f'<td class="n">{numero(a)}</td><td class="n">{numero(o - a)}</td></tr>')

    return f"""<html><head><meta charset="utf-8">{ESTILO}</head><body>
<h1>Certificación n.º {n}</h1>
<div><b>{escape(raiz.resumen)}</b></div>
<div>Propiedad: {escape(obra.propiedad)}</div>
<div>Fecha: {cert.fecha.strftime('%d/%m/%Y')}</div>
<h2>Relación valorada</h2>
<table>
<tr><th>Código</th><th>Ud</th><th>Resumen</th><th class="n">Precio</th>
<th class="n">Cant. anterior</th><th class="n">Cant. actual</th><th class="n">Cant. origen</th>
<th class="n">Imp. anterior</th><th class="n">Imp. actual</th><th class="n">Imp. origen</th></tr>
{''.join(filas)}
<tr class="total"><td></td><td></td><td colspan="5">TOTAL EJECUCIÓN MATERIAL</td>
<td class="n">{numero(total.importe_anterior)}</td><td class="n">{numero(total.importe_actual)}</td>
<td class="n">{numero(total.importe_origen)}</td></tr>
</table>
<h2>Resumen</h2>
<table class="resumen">
<tr><th></th><th class="n">A origen</th><th class="n">Anterior</th><th class="n">Esta certificación</th></tr>
{fila_resumen('Presupuesto de ejecución material', r_ant.pem, r_ori.pem)}
{fila_resumen(f'Gastos generales ({numero(p.gastos_generales)} %)', r_ant.gastos_generales, r_ori.gastos_generales)}
{fila_resumen(f'Beneficio industrial ({numero(p.beneficio_industrial)} %)', r_ant.beneficio_industrial, r_ori.beneficio_industrial)}
{fila_resumen(f'Baja ({numero(p.baja)} %)', -r_ant.baja, -r_ori.baja) if p.baja else ''}
{fila_resumen('Base imponible', r_ant.base, r_ori.base, 'sub')}
{fila_resumen(f'IVA ({numero(p.iva)} %)', r_ant.iva, r_ori.iva)}
{fila_resumen('TOTAL', r_ant.total, r_ori.total, 'total')}
</table>
<p>Importe líquido de esta certificación: <b>{numero(r_ori.total - r_ant.total)} {escape(p.divisa)}</b></p>
<p>Obra ejecutada a origen: {numero(porcentaje)} % del presupuesto de ejecución material
({numero(pem_presupuesto)} {escape(p.divisa)}).</p>
</body></html>"""


def presupuesto(obra: Obra) -> str:
    raiz = obra.conceptos[obra.raiz]
    dp = obra.parametros.decimales_precio
    filas: list[str] = []

    def visitar(codigo: str, nivel: int, visitando: frozenset[str]):
        c = obra.conceptos[codigo]
        for i, d in enumerate(c.hijos):
            hijo = obra.conceptos.get(d.codigo)
            if hijo is None or d.codigo in visitando:
                continue
            sangria = "&nbsp;" * 4 * nivel
            if hijo.es_agrupador:
                filas.append(f'<tr class="cap"><td>{sangria}{escape(d.codigo)}</td><td></td>'
                             f'<td colspan="3">{escape(hijo.resumen)}</td><td></td></tr>')
                visitar(d.codigo, nivel + 1, visitando | {d.codigo})
                filas.append(f'<tr class="sub"><td></td><td></td><td colspan="3">Total {escape(d.codigo)}</td>'
                             f'<td class="n">{numero(calculo.importe(obra, codigo, i))}</td></tr>')
            else:
                filas.append(
                    f'<tr><td>{sangria}{escape(d.codigo)}</td><td>{escape(hijo.unidad)}</td>'
                    f'<td>{escape(hijo.resumen)}</td>'
                    f'<td class="n">{numero(calculo.cantidad(obra, codigo, i), 3)}</td>'
                    f'<td class="n">{numero(calculo.precio(obra, d.codigo), dp)}</td>'
                    f'<td class="n">{numero(calculo.importe(obra, codigo, i))}</td></tr>')

    visitar(obra.raiz, 0, frozenset({obra.raiz}))
    r = calculo.resumen(obra, calculo.precio(obra, obra.raiz))
    p = obra.parametros
    return f"""<html><head><meta charset="utf-8">{ESTILO}</head><body>
<h1>{escape(raiz.resumen)}</h1>
<div>Propiedad: {escape(obra.propiedad)}</div>
<h2>Presupuesto</h2>
<table>
<tr><th>Código</th><th>Ud</th><th>Resumen</th><th class="n">Cantidad</th><th class="n">Precio</th>
<th class="n">Importe</th></tr>
{''.join(filas)}
</table>
<h2>Resumen</h2>
<table class="resumen">
<tr><td>Presupuesto de ejecución material</td><td class="n">{numero(r.pem)}</td></tr>
<tr><td>Gastos generales ({numero(p.gastos_generales)} %)</td><td class="n">{numero(r.gastos_generales)}</td></tr>
<tr><td>Beneficio industrial ({numero(p.beneficio_industrial)} %)</td><td class="n">{numero(r.beneficio_industrial)}</td></tr>
{f'<tr><td>Baja ({numero(p.baja)} %)</td><td class="n">-{numero(r.baja)}</td></tr>' if p.baja else ''}
<tr class="sub"><td>Base imponible</td><td class="n">{numero(r.base)}</td></tr>
<tr><td>IVA ({numero(p.iva)} %)</td><td class="n">{numero(r.iva)}</td></tr>
<tr class="total"><td>TOTAL</td><td class="n">{numero(r.total)} {escape(p.divisa)}</td></tr>
</table>
</body></html>"""
