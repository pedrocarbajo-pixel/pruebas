"""Registra el consejo como servidor MCP en la aplicación de escritorio de Claude.

Uso:  .venv/bin/python -m council.instalar_claude

Añade (o actualiza) la entrada «consejo-llm» en claude_desktop_config.json sin tocar el resto de
servidores configurados, y guarda antes una copia de seguridad del archivo.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

NOMBRE = "consejo-llm"


def ruta_configuracion() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"]) / "Claude/claude_desktop_config.json"
    return Path.home() / ".config/Claude/claude_desktop_config.json"


def registrar(configuracion: Path, python: Path, script: Path) -> Path | None:
    """Escribe la entrada del consejo y devuelve la ruta de la copia de seguridad (si había archivo)."""
    datos, copia = {}, None
    if configuracion.is_file():
        texto = configuracion.read_text(encoding="utf-8")
        datos = json.loads(texto) if texto.strip() else {}
        copia = configuracion.with_name(f"{configuracion.stem}.copia-{datetime.now():%Y%m%d-%H%M%S}.json")
        shutil.copy2(configuracion, copia)
    datos.setdefault("mcpServers", {})[NOMBRE] = {"command": str(python), "args": [str(script)]}
    configuracion.parent.mkdir(parents=True, exist_ok=True)
    configuracion.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return copia


def main() -> int:
    proyecto = Path(__file__).resolve().parent.parent
    python = Path(sys.executable)
    script = proyecto / "consejo_mcp.py"
    configuracion = ruta_configuracion()
    try:
        copia = registrar(configuracion, python, script)
    except json.JSONDecodeError as e:
        print(f"No se ha modificado nada: {configuracion} no es un JSON válido ({e}).")
        return 1
    print(f"Consejo registrado en la aplicación de Claude: {configuracion}")
    if copia:
        print(f"Copia de seguridad de la configuración anterior: {copia}")
    print("\nCierre por completo la aplicación de Claude (Cmd+Q) y vuelva a abrirla.")
    print("\nSi también usa Claude Code, regístrelo allí con:")
    print(f'  claude mcp add --scope user {NOMBRE} -- "{python}" "{script}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
