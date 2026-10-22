"""Diálogos auxiliares: parámetros de la obra, fecha de certificación e informes."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import (
    QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QTextBrowser, QVBoxLayout,
)

from ..modelo import Obra


def _porcentaje(valor: float) -> QDoubleSpinBox:
    caja = QDoubleSpinBox()
    caja.setRange(0, 100)
    caja.setDecimals(2)
    caja.setSuffix(" %")
    caja.setValue(valor)
    return caja


class DialogoParametros(QDialog):
    def __init__(self, obra: Obra, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Datos de la obra")
        self.obra = obra
        p = obra.parametros
        self.resumen = QLineEdit(obra.conceptos[obra.raiz].resumen)
        self.propiedad = QLineEdit(obra.propiedad)
        self.gg = _porcentaje(p.gastos_generales)
        self.bi = _porcentaje(p.beneficio_industrial)
        self.baja = _porcentaje(p.baja)
        self.iva = _porcentaje(p.iva)
        self.dec_precio = QSpinBox()
        self.dec_precio.setRange(0, 4)
        self.dec_precio.setValue(p.decimales_precio)
        self.divisa = QLineEdit(p.divisa)

        formulario = QFormLayout()
        formulario.addRow("Nombre de la obra", self.resumen)
        formulario.addRow("Propiedad", self.propiedad)
        formulario.addRow("Gastos generales", self.gg)
        formulario.addRow("Beneficio industrial", self.bi)
        formulario.addRow("Baja", self.baja)
        formulario.addRow("IVA", self.iva)
        formulario.addRow("Decimales de precio", self.dec_precio)
        formulario.addRow("Divisa", self.divisa)
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        capa = QVBoxLayout(self)
        capa.addLayout(formulario)
        capa.addWidget(botones)

    def aplicar(self) -> None:
        p = self.obra.parametros
        self.obra.conceptos[self.obra.raiz].resumen = self.resumen.text()
        self.obra.propiedad = self.propiedad.text()
        p.gastos_generales = self.gg.value()
        p.beneficio_industrial = self.bi.value()
        p.baja = self.baja.value()
        p.iva = self.iva.value()
        p.decimales_precio = self.dec_precio.value()
        p.divisa = self.divisa.text().strip() or "EUR"


class DialogoFecha(QDialog):
    def __init__(self, titulo: str, inicial: date, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.fecha = QDateEdit(QDate(inicial.year, inicial.month, inicial.day))
        self.fecha.setCalendarPopup(True)
        self.fecha.setDisplayFormat("dd/MM/yyyy")
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        formulario = QFormLayout(self)
        formulario.addRow("Fecha", self.fecha)
        formulario.addRow(botones)

    def valor(self) -> date:
        return self.fecha.date().toPython()


class DialogoInforme(QDialog):
    """Vista previa de un informe HTML con exportación a PDF."""

    def __init__(self, titulo: str, html: str, nombre_pdf: str, horizontal: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.resize(1000, 700)
        self.html = html
        self.nombre_pdf = nombre_pdf
        self.horizontal = horizontal
        vista = QTextBrowser()
        vista.setHtml(html)
        boton_pdf = QPushButton("Exportar a PDF…")
        boton_pdf.clicked.connect(self.exportar_pdf)
        boton_cerrar = QPushButton("Cerrar")
        boton_cerrar.clicked.connect(self.accept)
        barra = QHBoxLayout()
        barra.addStretch()
        barra.addWidget(boton_pdf)
        barra.addWidget(boton_cerrar)
        capa = QVBoxLayout(self)
        capa.addWidget(vista)
        capa.addLayout(barra)

    def exportar_pdf(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar a PDF", self.nombre_pdf, "PDF (*.pdf)")
        if not ruta:
            return
        if not ruta.lower().endswith(".pdf"):
            ruta += ".pdf"
        exportar_pdf(self.html, ruta, self.horizontal)
        QMessageBox.information(self, "PDF", f"Guardado en:\n{ruta}")


def exportar_pdf(html: str, ruta: str, horizontal: bool = False) -> None:
    escritor = QPdfWriter(ruta)
    escritor.setPageLayout(QPageLayout(
        QPageSize(QPageSize.A4),
        QPageLayout.Landscape if horizontal else QPageLayout.Portrait,
        QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter))
    documento = QTextDocument()
    documento.setHtml(html)
    documento.print_(escritor)
