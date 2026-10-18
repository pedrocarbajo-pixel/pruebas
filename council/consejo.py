"""Orquestación del consejo: borradores independientes, revisión cruzada y síntesis."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import prompts
from .providers import Miembro


@dataclass
class Resultado:
    tarea: str
    modo: str
    presidente: str
    borradores: dict[str, str] = field(default_factory=dict)
    revisiones: dict[str, str] = field(default_factory=dict)  # clave: «revisor → revisado»
    sintesis: str = ""
    fecha: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    modelos: dict[str, str] = field(default_factory=dict)


class Consejo:
    """Consejo de LLM en tres fases.

    1. Cada miembro responde de forma independiente (en paralelo, sin ver a los demás).
    2. Cada miembro revisa críticamente la respuesta anonimizada de los demás.
    3. El presidente integra borradores y revisiones en una respuesta final que expone
       consensos, discrepancias y cuestiones pendientes de verificación humana.
    """

    def __init__(self, miembros: list[Miembro], presidente: Miembro | None = None, registro=print):
        if len(miembros) < 2:
            raise ValueError("El consejo necesita al menos dos miembros.")
        self.miembros = miembros
        self.presidente = presidente or miembros[0]
        self.registro = registro

    def deliberar(self, tarea: str, documento: str | None = None, modo: str = "general") -> Resultado:
        if modo not in prompts.MODOS:
            raise ValueError(f"Modo desconocido: {modo}. Opciones: {', '.join(prompts.MODOS)}")
        contexto = {
            "modo": prompts.MODOS[modo],
            "tarea": tarea,
            "documento": prompts.bloque_documento(documento),
        }
        resultado = Resultado(
            tarea=tarea,
            modo=modo,
            presidente=self.presidente.nombre,
            modelos={m.nombre: m.modelo for m in self.miembros},
        )

        self.registro("Fase 1/3 · Borradores independientes…")
        mensaje = prompts.FASE_BORRADOR.format(**contexto)
        resultado.borradores = self._en_paralelo(
            {m.nombre: (m, mensaje) for m in self.miembros}
        )

        self.registro("Fase 2/3 · Revisión cruzada…")
        encargos = {}
        for revisor in self.miembros:
            for autor in self.miembros:
                if autor is revisor:
                    continue
                msg = prompts.FASE_REVISION_CRUZADA.format(
                    **contexto, respuesta=resultado.borradores[autor.nombre]
                )
                encargos[f"{revisor.nombre} → {autor.nombre}"] = (revisor, msg)
        resultado.revisiones = self._en_paralelo(encargos)

        self.registro(f"Fase 3/3 · Síntesis del presidente ({self.presidente.nombre})…")
        materiales = self._materiales(resultado)
        resultado.sintesis = self.presidente.preguntar(
            prompts.PRINCIPIOS,
            prompts.FASE_SINTESIS.format(**contexto, materiales=materiales),
        )
        return resultado

    def _en_paralelo(self, encargos: dict[str, tuple[Miembro, str]]) -> dict[str, str]:
        with ThreadPoolExecutor(max_workers=len(encargos)) as ejecutor:
            futuros = {
                clave: ejecutor.submit(miembro.preguntar, prompts.PRINCIPIOS, mensaje)
                for clave, (miembro, mensaje) in encargos.items()
            }
            return {clave: futuro.result() for clave, futuro in futuros.items()}

    def _materiales(self, r: Resultado) -> str:
        # Se anonimizan los autores para que el presidente no favorezca su propia respuesta.
        alias = {m.nombre: f"Miembro {chr(65 + i)}" for i, m in enumerate(self.miembros)}
        partes = []
        for nombre, texto in r.borradores.items():
            partes.append(f"### Borrador de {alias[nombre]}\n<<<\n{texto}\n>>>")
        for clave, texto in r.revisiones.items():
            revisor, autor = clave.split(" → ")
            partes.append(
                f"### Revisión de {alias[revisor]} sobre {alias[autor]}\n<<<\n{texto}\n>>>"
            )
        return "\n\n".join(partes)
