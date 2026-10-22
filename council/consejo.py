"""Orquestación del consejo: borradores independientes, revisión cruzada y síntesis."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
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
    # Versiones anteriores de la síntesis: {"fecha", "instrucciones", "sintesis"}
    versiones: list[dict[str, str]] = field(default_factory=list)
    # Miembros que fallaron durante la deliberación y en qué fase.
    incidencias: list[str] = field(default_factory=list)


def alias_de(nombres) -> dict[str, str]:
    """Alias anónimos («Miembro A», «Miembro B»…) en el orden de los miembros."""
    return {nombre: f"Miembro {chr(65 + i)}" for i, nombre in enumerate(nombres)}


def materiales(r: Resultado) -> str:
    """Borradores y revisiones con los autores anonimizados, en el orden de los miembros."""
    alias = alias_de(r.borradores)
    partes = [
        f"### Borrador de {alias[nombre]}\n<<<\n{texto}\n>>>"
        for nombre, texto in r.borradores.items()
    ]
    partes += [
        f"### Revisión de {alias[revisor]} sobre los demás miembros\n<<<\n{texto}\n>>>"
        for revisor, texto in r.revisiones.items()
    ]
    return "\n\n".join(partes)


def refinar(presidente: Miembro, r: Resultado, instrucciones: str,
            documento: str | None = None) -> Resultado:
    """Pide al presidente una nueva versión de la síntesis según las indicaciones del usuario.

    La versión vigente pasa al historial (`r.versiones`) y `r.sintesis` recibe la nueva.
    """
    if not instrucciones.strip():
        raise ValueError("Indique qué debe cambiar en la nueva versión.")
    mensaje = prompts.FASE_REFINAMIENTO.format(
        modo=prompts.MODOS[r.modo][1],
        tarea=r.tarea,
        documento=prompts.bloque_documento(documento),
        materiales=materiales(r),
        sintesis=r.sintesis,
        instrucciones=instrucciones,
    )
    nueva = presidente.preguntar(prompts.sistema(r.nivel), mensaje)
    r.versiones.append({
        "fecha": datetime.now(timezone.utc).isoformat(),
        "instrucciones": instrucciones,
        "sintesis": r.sintesis,
    })
    r.sintesis = nueva
    return r


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
            {m.nombre: (m, mensaje) for m in self.miembros}, "ha entregado su borrador",
            resultado, "borrador")
        # Solo siguen los miembros que han entregado borrador.
        activos = [m for m in self.miembros if m.nombre in resultado.borradores]
        if len(activos) < 2:
            raise RuntimeError("Menos de dos miembros han podido participar: " + "; ".join(resultado.incidencias))

        self.registro("Fase 2/3 · Revisión cruzada…")
        # Los autores se anonimizan para que nadie favorezca (ni penalice) una respuesta por su origen.
        alias = alias_de(resultado.borradores)
        encargos = {}
        for revisor in activos:
            respuestas = "\n\n".join(
                f"### Respuesta de {alias[autor.nombre]}\n<<<\n{resultado.borradores[autor.nombre]}\n>>>"
                for autor in activos
                if autor is not revisor
            )
            msg = prompts.FASE_REVISION_CRUZADA.format(**contexto, respuestas=respuestas)
            encargos[revisor.nombre] = (revisor, msg)
        # Una revisión fallida no impide la síntesis: se trabaja con las que haya.
        resultado.revisiones = self._en_paralelo(encargos, "ha entregado su revisión", resultado, "revisión")

        presidentes = [self.presidente] + [m for m in activos if m is not self.presidente]
        for presidente in presidentes:
            if presidente not in activos:
                continue
            self.registro(f"Fase 3/3 · Síntesis del presidente ({presidente.nombre})…")
            try:
                resultado.sintesis = presidente.preguntar(
                    self.sistema,
                    prompts.FASE_SINTESIS.format(**contexto, materiales=materiales(resultado)),
                )
            except Exception as e:
                self._incidencia(resultado, presidente.nombre, "síntesis", e)
                continue
            resultado.presidente = presidente.nombre
            break
        else:
            raise RuntimeError("Ningún miembro ha podido redactar la síntesis: " + "; ".join(resultado.incidencias))
        self.registro(f"✓ {resultado.presidente} ha entregado la síntesis final.")
        # Se anota al final porque el esfuerzo efectivo puede haberse rebajado durante la deliberación.
        resultado.modelos = {
            m.nombre: m.descripcion() if hasattr(m, "descripcion") else m.modelo
            for m in self.miembros
        }
        self.registro("Deliberación terminada.")
        return resultado

    def _en_paralelo(self, encargos: dict[str, tuple[Miembro, str]], aviso: str,
                     resultado: Resultado, fase: str) -> dict[str, str]:
        """Ejecuta los encargos en paralelo. Un miembro que falla no detiene a los demás: se
        anota como incidencia y queda fuera del resultado."""
        with ThreadPoolExecutor(max_workers=len(encargos)) as ejecutor:
            futuros = {
                ejecutor.submit(miembro.preguntar, self.sistema, mensaje): clave
                for clave, (miembro, mensaje) in encargos.items()
            }
            # Se avisa de cada entrega en cuanto llega, para que el progreso sea visible.
            resultados = {}
            for hecho, futuro in enumerate(as_completed(futuros), 1):
                clave = futuros[futuro]
                try:
                    resultados[clave] = futuro.result()
                except Exception as e:
                    self._incidencia(resultado, clave, fase, e)
                    continue
                self.registro(f"✓ {clave} {aviso} ({hecho} de {len(encargos)}).")
            # Se conserva el orden de los miembros, del que depende su alias anónimo.
            return {clave: resultados[clave] for clave in encargos if clave in resultados}

    def _incidencia(self, resultado: Resultado, nombre: str, fase: str, error: Exception) -> None:
        texto = f"{nombre} no pudo completar su {fase}: {type(error).__name__}: {str(error)[:300]}"
        resultado.incidencias.append(texto)
        self.registro(f"✗ {texto}")
