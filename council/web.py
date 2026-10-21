"""Interfaz web sencilla del consejo.

Arranque:  python -m council.web            (http://127.0.0.1:8000)
Escucha solo en la máquina local por defecto: no tiene autenticación.
"""

from __future__ import annotations

import os
import tempfile
import threading
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

from .config import cargar_env
from .informe import leer_documento
from .prompts import MODOS
from .providers import NIVELES
from .servicio import FABRICAS, ejecutar, refinar

CLAVES_API = {
    "claude": "ANTHROPIC_API_KEY",
    "chatgpt": "OPENAI_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
}
NOMBRES = {"claude": "Claude", "chatgpt": "ChatGPT", "perplexity": "Perplexity"}
EXTENSIONES = {".txt", ".md", ".docx", ".pdf"}


def crear_app(carpeta_salida: str | Path = "salidas", fabricas: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder="static")
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
    consultas: dict[str, dict] = {}
    cerrojo = threading.Lock()

    def disponibles() -> dict[str, bool]:
        if fabricas:
            return {clave: True for clave in fabricas}
        return {clave: bool(os.getenv(var)) for clave, var in CLAVES_API.items()}

    @app.get("/")
    def inicio():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/configuracion")
    def configuracion():
        return jsonify(
            modos=[{"id": k, "nombre": v[0]} for k, v in MODOS.items()],
            miembros=[{"id": k, "nombre": NOMBRES.get(k, k), "disponible": ok}
                      for k, ok in disponibles().items()],
        )

    @app.post("/api/consultas")
    def crear_consulta():
        tarea = request.form.get("tarea", "").strip()
        modo = request.form.get("modo", "general")
        miembros = request.form.getlist("miembros")
        presidente = request.form.get("presidente", "")
        seudonimizar = request.form.get("seudonimizar") == "on"
        nivel = request.form.get("nivel", "estandar")

        if not tarea:
            return jsonify(error="Escriba la tarea."), 400
        if modo not in MODOS:
            return jsonify(error="Modo no válido."), 400
        if nivel not in NIVELES:
            return jsonify(error="Nivel no válido."), 400
        activos = disponibles()
        if len(miembros) < 2 or any(not activos.get(m) for m in miembros):
            return jsonify(error="Seleccione al menos dos miembros con clave de API configurada."), 400
        if presidente not in miembros:
            return jsonify(error="El presidente debe ser uno de los miembros seleccionados."), 400

        documento = None
        fichero = request.files.get("documento")
        if fichero and fichero.filename:
            sufijo = Path(fichero.filename).suffix.lower()
            if sufijo not in EXTENSIONES:
                return jsonify(error=f"Formato no admitido: {sufijo}"), 400
            with tempfile.TemporaryDirectory() as tmp:
                ruta = Path(tmp) / f"documento{sufijo}"
                fichero.save(ruta)
                try:
                    documento = leer_documento(ruta)
                except Exception as e:
                    return jsonify(error=f"No se pudo leer el documento: {e}"), 400

        id_consulta = uuid.uuid4().hex
        estado = {"estado": "en_curso", "mensajes": [], "error": None, "salida": None}
        with cerrojo:
            consultas[id_consulta] = estado

        def anotar(mensaje: str) -> None:
            with cerrojo:
                estado["mensajes"].append(f"{datetime.now():%H:%M:%S} · {mensaje}")

        def trabajo() -> None:
            try:
                salida = ejecutar(
                    tarea=tarea, documento=documento, modo=modo, miembros=miembros,
                    presidente=presidente, seudonimizar=seudonimizar, nivel=nivel,
                    carpeta=carpeta_salida, registro=anotar, fabricas=fabricas,
                )
                with cerrojo:
                    estado.update(estado="terminada", salida=salida)
            except Exception as e:  # se muestra al usuario en lugar de perderse en el hilo
                with cerrojo:
                    estado.update(estado="error", error=f"{type(e).__name__}: {e}")

        threading.Thread(target=trabajo, daemon=True).start()
        return jsonify(id=id_consulta), 202

    @app.post("/api/consultas/<id_consulta>/refinar")
    def refinar_consulta(id_consulta: str):
        instrucciones = request.form.get("instrucciones", "").strip()
        with cerrojo:
            estado = consultas.get(id_consulta)
            if estado is None:
                abort(404)
            if not instrucciones:
                return jsonify(error="Escriba qué debe cambiar en la nueva versión."), 400
            if estado["estado"] == "en_curso" or not estado["salida"]:
                return jsonify(error="Espere a que termine el trabajo en curso."), 409
            estado.update(estado="en_curso", error=None)
            salida = estado["salida"]

        def anotar(mensaje: str) -> None:
            with cerrojo:
                estado["mensajes"].append(f"{datetime.now():%H:%M:%S} · {mensaje}")

        def trabajo() -> None:
            try:
                refinar(salida, instrucciones, registro=anotar, fabricas=fabricas)
                with cerrojo:
                    estado.update(estado="terminada")
            except Exception as e:  # se conserva la versión anterior y se informa del fallo
                with cerrojo:
                    estado.update(estado="terminada",
                                  error=f"No se pudo generar la nueva versión. {type(e).__name__}: {e}")

        threading.Thread(target=trabajo, daemon=True).start()
        return jsonify(id=id_consulta), 202

    @app.get("/api/consultas/<id_consulta>")
    def ver_consulta(id_consulta: str):
        with cerrojo:
            estado = consultas.get(id_consulta)
            if estado is None:
                abort(404)
            respuesta = {k: estado[k] for k in ("estado", "error")}
            respuesta["mensajes"] = list(estado["mensajes"])
            if estado["salida"]:
                respuesta["informe"] = estado["salida"].informe.read_text(encoding="utf-8")
                respuesta["seudonimizados"] = estado["salida"].datos_seudonimizados
                respuesta["version"] = len(estado["salida"].resultado.versiones) + 1
        return jsonify(respuesta)

    @app.get("/api/consultas/<id_consulta>/<tipo>")
    def descargar(id_consulta: str, tipo: str):
        with cerrojo:
            estado = consultas.get(id_consulta)
            salida = estado and estado["salida"]
        if not salida or tipo not in ("informe", "registro"):
            abort(404)
        ruta = salida.informe if tipo == "informe" else salida.registro
        return send_file(ruta.resolve(), as_attachment=True, download_name=ruta.name)

    return app


if __name__ == "__main__":
    cargar_env()
    host = os.getenv("COUNCIL_HOST", "127.0.0.1")
    puerto = int(os.getenv("COUNCIL_PORT", "8000"))
    direccion = f"http://{host}:{puerto}"
    print(f"Consejo de LLM disponible en {direccion}  (Ctrl+C para detenerlo)")
    if os.getenv("COUNCIL_ABRIR_NAVEGADOR", "1") == "1":
        threading.Timer(1.5, webbrowser.open, args=[direccion]).start()
    crear_app(os.getenv("COUNCIL_SALIDAS", "salidas")).run(host=host, port=puerto, threaded=True)
