"""Lectura de documentos de entrada y generación del informe y del registro de auditoría."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .consejo import Resultado
from .prompts import DELIBERACIONES, MODOS

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
        f"- **Deliberación:** {DELIBERACIONES[r.deliberacion][0]} ({DELIBERACIONES[r.deliberacion][1]})",
        f"- **Nivel:** {'Extremo (modelos más capaces y esfuerzo máximo)' if r.nivel == 'extremo' else 'Estándar'}",
        f"- **Miembros:** {modelos}",
        f"- **Presidente:** {r.presidente}",
        f"- **Tarea:** {r.tarea}",
        *([f"- **Versión:** {len(r.versiones) + 1} (corregida a petición del usuario)"] if r.versiones else []),
        *([f"- **Incidencias:** {'; '.join(r.incidencias)}"] if r.incidencias else []),
        "",
        r.sintesis,
    ]
    if incluir_detalle:
        agentes = r.deliberacion == "agentes_claude"
        lineas += ["", "---", "", "# Anexo I · " + ("Análisis independientes de los agentes" if agentes
                                                    else "Borradores independientes")]
        for nombre, texto in r.borradores.items():
            lineas += ["", f"## {nombre}", "", texto]
        lineas += ["", "# Anexo II · Revisiones cruzadas" + (" entre agentes" if agentes else "")]
        for revisor, texto in r.revisiones.items():
            lineas += ["", f"## Revisión de {revisor}", "", texto]
        if r.equipos:
            lineas += ["", "# Anexo IV · Trabajo interno de los equipos de agentes"]
            for miembro, trabajo in r.equipos.items():
                lineas += ["", f"## Equipo de {miembro}"]
                for rol, texto in trabajo["borradores"].items():
                    lineas += ["", f"### Análisis de {rol}", "", _rebajar_titulos(texto, 3)]
                for rol, texto in trabajo["revisiones"].items():
                    lineas += ["", f"### Revisión de {rol}", "", _rebajar_titulos(texto, 3)]
        if r.versiones:
            lineas += ["", "# Anexo III · Historial de versiones"]
            for n, v in enumerate(r.versiones, 1):
                lineas += ["", f"## Versión {n}", "",
                           f"**Indicaciones del usuario para pasar a la versión {n + 1}:** {v['instrucciones']}",
                           "", _rebajar_titulos(v["sintesis"])]
    return "\n".join(lineas) + "\n"


def _rebajar_titulos(texto: str, niveles: int = 2) -> str:
    """Baja los títulos Markdown de un texto anexado para que no compitan con los del informe."""
    return "\n".join("#" * niveles + linea if linea.startswith("#") else linea for linea in texto.splitlines())


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
