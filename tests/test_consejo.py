import json
import threading
import time
from types import SimpleNamespace as NS

import pytest

from council import privacidad
from council.consejo import Consejo
from council.informe import guardar
from council.providers import formatear_con_fuentes
from council.servicio import ejecutar
from council.web import crear_app


class MiembroFalso:
    def __init__(self, nombre):
        self.nombre = nombre
        self.modelo = f"{nombre.lower()}-falso"
        self.llamadas = []
        self._cerrojo = threading.Lock()

    def preguntar(self, sistema, mensaje):
        with self._cerrojo:
            self.llamadas.append(mensaje)
        if "PRESIDENTE" in mensaje:
            return f"## Respuesta final\nSíntesis de {self.nombre}: {mensaje[-60:]}"
        if "Respuesta de Miembro" in mensaje:
            return f"Revisión de {self.nombre}"
        return f"Borrador de {self.nombre}"


def fabricas_falsas():
    return {clave: (lambda n=nombre: MiembroFalso(n))
            for clave, nombre in [("claude", "Claude"), ("chatgpt", "ChatGPT"),
                                  ("perplexity", "Perplexity")]}


def consejo_de_tres():
    miembros = [MiembroFalso(n) for n in ("Claude", "ChatGPT", "Perplexity")]
    return miembros, Consejo(miembros, registro=lambda *_: None)


def test_deliberacion_con_tres_miembros():
    (a, b, c), consejo = consejo_de_tres()
    r = consejo.deliberar("Revisa", "Contrato X", modo="contrato_revisar")
    assert set(r.borradores) == {"Claude", "ChatGPT", "Perplexity"}
    assert set(r.revisiones) == {"Claude", "ChatGPT", "Perplexity"}
    assert "Síntesis de Claude" in r.sintesis
    # Cada miembro: 1 borrador + 1 revisión; el presidente, además, la síntesis (3 + 3 + 1 = 7).
    assert (len(a.llamadas), len(b.llamadas), len(c.llamadas)) == (3, 2, 2)
    # Cada revisor recibe las respuestas de los otros dos, no la propia, con autores anonimizados.
    revision_de_a = next(m for m in a.llamadas if "Respuesta de Miembro" in m)
    assert "Borrador de ChatGPT" in revision_de_a and "Borrador de Perplexity" in revision_de_a
    assert "Borrador de Claude" not in revision_de_a
    assert "### Respuesta de Miembro B" in revision_de_a and "Miembro A" not in revision_de_a
    # El presidente no ve los nombres reales de los autores.
    sintesis = a.llamadas[-1]
    assert "### Borrador de Miembro C" in sintesis
    assert "### Borrador de Perplexity" not in sintesis


@pytest.mark.parametrize("modo", ["informe_tributario", "procedimiento_tributario", "dictamen_juridico"])
def test_modos_tributarios_y_juridicos(modo):
    (a, _, _), consejo = consejo_de_tres()
    consejo.deliberar("Tarea", modo=modo)
    assert "Modo:" in a.llamadas[0]


def test_presidente_configurable_y_validaciones():
    a, b = MiembroFalso("Claude"), MiembroFalso("ChatGPT")
    r = Consejo([a, b], presidente=b, registro=lambda *_: None).deliberar("T")
    assert r.presidente == "ChatGPT" and "Síntesis de ChatGPT" in r.sintesis
    with pytest.raises(ValueError):
        Consejo([a])
    with pytest.raises(ValueError):
        Consejo([a, b]).deliberar("T", modo="inexistente")


def test_fuentes_de_perplexity():
    respuesta = NS(
        output_text="Según el art. 66 LGT…",
        output=[
            NS(type="search_results", results=[NS(url="https://www.boe.es/a", title="LGT")]),
            NS(type="message", content=[NS(annotations=[
                NS(url="https://www.boe.es/a", title="LGT"),
                NS(url="https://petete.tributos.hacienda.gob.es/b", title="Consulta DGT"),
                NS(url=None, title=None),
            ])]),
        ],
    )
    texto = formatear_con_fuentes(respuesta)
    assert texto.startswith("Según el art. 66 LGT…")
    assert "1. [LGT](https://www.boe.es/a)" in texto
    assert "2. [Consulta DGT](https://petete.tributos.hacienda.gob.es/b)" in texto
    assert texto.count("boe.es/a") == 1


def test_seudonimizacion_reversible():
    texto = ("D. Juan, DNI 12345678Z, IBAN ES91 2100 0418 4502 0005 1332, "
             "correo juan@ejemplo.es, tel. 612 345 678. Repite DNI 12345678Z. "
             "Sociedad B12345674, NIE X1234567L.")
    seudo, mapa = privacidad.seudonimizar(texto)
    for dato in ["12345678Z", "ES91", "juan@ejemplo.es", "612 345 678", "B12345674", "X1234567L"]:
        assert dato not in seudo
    assert seudo.count("[DNI_1]") == 2
    assert privacidad.restaurar(seudo, mapa) == texto


def test_guardar_restaura_datos(tmp_path):
    a, b = MiembroFalso("Claude"), MiembroFalso("ChatGPT")
    r = Consejo([a, b], registro=lambda *_: None).deliberar("Cliente [EMAIL_1]")
    mapa = {"[EMAIL_1]": "x@y.es"}
    md, js = guardar(r, tmp_path, restaurar=lambda t: privacidad.restaurar(t, mapa))
    assert "x@y.es" in md.read_text(encoding="utf-8")
    assert json.loads(js.read_text(encoding="utf-8"))["tarea"] == "Cliente x@y.es"


def test_servicio_seudonimiza_antes_de_enviar(tmp_path):
    enviados = []

    class Espia(MiembroFalso):
        def preguntar(self, sistema, mensaje):
            enviados.append(mensaje)
            return super().preguntar(sistema, mensaje)

    fabricas = {"claude": lambda: Espia("Claude"), "chatgpt": lambda: Espia("ChatGPT")}
    salida = ejecutar("Cliente con DNI 12345678Z", "IBAN ES9121000418450200051332",
                      seudonimizar=True, carpeta=tmp_path, registro=lambda *_: None,
                      fabricas=fabricas)
    assert all("12345678Z" not in m and "ES9121" not in m for m in enviados)
    assert "12345678Z" in salida.informe.read_text(encoding="utf-8")
    assert salida.datos_seudonimizados == 2 and salida.mapa.exists()
    with pytest.raises(ValueError):
        ejecutar("T", miembros=["claude", "chatgpt"], presidente="perplexity",
                 fabricas=fabricas, carpeta=tmp_path)


def test_web_flujo_completo(tmp_path):
    cliente = crear_app(tmp_path, fabricas=fabricas_falsas()).test_client()
    conf = cliente.get("/api/configuracion").get_json()
    assert {m["id"] for m in conf["miembros"]} == {"claude", "chatgpt", "perplexity"}
    assert "informe_tributario" in {m["id"] for m in conf["modos"]}
    assert cliente.get("/").status_code == 200

    # Validaciones
    assert cliente.post("/api/consultas", data={"tarea": ""}).status_code == 400
    assert cliente.post("/api/consultas", data={
        "tarea": "T", "miembros": ["claude"], "presidente": "claude"}).status_code == 400

    r = cliente.post("/api/consultas", data={
        "tarea": "Analiza la liquidación", "modo": "procedimiento_tributario",
        "miembros": ["claude", "chatgpt", "perplexity"], "presidente": "perplexity",
        "seudonimizar": "on",
    })
    assert r.status_code == 202
    id_consulta = r.get_json()["id"]
    for _ in range(100):
        estado = cliente.get(f"/api/consultas/{id_consulta}").get_json()
        if estado["estado"] != "en_curso":
            break
        time.sleep(0.05)
    assert estado["estado"] == "terminada", estado
    assert "Síntesis de Perplexity" in estado["informe"]
    assert any("Fase 3/3" in m for m in estado["mensajes"])
    descarga = cliente.get(f"/api/consultas/{id_consulta}/registro")
    assert descarga.status_code == 200 and json.loads(descarga.data)["modo"] == "procedimiento_tributario"
    assert cliente.get("/api/consultas/inexistente").status_code == 404
