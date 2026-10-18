import json
import threading

import pytest

from council import privacidad
from council.consejo import Consejo
from council.informe import guardar


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
            return f"## Respuesta final\nSíntesis de {self.nombre}"
        if "RESPUESTA A REVISAR" in mensaje:
            return f"Revisión de {self.nombre}"
        return f"Borrador de {self.nombre}"


def test_deliberacion_completa():
    a, b = MiembroFalso("Claude"), MiembroFalso("ChatGPT")
    r = Consejo([a, b], registro=lambda *_: None).deliberar(
        "Revisa", "Contrato X", modo="revisar"
    )
    assert r.borradores == {"Claude": "Borrador de Claude", "ChatGPT": "Borrador de ChatGPT"}
    assert set(r.revisiones) == {"Claude → ChatGPT", "ChatGPT → Claude"}
    assert r.sintesis.endswith("Síntesis de Claude")
    # Cada miembro: 1 borrador + 1 revisión; el presidente, además, la síntesis.
    assert len(a.llamadas) == 3 and len(b.llamadas) == 2
    # La revisión cruzada recibe la respuesta del otro miembro, no la propia.
    revision_de_a = next(m for m in a.llamadas if "RESPUESTA A REVISAR" in m)
    assert "Borrador de ChatGPT" in revision_de_a and "Borrador de Claude" not in revision_de_a
    # El presidente no ve los nombres reales de los autores.
    sintesis = a.llamadas[-1]
    assert "### Borrador de Miembro A" in sintesis
    assert "### Borrador de Claude" not in sintesis and "### Borrador de ChatGPT" not in sintesis


def test_presidente_configurable_y_validaciones():
    a, b = MiembroFalso("Claude"), MiembroFalso("ChatGPT")
    r = Consejo([a, b], presidente=b, registro=lambda *_: None).deliberar("T")
    assert r.presidente == "ChatGPT" and "ChatGPT" in r.sintesis
    with pytest.raises(ValueError):
        Consejo([a])
    with pytest.raises(ValueError):
        Consejo([a, b]).deliberar("T", modo="inexistente")


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
