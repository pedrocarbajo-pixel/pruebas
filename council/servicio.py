"""Ejecución completa de una consulta: seudonimización, deliberación y guardado.

Lo comparten la interfaz de línea de órdenes y la interfaz web.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from . import privacidad
from .consejo import Consejo, Resultado
from .consejo import refinar as refinar_resultado
from .informe import guardar
from .exportar import exportar
from .providers import MiembroClaude, MiembroOpenAI, MiembroPerplexity

FABRICAS = {
    "claude": MiembroClaude,
    "chatgpt": MiembroOpenAI,
    "perplexity": MiembroPerplexity,
}


@dataclass
class Salida:
    resultado: Resultado  # con los datos seudonimizados, tal como lo vieron los modelos
    informe: Path
    registro: Path
    mapa: Path | None
    datos_seudonimizados: int
    word: Path | None = None  # informe del presidente en Word    # Contexto necesario para pedir nuevas versiones (solo en memoria; no se guarda en disco).
    presidente: str = "claude"
    documento: str | None = None
    seudonimizar: bool = False
    mapa_datos: dict[str, str] = field(default_factory=dict)
    carpeta: Path = Path("salidas")


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

    salida = Salida(resultado, Path(), Path(), None, len(mapa), presidente=presidente,
                    documento=documento, seudonimizar=seudonimizar, mapa_datos=mapa,
                    carpeta=Path(carpeta))
    _guardar(salida)
    return salida


def refinar(salida: Salida, instrucciones: str, registro=print, fabricas: dict | None = None) -> Salida:
    """Genera con el presidente una nueva versión de la síntesis y la guarda como `_v2`, `_v3`…"""
    fabricas = fabricas or FABRICAS
    if salida.seudonimizar:
        # Las indicaciones también pueden contener datos personales.
        instrucciones, salida.mapa_datos = privacidad.seudonimizar(instrucciones, salida.mapa_datos)
        salida.datos_seudonimizados = len(salida.mapa_datos)
    version = len(salida.resultado.versiones) + 2
    registro(f"Versión {version} · el presidente aplica sus indicaciones…")
    presidente = fabricas[salida.presidente](nivel=salida.resultado.nivel)
    refinar_resultado(presidente, salida.resultado, instrucciones, salida.documento)
    _guardar(salida, sufijo=f"_v{version}")
    registro(f"Versión {version} terminada.")
    return salida


def exportar_presidente(salida: Salida, formato: str) -> Path:
    """Guarda el informe del presidente de la versión vigente en el formato indicado."""
    mapa = salida.mapa_datos
    restaurar = partial(privacidad.restaurar, mapa=mapa) if mapa else None
    return exportar(salida.resultado, formato, salida.informe.with_name(salida.informe.stem + "_presidente"),
                    restaurar=restaurar)


def _guardar(salida: Salida, sufijo: str = "") -> None:
    mapa = salida.mapa_datos
    restaurar = partial(privacidad.restaurar, mapa=mapa) if mapa else None
    salida.informe, salida.registro = guardar(salida.resultado, salida.carpeta,
                                              restaurar=restaurar, sufijo=sufijo)
    salida.word = exportar_presidente(salida, "docx")
    if mapa:
        # El mapa contiene los datos reales: se guarda aparte para poder custodiarlo.
        salida.mapa = salida.registro.parent / f"mapa_{salida.registro.stem}.json"
        salida.mapa.write_text(json.dumps(mapa, ensure_ascii=False, indent=2), encoding="utf-8")
