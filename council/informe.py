"""Lectura de documentos de entrada y generación del informe y del registro de auditoría."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .consejo import Resultado
from .prompts import MODOS

AVISO = (
    "> **Aviso:** este informe ha sido generado por modelos de lenguaje y constituye un borrador "
    "de apoyo. No sustituye el asesoramiento de un profesional cualificado, que debe revisarlo "
    "antes de cualquier uso."
)


def a_markdown(r: Resultado, incluir_detalle: bool = True) -> str:
    modelos = ", ".join(f"{n} ({m})" for n, m in r.modelos.items())
    lineas = [
        "# Informe del consejo de LLM",
        "",
        AVISO,
        "",
        f"- **Fecha (UTC):** {r.fecha}",
        f"- **Modo:** {MODOS[r.modo][0]}",
        f"- **Nivel:** {'Extremo (modelos más capaces y esfuerzo máximo)' if r.nivel == 'extremo' else 'Estándar'}",
        f"- **Miembros:** {modelos}",
        f"- **Presidente:** {r.presidente}",
        f"- **Tarea:** {r.tarea}",
        *([f"- **Versión:** {len(r.versiones) + 1} (corregida a petición del usuario)"] if r.versiones else []),
        "",
        r.sintesis,
    ]
    if incluir_detalle:
        lineas += ["", "---", "", "# Anexo I · Borradores independientes"]
        for nombre, texto in r.borradores.items():
            lineas += ["", f"## {nombre}", "", texto]
        lineas += ["", "# Anexo II · Revisiones cruzadas"]
        for revisor, texto in r.revisiones.items():
            lineas += ["", f"## Revisión de {revisor}", "", texto]
        if r.versiones:
            lineas += ["", "# Anexo III · Historial de versiones"]
            for n, v in enumerate(r.versiones, 1):
                lineas += ["", f"## Versión {n}", "",
                           f"**Indicaciones del usuario para pasar a la versión {n + 1}:** {v['instrucciones']}",
                           "", _rebajar_titulos(v["sintesis"])]
    return "\n".join(lineas) + "\n"


def _rebajar_titulos(texto: str) -> str:
    """Baja dos niveles los títulos Markdown de una versión archivada para que no compitan con los del informe."""
    return "\n".join("##" + linea if linea.startswith("#") else linea for linea in texto.splitlines())


def guardar(r: Resultado, carpeta: str | Path, restaurar=None, sufijo: str = "") -> tuple[Path, Path]:
    """Guarda el informe en Markdown y el registro completo en JSON (para auditoría)."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    sello = r.fecha.replace(":", "").replace("-", "").replace(".", "_")[:22]
    informe = a_markdown(r)
    datos = asdict(r)
    if restaurar:
        informe = restaurar(informe)
        datos = json.loads(restaurar(json.dumps(datos, ensure_ascii=False)))
    ruta_md = carpeta / f"informe_{sello}{sufijo}.md"
    ruta_json = carpeta / f"registro_{sello}{sufijo}.json"
    ruta_md.write_text(informe, encoding="utf-8")
    ruta_json.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta_md, ruta_json
