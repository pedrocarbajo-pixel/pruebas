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

from .modelos import candidatos

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


def _modelo_no_disponible(error: Exception) -> bool:
    """El proveedor indica que el modelo no existe o que la cuenta no tiene acceso a él."""
    estado = getattr(error, "status_code", None)
    texto = str(error).lower()
    if estado == 404:
        return True
    return estado in (400, 403) and any(p in texto for p in ("model", "preset")) and any(
        p in texto for p in ("not found", "does not exist", "not exist", "invalid", "no access",
                             "not have access", "unknown", "unsupported", "not supported"))


def _busqueda_activa() -> bool:
    return os.getenv("BUSQUEDA_WEB", "1") == "1"


def _dominios() -> list[str]:
    """Dominios a los que se limita la búsqueda web (vacío = sin límite)."""
    valor = os.getenv("BUSQUEDA_DOMINIOS") or os.getenv("PERPLEXITY_DOMINIOS", "")
    return [d.strip() for d in valor.split(",") if d.strip()]


def anexar_fuentes(texto: str, fuentes: dict[str, str], nombre: str) -> str:
    """Añade al texto la lista de fuentes web consultadas ({url: título})."""
    if not fuentes:
        return texto
    return texto + f"\n\n### Fuentes consultadas por {nombre}\n" + "\n".join(
        f"{i}. [{titulo}]({url})" for i, (url, titulo) in enumerate(fuentes.items(), 1)
    )


class _ConEsfuerzo:
    """Gestiona la cadena de modelos de reserva, la escala de esfuerzos y la búsqueda web."""

    esfuerzos: list[str | None]
    candidatos: list[str]
    busqueda: bool = False
    busqueda_rechazada: bool = False

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
                if (not _es_error_de_peticion(e) or _modelo_no_disponible(e)
                        or self._indice == len(self.esfuerzos) - 1):
                    raise
                self._indice += 1  # se mantiene el nivel rebajado para el resto de llamadas

    def _iniciar_modelos(self, candidatos: list[str]) -> None:
        self.candidatos = candidatos
        self.descartados: list[str] = []
        self.modelo = candidatos[0]

    def _ejecutar(self, llamada):
        """Como `_con_esfuerzo`, con dos recursos ante rechazos del proveedor:
        pasar al siguiente modelo de la cadena y, si rechaza la búsqueda web, seguir sin ella."""
        while True:
            try:
                return self._con_esfuerzo(llamada)
            except Exception as e:
                restantes = self.candidatos[self.candidatos.index(self.modelo) + 1:]
                if _modelo_no_disponible(e) and restantes:
                    self.descartados.append(self.modelo)
                    self.modelo, self._indice = restantes[0], 0
                elif self.busqueda and _es_error_de_peticion(e):
                    self.busqueda, self.busqueda_rechazada, self._indice = False, True, 0
                else:
                    raise

    def descripcion(self) -> str:
        partes = [self.modelo]
        if self.esfuerzo:
            partes.append(f"esfuerzo {self.esfuerzo}")
        if self.busqueda:
            partes.append("búsqueda web")
        elif self.busqueda_rechazada:
            partes.append("sin búsqueda web (rechazada por el proveedor)")
        if getattr(self, "descartados", None):
            partes.append(f"sustituye a {', '.join(self.descartados)} (no disponible)")
        return " · ".join(partes)


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
        self._iniciar_modelos([self.modelo] if self.modelo else candidatos("claude", self.nivel))
        self.max_tokens = 64000 if extremo else 16000
        self._iniciar_esfuerzo(
            _esfuerzos_extremo("CLAUDE_ESFUERZO_EXTREMO", "max,xhigh,high") if extremo else [None]
        )
        self.busqueda = _busqueda_activa()
        self._cliente = anthropic.Anthropic(timeout=3600 if extremo else 600)

    def preguntar(self, sistema: str, mensaje: str) -> str:
        def llamada(esfuerzo: str | None) -> str:
            extra: dict = {}
            if esfuerzo:
                extra = {"thinking": {"type": "adaptive"}, "output_config": {"effort": esfuerzo}}
            if self.busqueda:
                herramienta = {"type": os.getenv("CLAUDE_WEB_SEARCH", "web_search_20250305"),
                               "name": "web_search", "max_uses": 10}
                if _dominios():
                    herramienta["allowed_domains"] = _dominios()
                extra["tools"] = [herramienta]
            mensajes: list = [{"role": "user", "content": mensaje}]
            textos: list[str] = []
            fuentes: dict[str, str] = {}
            # Con búsqueda web el servidor puede pausar el turno («pause_turn»); se continúa
            # reenviando lo generado hasta que termine.
            for _ in range(5):
                # Se usa streaming porque las respuestas largas (contratos) pueden superar
                # el tiempo máximo de una petición no transmitida.
                with self._cliente.messages.stream(
                    model=self.modelo,
                    max_tokens=self.max_tokens,
                    system=sistema,
                    messages=mensajes,
                    **extra,
                ) as flujo:
                    respuesta = flujo.get_final_message()
                for bloque in respuesta.content:
                    if bloque.type == "text":
                        textos.append(bloque.text)
                        for cita in getattr(bloque, "citations", None) or []:
                            if getattr(cita, "url", None):
                                fuentes.setdefault(cita.url, getattr(cita, "title", None) or cita.url)
                if respuesta.stop_reason != "pause_turn":
                    break
                mensajes = mensajes + [{"role": "assistant", "content": respuesta.content}]
            return anexar_fuentes("".join(textos), fuentes, self.nombre)

        return self._ejecutar(llamada)


@dataclass
class MiembroOpenAI(_ConEsfuerzo):
    nivel: str = "estandar"
    nombre: str = "ChatGPT"
    modelo: str = ""

    def __post_init__(self) -> None:
        import openai

        extremo = self.nivel == "extremo"
        self._iniciar_modelos([self.modelo] if self.modelo else candidatos("chatgpt", self.nivel))
        self._iniciar_esfuerzo(
            _esfuerzos_extremo("OPENAI_ESFUERZO_EXTREMO", "max,xhigh,high") if extremo else [None]
        )
        self.busqueda = _busqueda_activa()
        self._cliente = openai.OpenAI(timeout=3600 if extremo else 600)

    def preguntar(self, sistema: str, mensaje: str) -> str:
        def llamada(esfuerzo: str | None) -> str:
            extra: dict = {"reasoning": {"effort": esfuerzo}} if esfuerzo else {}
            if self.busqueda:
                herramienta: dict = {"type": "web_search"}
                if _dominios():
                    herramienta["filters"] = {"allowed_domains": _dominios()}
                extra["tools"] = [herramienta]
            respuesta = self._cliente.responses.create(
                model=self.modelo,
                instructions=sistema,
                input=mensaje,
                **extra,
            )
            fuentes: dict[str, str] = {}
            for item in respuesta.output:
                if item.type == "message":
                    for parte in item.content:
                        for anotacion in getattr(parte, "annotations", None) or []:
                            if getattr(anotacion, "type", None) == "url_citation":
                                fuentes.setdefault(anotacion.url, anotacion.title or anotacion.url)
            return anexar_fuentes(respuesta.output_text, fuentes, self.nombre)

        return self._ejecutar(llamada)


@dataclass
class MiembroPerplexity(_ConEsfuerzo):
    """Miembro con búsqueda web: aporta fuentes actualizadas y verificables.

    Usa la Agent API de Perplexity (`responses.create`). Las fuentes consultadas se
    añaden al final de la respuesta para que el resto del consejo pueda contrastarlas.
    """

    nivel: str = "estandar"
    nombre: str = "Perplexity"
    modelo: str = ""
    dominios: list[str] = field(default_factory=_dominios)

    def __post_init__(self) -> None:
        import perplexity

        self.extremo = self.nivel == "extremo"
        self._iniciar_modelos([self.modelo] if self.modelo else candidatos("perplexity", self.nivel))
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

        return self._ejecutar(llamada)


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
    return anexar_fuentes(respuesta.output_text, fuentes, "Perplexity")
