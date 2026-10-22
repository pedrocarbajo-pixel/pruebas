"""Consultas en segundo plano: el consejo tarda minutos, así que cada consulta se ejecuta en
su propio hilo y se consulta su estado por un identificador.

Lo comparten la interfaz web y el servidor MCP (uso desde la aplicación de Claude).
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime
from pathlib import Path

from .servicio import ejecutar, refinar


class ConsultaNoEncontrada(KeyError):
    pass


class ConsultaOcupada(RuntimeError):
    pass


class GestorConsultas:
    def __init__(self, carpeta: str | Path = "salidas", fabricas: dict | None = None):
        self.carpeta = carpeta
        self.fabricas = fabricas
        self._consultas: dict[str, dict] = {}
        self._cambio = threading.Condition()

    def iniciar(self, **parametros) -> str:
        """Lanza una deliberación (mismos parámetros que `servicio.ejecutar`) y devuelve su id."""
        id_consulta = uuid.uuid4().hex[:12]
        estado = {"estado": "en_curso", "mensajes": [], "error": None, "salida": None}
        with self._cambio:
            self._consultas[id_consulta] = estado

        def trabajo() -> None:
            try:
                salida = ejecutar(**parametros, carpeta=self.carpeta, fabricas=self.fabricas,
                                  registro=self._anotador(estado))
                self._actualizar(estado, estado="terminada", salida=salida)
            except Exception as e:  # se muestra al usuario en lugar de perderse en el hilo
                self._actualizar(estado, estado="error", error=f"{type(e).__name__}: {e}")

        threading.Thread(target=trabajo, daemon=True).start()
        return id_consulta

    def refinar(self, id_consulta: str, instrucciones: str) -> None:
        """Pide al presidente una versión corregida de una consulta terminada."""
        with self._cambio:
            estado = self._buscar(id_consulta)
            if estado["estado"] == "en_curso" or not estado["salida"]:
                raise ConsultaOcupada("Espere a que termine el trabajo en curso.")
            estado.update(estado="en_curso", error=None)
            salida = estado["salida"]

        def trabajo() -> None:
            try:
                refinar(salida, instrucciones, registro=self._anotador(estado), fabricas=self.fabricas)
                self._actualizar(estado, estado="terminada")
            except Exception as e:  # se conserva la versión anterior y se informa del fallo
                self._actualizar(estado, estado="terminada",
                                 error=f"No se pudo generar la nueva versión. {type(e).__name__}: {e}")

        threading.Thread(target=trabajo, daemon=True).start()

    def estado(self, id_consulta: str, esperar: float = 0) -> dict:
        """Copia del estado de la consulta. Con `esperar`, aguarda hasta ese número de segundos
        a que termine el trabajo en curso antes de responder."""
        with self._cambio:
            estado = self._buscar(id_consulta)
            if esperar:
                self._cambio.wait_for(lambda: estado["estado"] != "en_curso", timeout=esperar)
            return {**estado, "mensajes": list(estado["mensajes"])}

    def _buscar(self, id_consulta: str) -> dict:
        try:
            return self._consultas[id_consulta]
        except KeyError:
            raise ConsultaNoEncontrada(id_consulta) from None

    def _anotador(self, estado: dict):
        def anotar(mensaje: str) -> None:
            with self._cambio:
                estado["mensajes"].append(f"{datetime.now():%H:%M:%S} · {mensaje}")
        return anotar

    def _actualizar(self, consulta: dict, **cambios) -> None:
        with self._cambio:
            consulta.update(**cambios)
            self._cambio.notify_all()
