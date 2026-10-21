@echo off
rem Iniciador del Consejo de LLM para Windows.
rem Primera vez: crea el entorno, instala dependencias y prepara .env. Despues: verifica y arranca.
setlocal
cd /d "%~dp0"

if not exist .venv (
  echo Creando el entorno de Python ^(solo la primera vez^)...
  py -3 -m venv .venv || python -m venv .venv || goto :sin_python
  .venv\Scripts\python -m pip install --quiet --upgrade pip
)
rem Instala lo que falte (p. ej., tras una actualizacion); si ya esta todo, termina en segundos.
.venv\Scripts\python -m pip install --quiet --disable-pip-version-check -r requirements.txt

if not exist .env (
  copy .env.example .env >nul
  echo.
  echo Se ha creado el archivo .env. Abralo con el Bloc de notas, pegue sus claves de API
  echo y vuelva a ejecutar este iniciador.
  pause
  exit /b 0
)

echo Verificando la conexion con los proveedores...
.venv\Scripts\python -m council.verificar
if errorlevel 1 (
  echo.
  echo Corrija .env segun los mensajes anteriores y vuelva a ejecutar el iniciador.
  pause
  exit /b 1
)

.venv\Scripts\python -m council.web
pause
exit /b 0

:sin_python
echo No se ha encontrado Python. Instale Python 3.10 o superior desde python.org
echo marcando la opcion "Add python.exe to PATH" y vuelva a ejecutar este iniciador.
pause
exit /b 1
