@echo off
rem Registra el consejo en la aplicacion de escritorio de Claude (Windows).
cd /d "%~dp0"
if not exist .venv (
  echo Primero ejecute iniciar.bat
  pause
  exit /b 1
)
.venv\Scripts\python -m pip install --quiet --disable-pip-version-check -r requirements.txt
.venv\Scripts\python -m council.instalar_claude
pause
