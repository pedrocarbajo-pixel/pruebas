"""Punto de entrada del servidor MCP para la aplicación de Claude.

La aplicación de Claude lo arranca con una ruta absoluta y sin fijar el directorio de trabajo,
así que aquí se sitúa en la carpeta del proyecto (para leer .env y guardar en salidas/).
"""

import os
import sys
from pathlib import Path

carpeta = Path(__file__).resolve().parent
os.chdir(carpeta)
sys.path.insert(0, str(carpeta))

from council.mcp_servidor import main  # noqa: E402

main()
