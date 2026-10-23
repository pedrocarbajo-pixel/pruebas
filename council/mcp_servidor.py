"""Servidor MCP: permite convocar el consejo desde la aplicación de Claude (o Claude Code).

Claude ve cinco herramientas: convocar el consejo, consultar su estado, pedir una versión
corregida, exportar el informe y ver la configuración. Como una deliberación tarda minutos,
`convocar_consejo` devuelve un identificador y `estado_consulta` espera un rato a que termine
antes de responder; Claude repite la consulta hasta obtener el informe.

Arranque (lo hace la aplicación de Claude): python consejo_mcp.py
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer

from .documentos import EXTENSIONES, combinar, leer_documento
from .exportar import FORMATOS
from .modelos import candidatos
from .prompts import DELIBERACIONES, MODOS
from .servicio import NOMBRES, exportar_presidente, miembros_disponibles
from .trabajos import ConsultaNoEncontrada, ConsultaOcupada, GestorConsultas

ESPERA = float(os.getenv("COUNCIL_MCP_ESPERA", "40"))  # segundos que espera estado_consulta

INSTRUCCIONES = """\
Consejo de LLM: Claude, ChatGPT y Perplexity deliberan sobre tareas jurídicas y tributarias de alto \
riesgo (borradores independientes, revisión cruzada anónima y síntesis de un presidente).
Uso:
1. Llama a convocar_consejo con la tarea. Si el usuario menciona archivos de su ordenador, pasa sus \
rutas en «archivos»; si el contenido está en la conversación, pásalo en «texto_adicional».
2. La deliberación tarda varios minutos. Llama a estado_consulta con el identificador hasta que el \
estado sea «terminada» o «error»; cada llamada espera un rato antes de responder. Informa al usuario \
del avance entre llamadas. No presentes ningún resultado como definitivo antes de «terminada».
3. Presenta el informe del presidente completo y fiel, sin resumirlo salvo que el usuario lo pida, \
destacando las discrepancias entre miembros y las cuestiones que requieren verificación humana. \
Recuerda que es un borrador que debe revisar un profesional.
4. Para corregir el informe usa version_corregida; para obtener Word, PDF, etc., exportar_informe.
Usa nivel «extremo» solo si el usuario lo pide expresamente: es mucho más lento y costoso.
Modos de deliberación: «consejo» (C, por defecto); «agentes_claude» (A: Claude con cinco agentes de \
perspectivas distintas) y «consejo_agentes» (B: cada IA con sus cinco agentes y después el consejo). \
Usa A o B solo si el usuario lo pide."""

TipoTrabajo = Literal["general", "contrato_revisar", "contrato_redactar", "dictamen_juridico",
                      "informe_tributario", "procedimiento_tributario"]
Formato = Literal["docx", "pdf", "html", "md", "txt"]
assert set(TipoTrabajo.__args__) == set(MODOS) and set(Formato.__args__) == set(FORMATOS)


def crear_servidor(gestor: GestorConsultas, disponibles=miembros_disponibles) -> MCPServer:
    servidor = MCPServer("consejo-llm", instructions=INSTRUCCIONES)

    def describir(id_consulta: str) -> str:
        try:
            estado = gestor.estado(id_consulta, esperar=ESPERA)
        except ConsultaNoEncontrada:
            return (f"No existe la consulta «{id_consulta}». Las consultas se pierden si se cierra la "
                    "aplicación de Claude; convoque de nuevo el consejo.")
        ultimos = "\n".join(f"- {m}" for m in estado["mensajes"][-6:])
        if estado["estado"] == "en_curso":
            return (f"Estado: en_curso. El consejo sigue trabajando. Últimos avisos:\n{ultimos}\n\n"
                    f"Vuelve a llamar a estado_consulta con id_consulta={id_consulta}.")
        if estado["estado"] == "error":
            return f"Estado: error. La deliberación ha fallado: {estado['error']}\nAvisos:\n{ultimos}"
        salida = estado["salida"]
        r = salida.resultado
        partes = [f"Estado: terminada (versión {len(r.versiones) + 1}).",
                  f"Modelos: {', '.join(f'{n} ({m})' for n, m in r.modelos.items())}. Presidente: {r.presidente}."]
        if estado["error"]:
            partes.append(f"Aviso: {estado['error']}")
        if salida.mapa_datos:
            partes.append(f"Los datos personales aparecen seudonimizados ({len(salida.mapa_datos)} marcadores "
                          "como [DNI_1]); los archivos guardados en el ordenador contienen los datos reales.")
        partes += [f"Archivos: informe completo con anexos en {salida.informe.resolve()}; "
                   f"informe del presidente en Word en {salida.word.resolve()}.",
                   "", "INFORME DEL PRESIDENTE:", "", r.sintesis]
        return "\n".join(partes)

    @servidor.tool()
    def convocar_consejo(
        tarea: str,
        tipo_trabajo: TipoTrabajo = "general",
        deliberacion: Literal["consejo", "agentes_claude", "consejo_agentes"] = "consejo",
        nivel: Literal["estandar", "extremo"] = "estandar",
        archivos: list[str] | None = None,
        texto_adicional: str = "",
        miembros: list[Literal["claude", "chatgpt", "perplexity"]] | None = None,
        presidente: Literal["claude", "chatgpt", "perplexity"] = "claude",
        seudonimizar: bool = True,
    ) -> str:
        """Convoca al consejo de LLM (Claude, ChatGPT y Perplexity) para una tarea jurídica o tributaria.

        tipo_trabajo: general, contrato_revisar, contrato_redactar, dictamen_juridico,
        informe_tributario o procedimiento_tributario.
        deliberacion: «consejo» (C, por defecto: Claude, ChatGPT y Perplexity, 7 llamadas);
        «agentes_claude» (A: Claude con cinco agentes —escéptico, optimista, práctico, raíz y ojos
        nuevos—, 11 llamadas); «consejo_agentes» (B: cada IA con sus cinco agentes y después el consejo,
        37 llamadas con tres miembros: mucho más lento y costoso). Usa A o B solo si el usuario lo pide.
        nivel: «extremo» usa los modelos más capaces con esfuerzo máximo; solo si el usuario lo pide.
        archivos: rutas de archivos del ordenador del usuario (.docx, .pdf, .xlsx, .xlsm, .xls, .csv,
        .txt, .md); admite «~/».
        texto_adicional: contenido aportado en la conversación (p. ej., el texto de un documento).
        miembros: por defecto, todos los que tengan clave de API configurada (mínimo dos).
        seudonimizar: oculta DNI, NIE, CIF, IBAN, correos y teléfonos antes de enviarlos a los modelos.
        Devuelve el identificador de la consulta; después hay que llamar a estado_consulta."""
        if not tarea.strip():
            return "Error: falta la tarea."
        activos = [m for m, ok in disponibles().items() if ok]
        elegidos = ["claude"] if deliberacion == "agentes_claude" else (list(miembros) if miembros else activos)
        if sin_clave := [m for m in elegidos if m not in activos]:
            return f"Error: sin clave de API para {', '.join(sin_clave)}. Disponibles: {', '.join(activos)}."
        if len(elegidos) < 2 and deliberacion != "agentes_claude":
            return "Error: hacen falta al menos dos miembros con clave de API configurada."
        if presidente not in elegidos:
            presidente = elegidos[0]

        leidos = []
        for archivo in archivos or []:
            ruta = Path(archivo).expanduser()
            if ruta.suffix.lower() not in EXTENSIONES:
                return f"Error: formato no admitido ({ruta.name}). Admitidos: {', '.join(sorted(EXTENSIONES))}."
            if not ruta.is_file():
                return f"Error: no se encuentra el archivo {ruta}."
            try:
                leidos.append((ruta.name, leer_documento(ruta)))
            except Exception as e:
                return f"Error: no se pudo leer {ruta.name}: {e}"
        if texto_adicional.strip():
            leidos.append(("Texto aportado en la conversación", texto_adicional.strip()))

        id_consulta = gestor.iniciar(tarea=tarea.strip(), documento=combinar(leidos), modo=tipo_trabajo,
                                     miembros=elegidos, presidente=presidente, seudonimizar=seudonimizar,
                                     nivel=nivel, deliberacion=deliberacion)
        adjuntos = f" con {len(leidos)} documento(s)" if leidos else ""
        return (f"Consejo convocado{adjuntos}. id_consulta={id_consulta}. Deliberación: "
                f"{DELIBERACIONES[deliberacion][0]}. Miembros: {', '.join(NOMBRES[m] for m in elegidos)}; "
                f"presidente: {NOMBRES[presidente]}; nivel: {nivel}. La deliberación tarda varios minutos: "
                "llama ahora a estado_consulta.")

    @servidor.tool()
    def estado_consulta(id_consulta: str) -> str:
        """Estado de una consulta al consejo. Espera hasta unos 40 segundos a que termine antes de
        responder. Si sigue en curso, vuelve a llamarla; si ha terminado, devuelve el informe del
        presidente y la ubicación de los archivos guardados."""
        return describir(id_consulta)

    @servidor.tool()
    def version_corregida(id_consulta: str, instrucciones: str) -> str:
        """Pide al presidente una nueva versión completa del informe aplicando las indicaciones del
        usuario (p. ej., «añade las citas concretas de la Ley del IRPF»). Después, llama a
        estado_consulta para obtenerla."""
        if not instrucciones.strip():
            return "Error: indique qué debe cambiar en la nueva versión."
        try:
            gestor.refinar(id_consulta, instrucciones.strip())
        except ConsultaNoEncontrada:
            return f"No existe la consulta «{id_consulta}»."
        except ConsultaOcupada as e:
            return f"Error: {e}"
        return f"Versión corregida en preparación. Llama a estado_consulta con id_consulta={id_consulta}."

    @servidor.tool()
    def exportar_informe(id_consulta: str, formato: Formato = "docx") -> str:
        """Guarda el informe del presidente (versión vigente) en Word (docx), PDF, HTML, Markdown (md)
        o texto (txt) en el ordenador del usuario y devuelve la ruta del archivo."""
        try:
            estado = gestor.estado(id_consulta)
        except ConsultaNoEncontrada:
            return f"No existe la consulta «{id_consulta}»."
        if estado["estado"] == "en_curso" or not estado["salida"]:
            return "Error: la consulta aún no ha terminado."
        ruta = exportar_presidente(estado["salida"], formato).resolve()
        return f"Informe del presidente en {FORMATOS[formato][1]} guardado en: {ruta}"

    @servidor.tool()
    def configuracion_consejo() -> str:
        """Miembros disponibles, modelos que usa cada uno y tipos de trabajo admitidos."""
        lineas = ["Miembros:"]
        for clave, ok in disponibles().items():
            modelos = f"estándar {candidatos(clave, 'estandar')[0]}, extremo {candidatos(clave, 'extremo')[0]}"
            lineas.append(f"- {NOMBRES[clave]}: {'disponible' if ok else 'sin clave de API'} ({modelos})")
        lineas.append("Tipos de trabajo: " + ", ".join(f"{k} ({v[0]})" for k, v in MODOS.items()))
        lineas.append("Formatos de exportación: " + ", ".join(f"{k} ({v[1]})" for k, v in FORMATOS.items()))
        return "\n".join(lineas)

    return servidor


def main() -> None:
    from .config import cargar_env

    cargar_env()
    crear_servidor(GestorConsultas(os.getenv("COUNCIL_SALIDAS", "salidas"))).run("stdio")


if __name__ == "__main__":
    main()
