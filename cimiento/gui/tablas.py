"""Tablas editables de mediciones y descomposición."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..informes import numero
from ..modelo import LineaMedicion, Medicion


def leer_numero(texto: str) -> float | None:
    """Admite '1.234,5', '1234,5' y '1234.5'. Vacío -> None."""
    texto = texto.strip().replace(" ", "")
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return float(texto)


def celda(texto: str, editable: bool = True, derecha: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(texto)
    if not editable:
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    if derecha:
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return item


class TablaMedicion(QWidget):
    """Edita las líneas de una Medicion. Emite `cambiado` tras cada modificación."""

    cambiado = Signal()
    COLUMNAS = ["Comentario", "Uds.", "Longitud", "Anchura", "Altura", "Parcial"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._medicion: Medicion | None = None
        self._cargando = False

        self.tabla = QTableWidget(0, len(self.COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(self.COLUMNAS)
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla.verticalHeader().setDefaultSectionSize(22)
        self.tabla.itemChanged.connect(self._celda_cambiada)

        self.total = QLabel()
        self.boton_anadir = QPushButton("Añadir línea")
        self.boton_quitar = QPushButton("Quitar línea")
        self.boton_anadir.clicked.connect(self.anadir_linea)
        self.boton_quitar.clicked.connect(self.quitar_linea)

        self.barra = QHBoxLayout()
        self.barra.addWidget(self.boton_anadir)
        self.barra.addWidget(self.boton_quitar)
        self.barra.addStretch()
        self.barra.addWidget(self.total)

        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addLayout(self.barra)
        capa.addWidget(self.tabla)
        self.set_medicion(None)

    def set_medicion(self, medicion: Medicion | None) -> None:
        self._medicion = medicion
        self._cargando = True
        self.tabla.setRowCount(0)
        activa = medicion is not None
        self.tabla.setEnabled(activa)
        self.boton_anadir.setEnabled(activa)
        self.boton_quitar.setEnabled(activa)
        if medicion is not None:
            for linea in medicion.lineas:
                self._poner_fila(self.tabla.rowCount(), linea)
        self._cargando = False
        self._actualizar_total()

    def _poner_fila(self, fila: int, linea: LineaMedicion) -> None:
        self.tabla.insertRow(fila)
        self.tabla.setItem(fila, 0, celda(linea.comentario))
        for col, v in enumerate((linea.unidades, linea.longitud, linea.anchura, linea.altura), start=1):
            self.tabla.setItem(fila, col, celda("" if v is None else numero(v, 3), derecha=True))
        self.tabla.setItem(fila, 5, celda(numero(linea.parcial(), 3), editable=False, derecha=True))

    def _actualizar_total(self) -> None:
        if self._medicion is None:
            self.total.setText("")
        else:
            self.total.setText(f"Total: <b>{numero(self._medicion.total(), 3)}</b>")

    def anadir_linea(self) -> None:
        if self._medicion is None:
            return
        fila = self.tabla.currentRow() + 1 if self.tabla.currentRow() >= 0 else len(self._medicion.lineas)
        self.insertar_linea(fila, LineaMedicion())
        self.tabla.setCurrentCell(fila, 0)
        self.tabla.editItem(self.tabla.item(fila, 0))

    def insertar_linea(self, fila: int, linea: LineaMedicion) -> None:
        if self._medicion is None:
            return
        if not self._medicion.lineas and self._medicion.total_directo:
            # al pasar de total directo a líneas, conservar la cantidad que había
            self._medicion.lineas.append(LineaMedicion("Cantidad anterior", self._medicion.total_directo))
            self._medicion.total_directo = 0.0
            self.set_medicion(self._medicion)
            fila = len(self._medicion.lineas)
        self._medicion.lineas.insert(fila, linea)
        self._cargando = True
        self._poner_fila(fila, linea)
        self._cargando = False
        self._actualizar_total()
        self.cambiado.emit()

    def quitar_linea(self) -> None:
        fila = self.tabla.currentRow()
        if self._medicion is None or not (0 <= fila < len(self._medicion.lineas)):
            return
        del self._medicion.lineas[fila]
        self.tabla.removeRow(fila)
        self._actualizar_total()
        self.cambiado.emit()

    def _celda_cambiada(self, item: QTableWidgetItem) -> None:
        if self._cargando or self._medicion is None:
            return
        fila, col = item.row(), item.column()
        linea = self._medicion.lineas[fila]
        if col == 0:
            linea.comentario = item.text()
        elif 1 <= col <= 4:
            atributo = ("unidades", "longitud", "anchura", "altura")[col - 1]
            try:
                valor = leer_numero(item.text())
            except ValueError:
                valor = getattr(linea, atributo)
            setattr(linea, atributo, valor)
            self._cargando = True
            item.setText("" if valor is None else numero(valor, 3))
            self._cargando = False
        else:
            return
        self._cargando = True
        self.tabla.item(fila, 5).setText(numero(linea.parcial(), 3))
        self._cargando = False
        self._actualizar_total()
        self.cambiado.emit()
