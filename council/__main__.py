"""Interfaz de línea de órdenes.

Ejemplos:
    python -m council contrato_revisar "Revisa este arrendamiento" --documento contrato.docx
    python -m council informe_tributario "Tributación de la venta de un inmueble heredado"
    python -m council procedimiento_tributario "Analiza esta propuesta de liquidación" \
        --documento propuesta.pdf --miembros claude perplexity
    python -m council dictamen_juridico "Riesgo de derivación de responsabilidad" --nivel extremo
"""

from __future__ import annotations

import argparse
import sys
from functools import partial

from .informe import leer_documento
from .prompts import MODOS
from .providers import NIVELES
from .servicio import FABRICAS, ejecutar


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="council",
                                description="Consejo de LLM (Claude, ChatGPT y Perplexity).")
    p.add_argument("modo", choices=list(MODOS), help="tipo de tarea")
    p.add_argument("tarea", help="instrucción para el consejo")
    p.add_argument("--documento", help="ruta a .txt, .md, .docx o .pdf")
    p.add_argument("--miembros", nargs="+", choices=list(FABRICAS), default=list(FABRICAS),
                   help="miembros del consejo (mínimo dos; por defecto, todos)")
    p.add_argument("--presidente", choices=list(FABRICAS), default="claude",
                   help="miembro que redacta la síntesis final (por defecto: claude)")
    p.add_argument("--nivel", choices=NIVELES, default="estandar",
                   help="«extremo»: modelos más capaces y esfuerzo máximo; solo para casos críticos "
                        "(mucho más lento y costoso)")
    p.add_argument("--seudonimizar", action="store_true",
                   help="sustituye DNI, NIE, CIF, IBAN, correos y teléfonos antes de enviar")
    p.add_argument("--salida", default="salidas", help="carpeta de resultados")
    args = p.parse_args(argv)

    salida = ejecutar(
        tarea=args.tarea,
        documento=leer_documento(args.documento) if args.documento else None,
        modo=args.modo,
        miembros=args.miembros,
        presidente=args.presidente,
        seudonimizar=args.seudonimizar,
        nivel=args.nivel,
        carpeta=args.salida,
        registro=partial(print, file=sys.stderr),
    )
    print(f"Informe: {salida.informe}\nRegistro de auditoría: {salida.registro}", file=sys.stderr)
    if salida.mapa:
        print(f"Mapa de seudonimización (confidencial): {salida.mapa}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
