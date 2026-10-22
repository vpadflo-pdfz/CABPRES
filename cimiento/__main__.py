import sys

from PySide6.QtWidgets import QApplication

from .gui.ventana import VentanaPrincipal


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Cimiento")
    app.setStyle("Fusion")
    ventana = VentanaPrincipal()
    if len(sys.argv) > 1:
        ventana.abrir(sys.argv[1])
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
