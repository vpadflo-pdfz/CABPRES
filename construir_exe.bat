@echo off
rem Genera dist\Cimiento\Cimiento.exe (requiere Python 3.10+ instalado en Windows)
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --windowed --name Cimiento Cimiento.pyw
echo.
echo Listo: dist\Cimiento\Cimiento.exe
pause
