"""Adaptadores de los proveedores de LLM que forman el consejo.

Cada miembro funciona en uno de dos niveles:
- «estandar»: modelo y esfuerzo habituales.
- «extremo»: el modelo más capaz configurado y el máximo esfuerzo de razonamiento, solo para
  casos críticos (más lento y bastante más caro). Si la API rechaza un nivel de esfuerzo,
  se prueba el siguiente inferior y el informe recoge el que se usó realmente.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Protocol

NIVELES = ("estandar", "extremo")


class Miembro(Protocol):
    """Interfaz mínima que debe cumplir cualquier miembro del consejo."""

    nombre: str
    modelo: str

    def preguntar(self, sistema: str, mensaje: str) -> str: ...


def _es_error_de_peticion(error: Exception) -> bool:
    """Errores 4xx (salvo 429): la petición es inválida y repetirla no sirve."""
    estado = getattr(error, "status_code", None)
    return isinstance(estado, int) and 400 <= estado < 500 and estado != 429


def _con_reintentos(funcion, intentos: int = 3, espera: float = 2.0):
    """Ejecuta `funcion` con reintentos y espera exponencial ante errores transitorios."""
    for intento in range(1, intentos + 1):
        try:
            return funcion()
        except Exception as e:  # los SDK lanzan clases distintas; se reintenta y se propaga al final
            if intento == intentos or _es_error_de_peticion(e):
                raise
            time.sleep(espera * 2 ** (intento - 1))


class _ConEsfuerzo:
    """Gestiona la escala descendente de esfuerzos del nivel extremo."""

    esfuerzos: list[str | None]

    def _iniciar_esfuerzo(self, esfuerzos: list[str | None]) -> None:
        self.esfuerzos = esfuerzos
        self._indice = 0

    @property
    def esfuerzo(self) -> str | None:
        return self.esfuerzos[self._indice]

    def _con_esfuerzo(self, llamada):
        """Llama a `llamada(esfuerzo)`; si la API rechaza el esfuerzo, prueba el siguiente."""
        while True:
            try:
                return _con_reintentos(lambda: llamada(self.esfuerzo))
            except Exception as e:
                if not _es_error_de_peticion(e) or self._indice == len(self.esfuerzos) - 1:
                    raise
                self._indice += 1  # se mantiene el nivel rebajado para el resto de llamadas

    def descripcion(self) -> str:
        return f"{self.modelo} · esfuerzo {self.esfuerzo}" if self.esfuerzo else self.modelo


def _esfuerzos_extremo(variable: str, por_defecto: str) -> list[str | None]:
    """Lista de esfuerzos a probar, de mayor a menor; `None` = valor por defecto del modelo."""
    valores = [v.strip() for v in os.getenv(variable, por_defecto).split(",") if v.strip()]
    return valores + [None]


@dataclass
class MiembroClaude(_ConEsfuerzo):
    nivel: str = "estandar"
    nombre: str = "Claude"
    modelo: str = ""

    def __post_init__(self) -> None:
        import anthropic

        extremo = self.nivel == "extremo"
        self.modelo = self.modelo or (
            os.getenv("CLAUDE_MODEL_EXTREMO", "claude-opus-5-5") if extremo
            else os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
        )
        self.max_tokens = 64000 if extremo else 16000
        self._iniciar_esfuerzo(
            _esfuerzos_extremo("CLAUDE_ESFUERZO_EXTREMO", "max,xhigh,high") if extremo else [None]
        )
        self._cliente = anthropic.Anthropic(timeout=3600 if extremo else 600)

    def preguntar(self, sistema: str, mensaje: str) -> str:
        def llamada(esfuerzo: str | None) -> str:
            extra = {}
            if esfuerzo:
                extra = {"thinking": {"type": "adaptive"}, "output_config": {"effort": esfuerzo}}
            # Se usa streaming porque las respuestas largas (contratos) pueden superar
            # el tiempo máximo de una petición no transmitida.
            with self._cliente.messages.stream(
                model=self.modelo,
                max_tokens=self.max_tokens,
                system=sistema,
                messages=[{"role": "user", "content": mensaje}],
                **extra,
            ) as flujo:
                respuesta = flujo.get_final_message()
            return "".join(b.text for b in respuesta.content if b.type == "text")

        return self._con_esfuerzo(llamada)


@dataclass
class MiembroOpenAI(_ConEsfuerzo):
    nivel: str = "estandar"
    nombre: str = "ChatGPT"
    modelo: str = ""

    def __post_init__(self) -> None:
        import openai

        extremo = self.nivel == "extremo"
        self.modelo = self.modelo or (
            os.getenv("OPENAI_MODEL_EXTREMO", "gpt-5.5-pro") if extremo
            else os.getenv("OPENAI_MODEL", "gpt-5")
        )
        self._iniciar_esfuerzo(
            _esfuerzos_extremo("OPENAI_ESFUERZO_EXTREMO", "max,xhigh,high") if extremo else [None]
        )
        self._cliente = openai.OpenAI(timeout=3600 if extremo else 600)

    def preguntar(self, sistema: str, mensaje: str) -> str:
        def llamada(esfuerzo: str | None) -> str:
            extra = {"reasoning": {"effort": esfuerzo}} if esfuerzo else {}
            respuesta = self._cliente.responses.create(
                model=self.modelo,
                instructions=sistema,
                input=mensaje,
                **extra,
            )
            return respuesta.output_text

        return self._con_esfuerzo(llamada)


@dataclass
class MiembroPerplexity(_ConEsfuerzo):
    """Miembro con búsqueda web: aporta fuentes actualizadas y verificables.

    Usa la Agent API de Perplexity (`responses.create`). Las fuentes consultadas se
    añaden al final de la respuesta para que el resto del consejo pueda contrastarlas.
    """

    nivel: str = "estandar"
    nombre: str = "Perplexity"
    modelo: str = ""
    dominios: list[str] = field(default_factory=lambda: [
        d.strip() for d in os.getenv("PERPLEXITY_DOMINIOS", "").split(",") if d.strip()
    ])

    def __post_init__(self) -> None:
        import perplexity

        self.extremo = self.nivel == "extremo"
        self.modelo = self.modelo or (
            os.getenv("PERPLEXITY_PRESET_EXTREMO", "sonar-reasoning") if self.extremo
            else os.getenv("PERPLEXITY_PRESET", "sonar-pro")
        )
        self._iniciar_esfuerzo(
            _esfuerzos_extremo("PERPLEXITY_ESFUERZO_EXTREMO", "xhigh,high") if self.extremo
            else [None]
        )
        self._cliente = perplexity.Perplexity(timeout=3600 if self.extremo else 600)

    def preguntar(self, sistema: str, mensaje: str) -> str:
        busqueda: dict = {}
        if self.dominios:
            # Restringe la búsqueda a fuentes oficiales (BOE, AEAT, CENDOJ, EUR-Lex…).
            busqueda["filters"] = {"search_domain_filter": self.dominios}
        if self.extremo:
            busqueda["search_context_size"] = "high"

        def llamada(esfuerzo: str | None) -> str:
            parametros: dict = {"preset": self.modelo, "instructions": sistema, "input": mensaje}
            if busqueda:
                parametros["tools"] = [{"type": "web_search", **busqueda}]
            if esfuerzo:
                parametros["reasoning"] = {"effort": esfuerzo}
            return formatear_con_fuentes(self._cliente.responses.create(**parametros))

        return self._con_esfuerzo(llamada)


def formatear_con_fuentes(respuesta) -> str:
    """Devuelve el texto de una respuesta de Perplexity seguido de la lista de fuentes."""
    fuentes: dict[str, str] = {}
    for item in respuesta.output:
        if item.type == "search_results":
            for r in item.results:
                fuentes.setdefault(r.url, r.title)
        elif item.type == "message":
            for parte in item.content:
                for anotacion in parte.annotations or []:
                    if anotacion.url:
                        fuentes.setdefault(anotacion.url, anotacion.title or anotacion.url)
    texto = respuesta.output_text
    if fuentes:
        texto += "\n\n### Fuentes consultadas por Perplexity\n" + "\n".join(
            f"{i}. [{titulo}]({url})" for i, (url, titulo) in enumerate(fuentes.items(), 1)
        )
    return texto
