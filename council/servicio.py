"""Ejecución completa de una consulta: seudonimización, deliberación y guardado.

Lo comparten la interfaz de línea de órdenes y la interfaz web.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from . import privacidad
from .consejo import Consejo, Resultado
from .informe import guardar
from .providers import MiembroClaude, MiembroOpenAI, MiembroPerplexity

FABRICAS = {
    "claude": MiembroClaude,
    "chatgpt": MiembroOpenAI,
    "perplexity": MiembroPerplexity,
}


@dataclass
class Salida:
    resultado: Resultado
    informe: Path
    registro: Path
    mapa: Path | None
    datos_seudonimizados: int


def ejecutar(
    tarea: str,
    documento: str | None = None,
    modo: str = "general",
    miembros: list[str] | None = None,
    presidente: str = "claude",
    seudonimizar: bool = False,
    nivel: str = "estandar",
    carpeta: str | Path = "salidas",
    registro=print,
    fabricas: dict | None = None,
) -> Salida:
    fabricas = fabricas or FABRICAS
    miembros = miembros or list(fabricas)
    if presidente not in miembros:
        raise ValueError("El presidente debe ser uno de los miembros seleccionados.")

    mapa: dict[str, str] = {}
    if seudonimizar:
        # Tarea y documento se procesan juntos para que un mismo dato reciba el mismo marcador.
        separador = "\n\x00\n"
        combinado, mapa = privacidad.seudonimizar(tarea + separador + (documento or ""))
        tarea, documento = combinado.split(separador, 1)
        documento = documento or None
        registro(f"Seudonimizados {len(mapa)} datos.")

    instancias = {clave: fabricas[clave](nivel=nivel) for clave in miembros}
    consejo = Consejo(list(instancias.values()), presidente=instancias[presidente],
                      registro=registro, nivel=nivel)
    resultado = consejo.deliberar(tarea, documento, modo=modo)

    restaurar = partial(privacidad.restaurar, mapa=mapa) if mapa else None
    ruta_md, ruta_json = guardar(resultado, carpeta, restaurar=restaurar)
    ruta_mapa = None
    if mapa:
        # El mapa contiene los datos reales: se guarda aparte para poder custodiarlo.
        ruta_mapa = ruta_json.parent / f"mapa_{ruta_json.stem}.json"
        ruta_mapa.write_text(json.dumps(mapa, ensure_ascii=False, indent=2), encoding="utf-8")
    return Salida(resultado, ruta_md, ruta_json, ruta_mapa, len(mapa))
