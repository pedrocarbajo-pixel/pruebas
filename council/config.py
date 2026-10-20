"""Carga de la configuración local desde un archivo `.env`."""

from __future__ import annotations

import os
from pathlib import Path


def cargar_env(ruta: str | Path = ".env") -> list[str]:
    """Carga las variables `CLAVE=valor` del archivo indicado, si existe.

    Las variables ya definidas en el entorno tienen prioridad. Las líneas vacías, los
    comentarios (#) y las claves sin valor se ignoran. Devuelve los nombres cargados.
    """
    ruta = Path(ruta)
    if not ruta.is_file():
        return []
    cargadas = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = (parte.strip() for parte in linea.split("=", 1))
        if clave.startswith("export "):
            clave = clave[len("export "):].strip()
        valor = valor.strip('"').strip("'")
        if clave and valor and clave not in os.environ:
            os.environ[clave] = valor
            cargadas.append(clave)
    return cargadas
