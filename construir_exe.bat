@echo off
rem Genera dist\CABPRES\CABPRES.exe (requiere Python 3.10+ instalado en Windows)
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --windowed --name CABPRES CABPRES.pyw
echo.
echo Listo: dist\CABPRES\CABPRES.exe
pause
