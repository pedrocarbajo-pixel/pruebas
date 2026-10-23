"""Equipos de cinco agentes con perspectivas distintas (opciones A y B).

Un equipo está formado por cinco instancias de un mismo modelo, cada una con un papel: el
escéptico, el optimista, el práctico, el de la raíz y el de ojos nuevos (véase prompts.ROLES).

1. Cada agente analiza la tarea por su cuenta, en paralelo.
2. Cada agente revisa los análisis de los demás, identificados solo como «Agente N»: el número
   se asigna al azar en cada deliberación, así que el revisor no sabe qué papel tiene cada uno.
3. Un coordinador integra análisis y revisiones (conociendo ya el papel de cada agente).

Opción A: el equipo de Claude entrega directamente el informe final.
Opción B: cada miembro del consejo responde con su equipo y después delibera el consejo.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable

from . import prompts
from .consejo import Resultado, en_paralelo
from .providers import Miembro

MINIMO_AGENTES = 2


@dataclass
class TrabajoEquipo:
    sintesis: str
    borradores: dict[str, str]  # clave: nombre del papel («El escéptico»…)
    revisiones: dict[str, str]
    incidencias: list[str] = field(default_factory=list)
    descripcion: str = ""


class Equipo:
    def __init__(self, fabrica: Callable[[], Miembro], nombre: str, nivel: str = "estandar",
                 registro=print, fases_principales: bool = False):
        # Cada agente usa su propia instancia del modelo: las instancias guardan estado (modelo de
        # reserva, esfuerzo rebajado) y no deben compartirse entre llamadas simultáneas.
        self.fabrica = fabrica
        self.nombre = nombre
        self.nivel = nivel
        self.registro = registro
        # En la opción A los pasos del equipo son las fases de la consulta («Fase 1/3…»).
        self.fases_principales = fases_principales

    def _fase(self, numero: int, texto: str) -> None:
        if self.fases_principales:
            self.registro(f"Fase {numero}/3 · {texto[0].upper()}{texto[1:]}…")
        else:
            self.registro(f"{self.nombre} · equipo de agentes: {texto}…")

    def deliberar(self, contexto: dict, final: bool) -> TrabajoEquipo:
        """`contexto`: modo, tarea y documento ya formateados. `final`: si la síntesis es el informe
        definitivo (opción A) o la respuesta del miembro al consejo (opción B)."""
        roles = list(prompts.ROLES)
        numeros = random.sample(range(1, len(roles) + 1), len(roles))
        alias = {rol: f"Agente {n}" for rol, n in zip(roles, numeros)}
        nombre_rol = {rol: prompts.ROLES[rol][0] for rol in roles}
        incidencias: list[str] = []

        def fallo(fase: str):
            def anotar(rol: str, error: Exception) -> None:
                texto = (f"{self.nombre} · {nombre_rol[rol]} no pudo completar su {fase}: "
                         f"{type(error).__name__}: {str(error)[:300]}")
                incidencias.append(texto)
                self.registro(f"✗ {texto}")
            return anotar

        def entrega(que: str):
            return lambda rol, hecho, total: self.registro(
                f"✓ {self.nombre} · {nombre_rol[rol]} ha entregado su {que} ({hecho} de {total}).")

        # 1. Análisis independientes
        self._fase(1, "análisis independiente de los cinco agentes")
        agentes = {}
        mensaje = prompts.FASE_BORRADOR.format(**contexto)

        def analizar(rol: str) -> str:
            agentes[rol] = self.fabrica()
            return agentes[rol].preguntar(prompts.sistema_agente(self.nivel, rol), mensaje)

        analisis = en_paralelo({rol: (lambda rol=rol: analizar(rol)) for rol in roles},
                               entrega("análisis"), fallo("análisis"))
        if len(analisis) < MINIMO_AGENTES:
            raise RuntimeError(f"El equipo de {self.nombre} se ha quedado con menos de {MINIMO_AGENTES} "
                               "agentes: " + "; ".join(incidencias))

        # 2. Revisión cruzada anónima: cada revisor ve a los demás en un orden aleatorio propio.
        self._fase(2, "revisión cruzada anónima entre agentes")

        def revisar(rol: str) -> str:
            otros = [r for r in analisis if r != rol]
            random.shuffle(otros)
            respuestas = "\n\n".join(f"### Análisis del {alias[r]}\n<<<\n{analisis[r]}\n>>>" for r in otros)
            return agentes[rol].preguntar(
                prompts.sistema_agente(self.nivel, rol),
                prompts.AGENTES_REVISION.format(**contexto, respuestas=respuestas))

        revisiones = en_paralelo({rol: (lambda rol=rol: revisar(rol)) for rol in analisis},
                                 entrega("revisión"), fallo("revisión"))

        # 3. Síntesis del coordinador, que sí conoce el papel de cada agente.
        self._fase(3, "síntesis del coordinador")
        materiales = "\n\n".join(
            [f"### Análisis del {alias[r]} ({nombre_rol[r]})\n<<<\n{texto}\n>>>" for r, texto in analisis.items()]
            + [f"### Revisión del {alias[r]} ({nombre_rol[r]}) sobre los demás\n<<<\n{texto}\n>>>"
               for r, texto in revisiones.items()])
        coordinador = self.fabrica()
        sintesis = coordinador.preguntar(
            prompts.sistema(self.nivel),
            prompts.AGENTES_SINTESIS.format(
                **contexto, materiales=materiales,
                entrega=prompts.ENTREGA_FINAL if final else prompts.ENTREGA_EQUIPO))
        self.registro(f"✓ {self.nombre} · el coordinador ha entregado la síntesis del equipo.")

        descripcion = coordinador.descripcion() if hasattr(coordinador, "descripcion") else coordinador.modelo
        return TrabajoEquipo(
            sintesis=sintesis,
            borradores={nombre_rol[r]: t for r, t in analisis.items()},
            revisiones={nombre_rol[r]: t for r, t in revisiones.items()},
            incidencias=incidencias,
            descripcion=descripcion,
        )


def deliberar_con_agentes(fabrica: Callable[[], Miembro], nombre: str, tarea: str, documento: str | None,
                          modo: str = "general", nivel: str = "estandar", registro=print) -> Resultado:
    """Opción A: un único modelo trabaja con su equipo de cinco agentes y entrega el informe final."""
    if modo not in prompts.MODOS:
        raise ValueError(f"Modo desconocido: {modo}. Opciones: {', '.join(prompts.MODOS)}")
    contexto = {"modo": prompts.MODOS[modo][1], "tarea": tarea, "documento": prompts.bloque_documento(documento)}
    if nivel == "extremo":
        registro("Nivel EXTREMO: modelos más capaces y esfuerzo máximo (más lento y costoso).")
    trabajo = Equipo(fabrica, nombre, nivel, registro, fases_principales=True).deliberar(contexto, final=True)
    registro("Deliberación terminada.")
    return Resultado(
        tarea=tarea, modo=modo, presidente=f"{nombre} (coordinador)", nivel=nivel,
        borradores=trabajo.borradores, revisiones=trabajo.revisiones, sintesis=trabajo.sintesis,
        modelos={nombre: f"{trabajo.descripcion} · equipo de cinco agentes"},
        incidencias=trabajo.incidencias, deliberacion="agentes_claude",
    )
