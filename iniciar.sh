#!/usr/bin/env bash
# Iniciador del Consejo de LLM para macOS y Linux.
# Primera vez: crea el entorno, instala dependencias y prepara .env. Después: verifica y arranca.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Creando el entorno de Python (solo la primera vez)…"
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "Se ha creado el archivo .env. Ábralo, pegue sus claves de API y vuelva a ejecutar este iniciador."
  exit 0
fi

echo "Verificando la conexión con los proveedores…"
if ! .venv/bin/python -m council.verificar; then
  echo
  echo "Corrija .env según los mensajes anteriores y vuelva a ejecutar el iniciador."
  exit 1
fi

.venv/bin/python -m council.web
