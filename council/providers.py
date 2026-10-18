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
