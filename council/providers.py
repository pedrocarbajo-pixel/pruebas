"""Adaptadores de los proveedores de LLM que forman el consejo."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Protocol


class Miembro(Protocol):
    """Interfaz mínima que debe cumplir cualquier miembro del consejo."""

    nombre: str
    modelo: str

    def preguntar(self, sistema: str, mensaje: str) -> str: ...


def _con_reintentos(funcion, intentos: int = 3, espera: float = 2.0):
    """Ejecuta `funcion` con reintentos y espera exponencial ante errores transitorios."""
    for intento in range(1, intentos + 1):
        try:
            return funcion()
        except Exception:  # los SDK lanzan clases distintas; se reintenta y se propaga al final
            if intento == intentos:
                raise
            time.sleep(espera * 2 ** (intento - 1))


@dataclass
class MiembroClaude:
    modelo: str = field(default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-opus-5-5"))
    max_tokens: int = 16000
    nombre: str = "Claude"

    def __post_init__(self) -> None:
        import anthropic

        self._cliente = anthropic.Anthropic()

    def preguntar(self, sistema: str, mensaje: str) -> str:
        def llamada() -> str:
            # Se usa streaming porque las respuestas largas (contratos) pueden superar
            # el tiempo máximo de una petición no transmitida.
            with self._cliente.messages.stream(
                model=self.modelo,
                max_tokens=self.max_tokens,
                system=sistema,
                messages=[{"role": "user", "content": mensaje}],
            ) as flujo:
                respuesta = flujo.get_final_message()
            return "".join(b.text for b in respuesta.content if b.type == "text")

        return _con_reintentos(llamada)


@dataclass
class MiembroOpenAI:
    modelo: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-5"))
    nombre: str = "ChatGPT"

    def __post_init__(self) -> None:
        import openai

        self._cliente = openai.OpenAI()

    def preguntar(self, sistema: str, mensaje: str) -> str:
        def llamada() -> str:
            respuesta = self._cliente.responses.create(
                model=self.modelo,
                instructions=sistema,
                input=mensaje,
            )
            return respuesta.output_text

        return _con_reintentos(llamada)


@dataclass
class MiembroPerplexity:
    """Miembro con búsqueda web: aporta fuentes actualizadas y verificables.

    Usa la Agent API de Perplexity (`responses.create`). Las fuentes consultadas se
    añaden al final de la respuesta para que el resto del consejo pueda contrastarlas.
    """

    preset: str = field(default_factory=lambda: os.getenv("PERPLEXITY_PRESET", "sonar-pro"))
    dominios: list[str] = field(default_factory=lambda: [
        d.strip() for d in os.getenv("PERPLEXITY_DOMINIOS", "").split(",") if d.strip()
    ])
    nombre: str = "Perplexity"

    def __post_init__(self) -> None:
        import perplexity

        self._cliente = perplexity.Perplexity()
        self.modelo = self.preset

    def preguntar(self, sistema: str, mensaje: str) -> str:
        parametros: dict = {"preset": self.preset, "instructions": sistema, "input": mensaje}
        if self.dominios:
            # Restringe la búsqueda a fuentes oficiales (BOE, AEAT, CENDOJ, EUR-Lex…).
            parametros["tools"] = [
                {"type": "web_search", "filters": {"search_domain_filter": self.dominios}}
            ]

        def llamada() -> str:
            return formatear_con_fuentes(self._cliente.responses.create(**parametros))

        return _con_reintentos(llamada)


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
