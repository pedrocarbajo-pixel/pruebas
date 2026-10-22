#!/usr/bin/env bash
# Registra el consejo en la aplicación de escritorio de Claude (macOS y Linux).
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Primero ejecute: bash iniciar.sh"
  exit 1
fi
.venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt
.venv/bin/python -m council.instalar_claude
