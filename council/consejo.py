"""Orquestación del consejo: borradores independientes, revisión cruzada y síntesis."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import prompts
from .providers import NIVELES, Miembro


@dataclass
class Resultado:
    tarea: str
    modo: str
    presidente: str
    borradores: dict[str, str] = field(default_factory=dict)
    revisiones: dict[str, str] = field(default_factory=dict)  # clave: nombre del revisor
    sintesis: str = ""
    fecha: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    modelos: dict[str, str] = field(default_factory=dict)
    nivel: str = "estandar"


class Consejo:
    """Consejo de LLM en tres fases.

    1. Cada miembro responde de forma independiente (en paralelo, sin ver a los demás).
    2. Cada miembro revisa críticamente, en una sola llamada, las respuestas anonimizadas
       de los demás.
    3. El presidente integra borradores y revisiones en una respuesta final que expone
       consensos, discrepancias y cuestiones pendientes de verificación humana.
    """

    def __init__(self, miembros: list[Miembro], presidente: Miembro | None = None, registro=print,
                 nivel: str = "estandar"):
        if len(miembros) < 2:
            raise ValueError("El consejo necesita al menos dos miembros.")
        if nivel not in NIVELES:
            raise ValueError(f"Nivel desconocido: {nivel}. Opciones: {', '.join(NIVELES)}")
        self.nivel = nivel
        self.sistema = prompts.sistema(nivel)
        self.miembros = miembros
        self.presidente = presidente or miembros[0]
        self.registro = registro
        # Los autores se anonimizan para que nadie favorezca (ni penalice) una respuesta por su origen.
        self.alias = {m.nombre: f"Miembro {chr(65 + i)}" for i, m in enumerate(miembros)}

    def deliberar(self, tarea: str, documento: str | None = None, modo: str = "general") -> Resultado:
        if modo not in prompts.MODOS:
            raise ValueError(f"Modo desconocido: {modo}. Opciones: {', '.join(prompts.MODOS)}")
        contexto = {
            "modo": prompts.MODOS[modo][1],
            "tarea": tarea,
            "documento": prompts.bloque_documento(documento),
        }
        resultado = Resultado(
            tarea=tarea,
            modo=modo,
            presidente=self.presidente.nombre,
            nivel=self.nivel,
        )

        if self.nivel == "extremo":
            self.registro("Nivel EXTREMO: modelos más capaces y esfuerzo máximo (más lento y costoso).")
        self.registro("Fase 1/3 · Borradores independientes…")
        mensaje = prompts.FASE_BORRADOR.format(**contexto)
        resultado.borradores = self._en_paralelo(
            {m.nombre: (m, mensaje) for m in self.miembros}
        )

        self.registro("Fase 2/3 · Revisión cruzada…")
        encargos = {}
        for revisor in self.miembros:
            respuestas = "\n\n".join(
                f"### Respuesta de {self.alias[autor.nombre]}\n<<<\n{resultado.borradores[autor.nombre]}\n>>>"
                for autor in self.miembros
                if autor is not revisor
            )
            msg = prompts.FASE_REVISION_CRUZADA.format(**contexto, respuestas=respuestas)
            encargos[revisor.nombre] = (revisor, msg)
        resultado.revisiones = self._en_paralelo(encargos)

        self.registro(f"Fase 3/3 · Síntesis del presidente ({self.presidente.nombre})…")
        resultado.sintesis = self.presidente.preguntar(
            self.sistema,
            prompts.FASE_SINTESIS.format(**contexto, materiales=self._materiales(resultado)),
        )
        # Se anota al final porque el esfuerzo efectivo puede haberse rebajado durante la deliberación.
        resultado.modelos = {
            m.nombre: m.descripcion() if hasattr(m, "descripcion") else m.modelo
            for m in self.miembros
        }
        self.registro("Deliberación terminada.")
        return resultado

    def _en_paralelo(self, encargos: dict[str, tuple[Miembro, str]]) -> dict[str, str]:
        with ThreadPoolExecutor(max_workers=len(encargos)) as ejecutor:
            futuros = {
                clave: ejecutor.submit(miembro.preguntar, self.sistema, mensaje)
                for clave, (miembro, mensaje) in encargos.items()
            }
            return {clave: futuro.result() for clave, futuro in futuros.items()}

    def _materiales(self, r: Resultado) -> str:
        partes = [
            f"### Borrador de {self.alias[nombre]}\n<<<\n{texto}\n>>>"
            for nombre, texto in r.borradores.items()
        ]
        partes += [
            f"### Revisión de {self.alias[revisor]} sobre los demás miembros\n<<<\n{texto}\n>>>"
            for revisor, texto in r.revisiones.items()
        ]
        return "\n\n".join(partes)
