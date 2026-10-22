"""Ventana principal: árbol de presupuesto con columnas de certificación."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTabWidget, QToolButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import bc3, calculo, informes, proyecto
from ..informes import numero
from ..modelo import (
    CAPITULO, MANO_OBRA, MAQUINARIA, MATERIAL, PARTIDA, Concepto, LineaMedicion, Medicion, Obra,
)
from .dialogos import DialogoFecha, DialogoInforme, DialogoParametros
from .tablas import TablaMedicion, celda, leer_numero

(COL_CODIGO, COL_UD, COL_RESUMEN, COL_CANTIDAD, COL_PRECIO, COL_IMPORTE,
 COL_ANTERIOR, COL_ACTUAL, COL_ORIGEN, COL_IMP_ACTUAL, COL_IMP_ORIGEN, COL_PORCENTAJE) = range(12)
CABECERAS = ["Código", "Ud", "Resumen", "Cantidad", "Precio", "Importe",
             "Cert. anterior", "Cert. actual", "Cert. origen", "Imp. actual", "Imp. origen", "%"]
COLUMNAS_CERT = range(COL_ANTERIOR, COL_PORCENTAJE + 1)
ROL = Qt.UserRole
FILTRO_OBRA = "Obra de CABPRES (*.obra)"
FILTRO_BC3 = "FIEBDC-3 (*.bc3 *.BC3)"
NOMBRES_NATURALEZA = {MANO_OBRA: "Mano de obra", MAQUINARIA: "Maquinaria", MATERIAL: "Material",
                      PARTIDA: "Partida", CAPITULO: "Capítulo"}
COLOR_CERT = QColor("#eef6ee")


class VentanaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.obra = Obra.nueva()
        self.ruta: Path | None = None
        self.modificado = False
        self._actualizando = False
        self._cargando_desc = False
        self.ajustes = QSettings("CABPRES", "CABPRES")

        self._crear_arbol()
        self._crear_paneles()
        self._crear_acciones()

        divisor = QSplitter(Qt.Vertical)
        divisor.addWidget(self.arbol)
        divisor.addWidget(self.pestanas)
        divisor.setSizes([500, 260])
        self.setCentralWidget(divisor)
        self.etiqueta_totales = QLabel()
        self.statusBar().addPermanentWidget(self.etiqueta_totales)
        self.resize(1400, 850)
        self.reconstruir()

    # --- construcción de la interfaz ------------------------------------------
    def _crear_arbol(self) -> None:
        self.arbol = QTreeWidget()
        self.arbol.setColumnCount(len(CABECERAS))
        self.arbol.setHeaderLabels(CABECERAS)
        self.arbol.setAlternatingRowColors(True)
        self.arbol.setUniformRowHeights(True)
        self.arbol.setEditTriggers(QTreeWidget.NoEditTriggers)
        cabecera = self.arbol.header()
        cabecera.setSectionResizeMode(COL_RESUMEN, QHeaderView.Stretch)
        cabecera.setStretchLastSection(False)
        for col, ancho in ((COL_CODIGO, 150), (COL_UD, 45)):
            self.arbol.setColumnWidth(col, ancho)
        for col in range(COL_CANTIDAD, COL_PORCENTAJE + 1):
            self.arbol.setColumnWidth(col, 95)
        self.arbol.currentItemChanged.connect(lambda *_: self.actualizar_paneles())
        self.arbol.itemDoubleClicked.connect(self._editar_celda)
        self.arbol.itemChanged.connect(self._celda_arbol_cambiada)
        self.arbol.setContextMenuPolicy(Qt.CustomContextMenu)
        self.arbol.customContextMenuRequested.connect(self._menu_contextual)

    def _crear_paneles(self) -> None:
        self.pestanas = QTabWidget()

        self.tabla_medicion = TablaMedicion()
        self.tabla_medicion.cambiado.connect(self._medicion_cambiada)
        self.pestanas.addTab(self.tabla_medicion, "Medición")

        panel_cert = QWidget()
        self.tabla_cert = TablaMedicion()
        self.tabla_cert.cambiado.connect(self._medicion_cambiada)
        self.info_cert = QLabel()
        self.boton_pendiente = QPushButton("Certificar todo lo pendiente")
        self.boton_pendiente.clicked.connect(self.certificar_pendiente)
        self.boton_copiar_lineas = QPushButton("Copiar líneas de la medición")
        self.boton_copiar_lineas.setToolTip("Añade las líneas de medición del presupuesto para marcar lo ejecutado")
        self.boton_copiar_lineas.clicked.connect(self.copiar_lineas_presupuesto)
        barra = QHBoxLayout()
        barra.addWidget(self.info_cert)
        barra.addStretch()
        barra.addWidget(self.boton_copiar_lineas)
        barra.addWidget(self.boton_pendiente)
        capa = QVBoxLayout(panel_cert)
        capa.addLayout(barra)
        capa.addWidget(self.tabla_cert)
        self.indice_pestana_cert = self.pestanas.addTab(panel_cert, "Certificación")

        panel_desc = QWidget()
        self.tabla_desc = QTableWidget(0, 7)
        self.tabla_desc.setHorizontalHeaderLabels(
            ["Código", "Ud", "Resumen", "Tipo", "Rendimiento", "Precio", "Importe"])
        self.tabla_desc.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabla_desc.verticalHeader().setDefaultSectionSize(22)
        self.tabla_desc.itemChanged.connect(self._celda_desc_cambiada)
        boton_anadir = QToolButton()
        boton_anadir.setText("Añadir")
        boton_anadir.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(boton_anadir)
        for naturaleza in (MANO_OBRA, MAQUINARIA, MATERIAL, PARTIDA):
            menu.addAction(NOMBRES_NATURALEZA[naturaleza], lambda n=naturaleza: self.anadir_descompuesto(n))
        boton_anadir.setMenu(menu)
        boton_quitar = QPushButton("Quitar")
        boton_quitar.clicked.connect(self.quitar_descompuesto)
        barra = QHBoxLayout()
        barra.addWidget(boton_anadir)
        barra.addWidget(boton_quitar)
        barra.addStretch()
        capa = QVBoxLayout(panel_desc)
        capa.addLayout(barra)
        capa.addWidget(self.tabla_desc)
        self.panel_desc = panel_desc
        self.pestanas.addTab(panel_desc, "Descomposición")

        self.texto = QPlainTextEdit()
        self.texto.textChanged.connect(self._texto_cambiado)
        self.pestanas.addTab(self.texto, "Texto")

    def _accion(self, texto: str, funcion, atajo=None) -> QAction:
        accion = QAction(texto, self)
        accion.triggered.connect(funcion)
        if atajo:
            accion.setShortcut(QKeySequence(atajo))
        return accion

    def _crear_acciones(self) -> None:
        menu = self.menuBar().addMenu("&Archivo")
        menu.addAction(self._accion("&Nueva obra", self.nueva, QKeySequence.New))
        menu.addAction(self._accion("&Abrir…", self.abrir, QKeySequence.Open))
        menu.addAction(self._accion("&Guardar", self.guardar, QKeySequence.Save))
        menu.addAction(self._accion("Guardar &como…", self.guardar_como, QKeySequence.SaveAs))
        menu.addSeparator()
        menu.addAction(self._accion("&Importar BC3…", self.importar_bc3))
        menu.addAction(self._accion("&Exportar BC3…", self.exportar_bc3))
        menu.addSeparator()
        menu.addAction(self._accion("Datos de la &obra…", self.editar_parametros))
        menu.addSeparator()
        menu.addAction(self._accion("&Salir", self.close, QKeySequence.Quit))

        self.accion_capitulo = self._accion("Nuevo capítulo", lambda: self.anadir(CAPITULO), "Ctrl+Shift+N")
        self.accion_partida = self._accion("Nueva partida", lambda: self.anadir(PARTIDA), "Ctrl+Shift+P")
        self.accion_borrar = self._accion("Eliminar", self.eliminar, "Ctrl+Del")
        self.accion_subir = self._accion("Subir", lambda: self.mover(-1), "Ctrl+Up")
        self.accion_bajar = self._accion("Bajar", lambda: self.mover(1), "Ctrl+Down")
        self.accion_editar = self._accion("Editar celda", self._editar_celda_actual, "F2")
        menu = self.menuBar().addMenu("&Presupuesto")
        for a in (self.accion_capitulo, self.accion_partida, self.accion_borrar, self.accion_subir,
                  self.accion_bajar, self.accion_editar):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(self._accion("Informe de presupuesto…", self.informe_presupuesto))

        menu = self.menuBar().addMenu("&Certificación")
        menu.addAction(self._accion("&Nueva certificación…", self.nueva_certificacion))
        menu.addAction(self._accion("Cambiar &fecha…", self.cambiar_fecha_certificacion))
        menu.addAction(self._accion("&Borrar certificación", self.borrar_certificacion))
        menu.addSeparator()
        menu.addAction(self._accion("&Informe de certificación…", self.informe_certificacion, "Ctrl+I"))
        menu.addAction(self._accion("&Exportar certificación a BC3…", self.exportar_certificacion_bc3))
        menu.addAction(self._accion("I&mportar certificación de BC3…", self.importar_certificacion_bc3))

        barra = self.addToolBar("Principal")
        barra.setObjectName("barra_principal")
        barra.addAction(self.accion_capitulo)
        barra.addAction(self.accion_partida)
        barra.addAction(self.accion_borrar)
        barra.addAction(self.accion_subir)
        barra.addAction(self.accion_bajar)
        barra.addSeparator()
        barra.addWidget(QLabel(" Certificación: "))
        self.combo_cert = QComboBox()
        self.combo_cert.setMinimumWidth(220)
        self.combo_cert.currentIndexChanged.connect(lambda _: self._cert_seleccionada())
        barra.addWidget(self.combo_cert)
        barra.addAction(self._accion("Nueva certificación", self.nueva_certificacion))
        barra.addAction(self._accion("Informe", self.informe_certificacion))

    # --- estado ---------------------------------------------------------------
    @property
    def numero_cert(self) -> int | None:
        return self.combo_cert.currentData()

    def _marcar_modificado(self) -> None:
        self.modificado = True
        self._actualizar_titulo()

    def _actualizar_titulo(self) -> None:
        nombre = self.ruta.name if self.ruta else "Sin título"
        self.setWindowTitle(f"{nombre}{' *' if self.modificado else ''} — CABPRES")

    def _rellenar_combo_cert(self, seleccionar: int | None = None) -> None:
        self.combo_cert.blockSignals(True)
        self.combo_cert.clear()
        self.combo_cert.addItem("(ninguna)", None)
        for cert in sorted(self.obra.certificaciones, key=lambda c: c.numero):
            self.combo_cert.addItem(f"N.º {cert.numero} — {cert.fecha.strftime('%d/%m/%Y')}", cert.numero)
        indice = self.combo_cert.findData(seleccionar) if seleccionar is not None else -1
        self.combo_cert.setCurrentIndex(indice if indice >= 0 else self.combo_cert.count() - 1)
        self.combo_cert.blockSignals(False)
        self._cert_seleccionada()

    def _cert_seleccionada(self) -> None:
        hay = self.numero_cert is not None
        for col in COLUMNAS_CERT:
            self.arbol.setColumnHidden(col, not hay)
        self.pestanas.setTabEnabled(self.indice_pestana_cert, hay)
        self.refrescar()

    # --- árbol ----------------------------------------------------------------
    def _referencia(self, item: QTreeWidgetItem | None) -> tuple[str | None, int | None, str]:
        """(padre, índice, código) del elemento del árbol."""
        if item is None:
            return None, None, self.obra.raiz
        padre, indice = item.data(COL_CODIGO, ROL)
        if padre is None:
            return None, None, self.obra.raiz
        return padre, indice, self.obra.conceptos[padre].hijos[indice].codigo

    def reconstruir(self, seleccionar: tuple[str | None, int | None] | None = None) -> None:
        """Vuelve a crear el árbol (tras cambios de estructura)."""
        expandidos = set()
        if self.arbol.topLevelItemCount():
            def recoger(item):
                if item.isExpanded():
                    expandidos.add(self._referencia(item)[2])
                for i in range(item.childCount()):
                    recoger(item.child(i))
            recoger(self.arbol.topLevelItem(0))
        else:
            expandidos.add(self.obra.raiz)
        if seleccionar is None:
            actual = self.arbol.currentItem()
            seleccionar = self._referencia(actual)[:2] if actual else (None, None)

        self._actualizando = True
        self.arbol.blockSignals(True)
        self.arbol.clear()
        raiz = QTreeWidgetItem([self.obra.raiz])
        raiz.setData(COL_CODIGO, ROL, (None, None))
        self.arbol.addTopLevelItem(raiz)
        elegido = raiz

        def construir(item: QTreeWidgetItem, codigo: str, visitando: frozenset[str]):
            nonlocal elegido
            for i, d in enumerate(self.obra.conceptos[codigo].hijos):
                hijo = self.obra.conceptos.get(d.codigo)
                if hijo is None or d.codigo in visitando:
                    continue
                nuevo = QTreeWidgetItem(item)
                nuevo.setData(COL_CODIGO, ROL, (codigo, i))
                nuevo.setFlags(nuevo.flags() | Qt.ItemIsEditable)
                if (codigo, i) == seleccionar:
                    elegido = nuevo
                if hijo.es_agrupador:
                    construir(nuevo, d.codigo, visitando | {d.codigo})
                    nuevo.setExpanded(d.codigo in expandidos)

        raiz.setFlags(raiz.flags() | Qt.ItemIsEditable)
        construir(raiz, self.obra.raiz, frozenset({self.obra.raiz}))
        raiz.setExpanded(True)
        self._actualizando = False
        self.refrescar()
        self.arbol.setCurrentItem(elegido)
        self.arbol.blockSignals(False)
        self.actualizar_paneles()
        self._actualizar_titulo()

    def refrescar(self) -> None:
        """Recalcula y actualiza los textos de todo el árbol sin cambiar su estructura."""
        if not self.arbol.topLevelItemCount():
            return
        self._actualizando = True
        n = self.numero_cert
        negrita = QFont()
        negrita.setBold(True)
        fondo_cert = QBrush(COLOR_CERT)
        dp = self.obra.parametros.decimales_precio

        def pintar(item: QTreeWidgetItem):
            padre, indice, codigo = self._referencia(item)
            c = self.obra.conceptos[codigo]
            item.setText(COL_CODIGO, codigo)
            item.setText(COL_UD, c.unidad)
            item.setText(COL_RESUMEN, c.resumen)
            if padre is None:
                item.setText(COL_IMPORTE, numero(calculo.precio(self.obra, codigo)))
                if n is not None:
                    total = calculo.certificado_obra(self.obra, n)
                    self._pintar_cert(item, total, calculo.precio(self.obra, codigo), False)
            else:
                pu = calculo.precio(self.obra, codigo)
                imp = calculo.importe(self.obra, padre, indice)
                if c.es_agrupador:
                    item.setText(COL_CANTIDAD, "")
                    item.setText(COL_PRECIO, "")
                else:
                    item.setText(COL_CANTIDAD, numero(calculo.cantidad(self.obra, padre, indice), 3))
                    item.setText(COL_PRECIO, numero(pu, dp))
                item.setText(COL_IMPORTE, numero(imp))
                if n is not None:
                    cer = calculo.certificado(self.obra, padre, indice, n)
                    self._pintar_cert(item, cer, imp, not c.es_agrupador)
            for col in range(COL_CANTIDAD, COL_PORCENTAJE + 1):
                item.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
            if c.es_agrupador:
                for col in range(len(CABECERAS)):
                    item.setFont(col, negrita)
            for col in COLUMNAS_CERT:
                item.setBackground(col, fondo_cert)
            for i in range(item.childCount()):
                pintar(item.child(i))

        pintar(self.arbol.topLevelItem(0))
        self._actualizando = False
        self._actualizar_totales()

    def _pintar_cert(self, item: QTreeWidgetItem, cer: calculo.Certificado, importe_pres: float,
                     con_cantidades: bool) -> None:
        if con_cantidades:
            item.setText(COL_ANTERIOR, numero(cer.anterior, 3))
            item.setText(COL_ACTUAL, numero(cer.actual, 3))
            item.setText(COL_ORIGEN, numero(cer.origen, 3))
        else:
            for col in (COL_ANTERIOR, COL_ACTUAL, COL_ORIGEN):
                item.setText(col, "")
        item.setText(COL_IMP_ACTUAL, numero(cer.importe_actual))
        item.setText(COL_IMP_ORIGEN, numero(cer.importe_origen))
        porcentaje = 100 * cer.importe_origen / importe_pres if importe_pres else 0.0
        item.setText(COL_PORCENTAJE, numero(porcentaje))
        exceso = importe_pres >= 0 and cer.importe_origen > importe_pres + 0.005
        item.setForeground(COL_PORCENTAJE, QBrush(QColor("#c0392b") if exceso else QColor("#000")))

    def _actualizar_totales(self) -> None:
        div = self.obra.parametros.divisa
        pem = calculo.precio(self.obra, self.obra.raiz)
        texto = f"PEM: <b>{numero(pem)} {div}</b>"
        if self.numero_cert is not None:
            total = calculo.certificado_obra(self.obra, self.numero_cert)
            texto += (f" &nbsp;|&nbsp; Cert. {self.numero_cert}: <b>{numero(total.importe_actual)}</b>"
                      f" &nbsp;|&nbsp; A origen: <b>{numero(total.importe_origen)}</b>"
                      f" ({numero(100 * total.importe_origen / pem if pem else 0)} %)")
        self.etiqueta_totales.setText(texto)

    def _editable(self, item: QTreeWidgetItem, col: int) -> bool:
        padre, indice, codigo = self._referencia(item)
        c = self.obra.conceptos[codigo]
        if col in (COL_CODIGO, COL_RESUMEN):
            return True
        if padre is None:
            return False
        if col == COL_UD:
            return not c.es_agrupador
        if col == COL_PRECIO:
            return not c.es_agrupador and not c.hijos
        if col == COL_CANTIDAD:
            med = self.obra.mediciones.get((padre, codigo))
            return not c.es_agrupador and (med is None or not med.lineas)
        if col == COL_ACTUAL and self.numero_cert is not None:
            cert = self.obra.certificacion(self.numero_cert)
            med = cert.mediciones.get((padre, codigo))
            return not c.es_agrupador and (med is None or not med.lineas)
        return False

    def _editar_celda(self, item: QTreeWidgetItem, col: int) -> None:
        if self._editable(item, col):
            self.arbol.editItem(item, col)
        elif col == COL_CANTIDAD:
            self.pestanas.setCurrentWidget(self.tabla_medicion)
        elif col in (COL_ANTERIOR, COL_ACTUAL, COL_ORIGEN) and self.numero_cert is not None:
            self.pestanas.setCurrentIndex(self.indice_pestana_cert)

    def _editar_celda_actual(self) -> None:
        item = self.arbol.currentItem()
        if item is not None:
            self._editar_celda(item, max(self.arbol.currentColumn(), 0))

    def _celda_arbol_cambiada(self, item: QTreeWidgetItem, col: int) -> None:
        if self._actualizando:
            return
        padre, indice, codigo = self._referencia(item)
        c = self.obra.conceptos[codigo]
        texto = item.text(col)
        try:
            if col == COL_CODIGO:
                if texto.strip().rstrip("#") != codigo:
                    self.obra.renombrar(codigo, texto)
                    self._marcar_modificado()
                # no reconstruir dentro de la señal del propio elemento
                QTimer.singleShot(0, self.reconstruir)
                return
            if col == COL_RESUMEN:
                c.resumen = texto
            elif col == COL_UD:
                c.unidad = texto
            elif col == COL_PRECIO:
                c.precio = leer_numero(texto) or 0.0
            elif col == COL_CANTIDAD:
                valor = leer_numero(texto) or 0.0
                calculo.medicion_de(self.obra, padre, codigo).total_directo = valor
                self.obra.conceptos[padre].hijos[indice].rendimiento = valor
            elif col == COL_ACTUAL:
                cert = self.obra.certificacion(self.numero_cert)
                cert.mediciones[(padre, codigo)] = Medicion(total_directo=leer_numero(texto) or 0.0)
            else:
                return
        except ValueError as e:
            QMessageBox.warning(self, "Valor no válido", str(e))
        self._marcar_modificado()
        self.refrescar()
        self.actualizar_paneles()

    def _menu_contextual(self, posicion) -> None:
        menu = QMenu(self)
        for a in (self.accion_capitulo, self.accion_partida, self.accion_borrar,
                  self.accion_subir, self.accion_bajar):
            menu.addAction(a)
        menu.exec(self.arbol.viewport().mapToGlobal(posicion))

    # --- paneles inferiores ------------------------------------------------------
    def actualizar_paneles(self) -> None:
        padre, indice, codigo = self._referencia(self.arbol.currentItem())
        c = self.obra.conceptos.get(codigo)
        es_partida = padre is not None and c is not None and not c.es_agrupador

        self.tabla_medicion.set_medicion(
            calculo.medicion_de(self.obra, padre, codigo) if es_partida else None)

        n = self.numero_cert
        cert = self.obra.certificacion(n) if n is not None else None
        if cert is not None and es_partida:
            self.tabla_cert.set_medicion(cert.mediciones.setdefault((padre, codigo), Medicion()))
            self._actualizar_info_cert()
        else:
            self.tabla_cert.set_medicion(None)
            self.info_cert.setText("Seleccione una partida." if cert is not None else "")
        self.boton_pendiente.setEnabled(cert is not None and es_partida)
        self.boton_copiar_lineas.setEnabled(cert is not None and es_partida)

        self._rellenar_descomposicion(c if (c is not None and not c.es_agrupador) else None)
        self.panel_desc.setEnabled(c is not None and not c.es_agrupador)
        self.texto.blockSignals(True)
        self.texto.setPlainText(c.texto if c else "")
        self.texto.blockSignals(False)

    def _actualizar_info_cert(self) -> None:
        padre, indice, codigo = self._referencia(self.arbol.currentItem())
        if padre is None or self.numero_cert is None:
            return
        cer = calculo.certificado(self.obra, padre, indice, self.numero_cert)
        presupuesto = calculo.cantidad(self.obra, padre, indice)
        ud = self.obra.conceptos[codigo].unidad
        pendiente = presupuesto - cer.origen
        self.info_cert.setText(
            f"Presupuesto: <b>{numero(presupuesto, 3)}</b> {ud} &nbsp; Anterior: <b>{numero(cer.anterior, 3)}</b>"
            f" &nbsp; Origen: <b>{numero(cer.origen, 3)}</b> &nbsp; Pendiente: "
            f"<b style='color:{'#c0392b' if pendiente < -0.0005 else '#000'}'>{numero(pendiente, 3)}</b>")

    def _medicion_cambiada(self) -> None:
        padre, indice, codigo = self._referencia(self.arbol.currentItem())
        if padre is not None and self.sender() is self.tabla_medicion:
            # mantener el rendimiento del ~D igual a la medición (lo usa el BC3)
            self.obra.conceptos[padre].hijos[indice].rendimiento = calculo.cantidad(self.obra, padre, indice)
        self._marcar_modificado()
        self.refrescar()
        self._actualizar_info_cert()

    def certificar_pendiente(self) -> None:
        padre, indice, codigo = self._referencia(self.arbol.currentItem())
        if padre is None or self.numero_cert is None:
            return
        pendiente = calculo.medicion_pendiente(self.obra, padre, codigo, self.numero_cert)
        cert = self.obra.certificacion(self.numero_cert)
        actual = cert.mediciones.get((padre, codigo))
        ya = actual.total() if actual else 0.0
        if abs(pendiente - ya) < 1e-9:
            return
        self.tabla_cert.insertar_linea(len(actual.lineas) if actual else 0,
                                       LineaMedicion("Resto pendiente", pendiente - ya))

    def copiar_lineas_presupuesto(self) -> None:
        padre, indice, codigo = self._referencia(self.arbol.currentItem())
        med = self.obra.mediciones.get((padre, codigo)) if padre else None
        if med is None or not med.lineas:
            QMessageBox.information(self, "Certificación", "La partida no tiene líneas de medición.")
            return
        cert = self.obra.certificacion(self.numero_cert)
        destino = cert.mediciones.setdefault((padre, codigo), Medicion())
        for linea in med.lineas:
            self.tabla_cert.insertar_linea(len(destino.lineas), LineaMedicion(
                linea.comentario, linea.unidades, linea.longitud, linea.anchura, linea.altura, linea.tipo))

    def _rellenar_descomposicion(self, c: Concepto | None) -> None:
        self._cargando_desc = True
        self.tabla_desc.setRowCount(0)
        if c is not None:
            for i, d in enumerate(c.hijos):
                h = self.obra.conceptos[d.codigo]
                pu = calculo.precio(self.obra, d.codigo)
                self.tabla_desc.insertRow(i)
                self.tabla_desc.setItem(i, 0, celda(d.codigo))
                self.tabla_desc.setItem(i, 1, celda(h.unidad))
                self.tabla_desc.setItem(i, 2, celda(h.resumen))
                self.tabla_desc.setItem(i, 3, celda(NOMBRES_NATURALEZA.get(h.naturaleza, ""), editable=False))
                self.tabla_desc.setItem(i, 4, celda(numero(d.rendimiento, 3), derecha=True))
                self.tabla_desc.setItem(i, 5, celda(numero(pu, self.obra.parametros.decimales_precio),
                                                    editable=not h.hijos, derecha=True))
                self.tabla_desc.setItem(i, 6, celda(numero(pu * d.factor * d.rendimiento), editable=False,
                                                    derecha=True))
        self._cargando_desc = False

    def _celda_desc_cambiada(self, item) -> None:
        if self._cargando_desc:
            return
        _, _, codigo = self._referencia(self.arbol.currentItem())
        c = self.obra.conceptos[codigo]
        d = c.hijos[item.row()]
        h = self.obra.conceptos[d.codigo]
        try:
            col = item.column()
            if col == 0:
                self.obra.renombrar(d.codigo, item.text())
            elif col == 1:
                h.unidad = item.text()
            elif col == 2:
                h.resumen = item.text()
            elif col == 4:
                d.rendimiento = leer_numero(item.text()) or 0.0
            elif col == 5:
                h.precio = leer_numero(item.text()) or 0.0
        except ValueError as e:
            QMessageBox.warning(self, "Valor no válido", str(e))
        self._marcar_modificado()
        self.refrescar()
        self._rellenar_descomposicion(c)

    def anadir_descompuesto(self, naturaleza: str) -> None:
        _, _, codigo = self._referencia(self.arbol.currentItem())
        c = self.obra.conceptos[codigo]
        if c.es_agrupador:
            return
        prefijo = {MANO_OBRA: "MO", MAQUINARIA: "MQ", MATERIAL: "MT"}.get(naturaleza, "P")
        nuevo = Concepto(self.obra.codigo_libre(prefijo), NOMBRES_NATURALEZA[naturaleza],
                         {MANO_OBRA: "h", MAQUINARIA: "h"}.get(naturaleza, "ud"), naturaleza=naturaleza)
        self.obra.anadir_hijo(codigo, nuevo)
        self._marcar_modificado()
        self.refrescar()
        self._rellenar_descomposicion(c)
        fila = len(c.hijos) - 1
        self.tabla_desc.setCurrentCell(fila, 2)
        self.tabla_desc.editItem(self.tabla_desc.item(fila, 2))

    def quitar_descompuesto(self) -> None:
        _, _, codigo = self._referencia(self.arbol.currentItem())
        fila = self.tabla_desc.currentRow()
        c = self.obra.conceptos[codigo]
        if c.es_agrupador or not 0 <= fila < len(c.hijos):
            return
        self.obra.quitar_hijo(codigo, fila)
        self._marcar_modificado()
        self.refrescar()
        self._rellenar_descomposicion(c)

    def _texto_cambiado(self) -> None:
        _, _, codigo = self._referencia(self.arbol.currentItem())
        if codigo in self.obra.conceptos:
            self.obra.conceptos[codigo].texto = self.texto.toPlainText()
            self._marcar_modificado()

    # --- edición de estructura ---------------------------------------------------
    def anadir(self, naturaleza: str) -> None:
        padre, indice, codigo = self._referencia(self.arbol.currentItem())
        c = self.obra.conceptos[codigo]
        if c.es_agrupador:
            destino, posicion = codigo, len(c.hijos)
        else:
            destino, posicion = padre, indice + 1
        if naturaleza == CAPITULO:
            nuevo = Concepto(self.obra.codigo_libre("C"), "Nuevo capítulo", naturaleza=CAPITULO)
        else:
            nuevo = Concepto(self.obra.codigo_libre("P"), "Nueva partida", "ud", naturaleza=PARTIDA)
        self.obra.anadir_hijo(destino, nuevo, rendimiento=1.0 if naturaleza == CAPITULO else 0.0)
        hijos = self.obra.conceptos[destino].hijos
        hijos.insert(posicion, hijos.pop())
        self._marcar_modificado()
        self.reconstruir(seleccionar=(destino, posicion))
        self.arbol.currentItem().parent().setExpanded(True)
        self.arbol.editItem(self.arbol.currentItem(), COL_RESUMEN)

    def eliminar(self) -> None:
        padre, indice, codigo = self._referencia(self.arbol.currentItem())
        if padre is None:
            return
        c = self.obra.conceptos[codigo]
        if QMessageBox.question(self, "Eliminar", f"¿Eliminar «{codigo} {c.resumen}» y todo su contenido?"
                                ) != QMessageBox.Yes:
            return
        self.obra.quitar_hijo(padre, indice)
        self._marcar_modificado()
        hermanos = len(self.obra.conceptos[padre].hijos)
        self.reconstruir(seleccionar=(padre, min(indice, hermanos - 1)) if hermanos else None)

    def mover(self, desplazamiento: int) -> None:
        padre, indice, _ = self._referencia(self.arbol.currentItem())
        if padre is None:
            return
        nuevo = self.obra.mover_hijo(padre, indice, desplazamiento)
        if nuevo != indice:
            self._marcar_modificado()
            self.reconstruir(seleccionar=(padre, nuevo))

    # --- certificaciones --------------------------------------------------------
    def nueva_certificacion(self) -> None:
        ultima = max(self.obra.certificaciones, key=lambda c: c.numero, default=None)
        from datetime import date
        dialogo = DialogoFecha("Nueva certificación", date.today(), self)
        if not dialogo.exec():
            return
        if ultima and dialogo.valor() < ultima.fecha:
            QMessageBox.warning(self, "Fecha", "La fecha es anterior a la de la última certificación.")
        cert = self.obra.nueva_certificacion(dialogo.valor())
        self._marcar_modificado()
        self._rellenar_combo_cert(cert.numero)
        self.actualizar_paneles()

    def cambiar_fecha_certificacion(self) -> None:
        cert = self.obra.certificacion(self.numero_cert) if self.numero_cert else None
        if cert is None:
            return
        dialogo = DialogoFecha(f"Certificación n.º {cert.numero}", cert.fecha, self)
        if dialogo.exec():
            cert.fecha = dialogo.valor()
            self._marcar_modificado()
            self._rellenar_combo_cert(cert.numero)

    def borrar_certificacion(self) -> None:
        n = self.numero_cert
        if n is None:
            return
        if n != max(c.numero for c in self.obra.certificaciones):
            QMessageBox.warning(self, "Certificación", "Solo se puede borrar la última certificación.")
            return
        if QMessageBox.question(self, "Borrar", f"¿Borrar la certificación n.º {n}?") != QMessageBox.Yes:
            return
        self.obra.borrar_certificacion(n)
        self._marcar_modificado()
        self._rellenar_combo_cert()
        self.actualizar_paneles()

    def informe_certificacion(self) -> None:
        n = self.numero_cert
        if n is None:
            QMessageBox.information(self, "Informe", "Seleccione una certificación.")
            return
        DialogoInforme(f"Certificación n.º {n}", informes.certificacion(self.obra, n),
                       self._nombre_base() + f" - Certificación {n}.pdf", horizontal=True, parent=self).exec()

    def informe_presupuesto(self) -> None:
        DialogoInforme("Presupuesto", informes.presupuesto(self.obra),
                       self._nombre_base() + " - Presupuesto.pdf", parent=self).exec()

    def exportar_certificacion_bc3(self) -> None:
        n = self.numero_cert
        if n is None:
            QMessageBox.information(self, "Exportar", "Seleccione una certificación.")
            return
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar certificación",
                                              self._nombre_base() + f" - Cert {n}.bc3", FILTRO_BC3)
        if ruta:
            bc3.escribir(self.obra, ruta, certificacion=n)

    def importar_certificacion_bc3(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Importar certificación", self._carpeta(), FILTRO_BC3)
        if not ruta:
            return
        try:
            cert = bc3.importar_certificacion(self.obra, ruta)
        except (bc3.ErrorBC3, OSError) as e:
            QMessageBox.critical(self, "Importar certificación", str(e))
            return
        self._marcar_modificado()
        self._rellenar_combo_cert(cert.numero)
        self.actualizar_paneles()

    # --- archivos ---------------------------------------------------------------
    def _nombre_base(self) -> str:
        carpeta = self._carpeta()
        nombre = self.ruta.stem if self.ruta else "Obra"
        return str(Path(carpeta) / nombre)

    def _carpeta(self) -> str:
        if self.ruta:
            return str(self.ruta.parent)
        return self.ajustes.value("carpeta", str(Path.home()))

    def _recordar_carpeta(self, ruta: str) -> None:
        self.ajustes.setValue("carpeta", str(Path(ruta).parent))

    def _descartar_cambios(self) -> bool:
        if not self.modificado:
            return True
        respuesta = QMessageBox.question(
            self, "Cambios sin guardar", "¿Guardar los cambios de la obra actual?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if respuesta == QMessageBox.Save:
            return self.guardar()
        return respuesta == QMessageBox.Discard

    def cargar(self, obra: Obra, ruta: Path | None) -> None:
        self.obra = obra
        self.ruta = ruta
        self.modificado = False
        self.arbol.clear()
        self._rellenar_combo_cert()
        self.reconstruir(seleccionar=(None, None))

    def nueva(self) -> None:
        if self._descartar_cambios():
            self.cargar(Obra.nueva(), None)

    def abrir(self, ruta: str | None = None) -> None:
        if not self._descartar_cambios():
            return
        if not ruta:
            ruta, _ = QFileDialog.getOpenFileName(self, "Abrir obra", self._carpeta(),
                                                  f"{FILTRO_OBRA};;{FILTRO_BC3}")
            if not ruta:
                return
        if ruta.lower().endswith(".bc3"):
            self.importar_bc3(ruta, preguntar=False)
            return
        try:
            obra = proyecto.abrir(ruta)
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.critical(self, "Abrir", f"No se pudo abrir el archivo:\n{e}")
            return
        self._recordar_carpeta(ruta)
        self.cargar(obra, Path(ruta))

    def guardar(self) -> bool:
        if self.ruta is None:
            return self.guardar_como()
        try:
            proyecto.guardar(self.obra, self.ruta)
        except OSError as e:
            QMessageBox.critical(self, "Guardar", f"No se pudo guardar:\n{e}")
            return False
        self.modificado = False
        self._actualizar_titulo()
        self.statusBar().showMessage("Guardado", 3000)
        return True

    def guardar_como(self) -> bool:
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar obra", self._nombre_base() + ".obra", FILTRO_OBRA)
        if not ruta:
            return False
        if not ruta.lower().endswith(".obra"):
            ruta += ".obra"
        self.ruta = Path(ruta)
        self._recordar_carpeta(ruta)
        return self.guardar()

    def importar_bc3(self, ruta: str | None = None, preguntar: bool = True) -> None:
        if preguntar and not self._descartar_cambios():
            return
        if not ruta:
            ruta, _ = QFileDialog.getOpenFileName(self, "Importar BC3", self._carpeta(), FILTRO_BC3)
            if not ruta:
                return
        try:
            obra, cabecera = bc3.leer(ruta)
        except (bc3.ErrorBC3, OSError) as e:
            QMessageBox.critical(self, "Importar BC3", str(e))
            return
        self._recordar_carpeta(ruta)
        self.cargar(obra, None)
        self.modificado = True
        self._actualizar_titulo()
        self.statusBar().showMessage(
            f"Importado {Path(ruta).name} ({len(obra.conceptos)} conceptos, programa: "
            f"{cabecera.get('programa') or 'desconocido'})", 8000)

    def exportar_bc3(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar BC3", self._nombre_base() + ".bc3", FILTRO_BC3)
        if ruta:
            bc3.escribir(self.obra, ruta)

    def editar_parametros(self) -> None:
        dialogo = DialogoParametros(self.obra, self)
        if dialogo.exec():
            dialogo.aplicar()
            self._marcar_modificado()
            self.refrescar()

    def closeEvent(self, evento) -> None:
        if self._descartar_cambios():
            evento.accept()
        else:
            evento.ignore()
