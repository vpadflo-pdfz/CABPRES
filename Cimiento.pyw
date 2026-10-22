"""Lanzador para Windows (doble clic, sin consola) y punto de entrada para PyInstaller."""
import sys

from cimiento.__main__ import main

sys.exit(main())
