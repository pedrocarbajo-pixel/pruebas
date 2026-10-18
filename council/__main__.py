"""Interfaz de línea de órdenes.

Ejemplos:
    python -m council revisar --documento contrato.docx "Revisa este contrato de arrendamiento"
    python -m council redactar "Redacta un NDA mutuo entre dos sociedades españolas"
    python -m council general "Analiza los riesgos de esta operación societaria" --presidente chatgpt
"""

from __future__ import annotations

import argparse
import json
import sys
from functools import partial

from . import privacidad
from .consejo import Consejo
from .informe import guardar, leer_documento
from .prompts import MODOS
from .providers import MiembroClaude, MiembroOpenAI


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="council", description="Consejo de LLM (Claude + ChatGPT).")
    p.add_argument("modo", choices=list(MODOS), help="tipo de tarea")
    p.add_argument("tarea", help="instrucción para el consejo")
    p.add_argument("--documento", help="ruta a .txt, .md, .docx o .pdf")
    p.add_argument("--presidente", choices=["claude", "chatgpt"], default="claude",
                   help="miembro que redacta la síntesis final (por defecto: claude)")
    p.add_argument("--seudonimizar", action="store_true",
                   help="sustituye DNI, NIE, CIF, IBAN, correos y teléfonos antes de enviar")
    p.add_argument("--salida", default="salidas", help="carpeta de resultados")
    args = p.parse_args(argv)

    tarea = args.tarea
    documento = leer_documento(args.documento) if args.documento else None
    mapa: dict[str, str] = {}
    if args.seudonimizar:
        # Tarea y documento se procesan juntos para que un mismo dato reciba el mismo marcador.
        separador = "\n\x00\n"
        combinado, mapa = privacidad.seudonimizar(tarea + separador + (documento or ""))
        tarea, documento = combinado.split(separador, 1)
        documento = documento or None
        print(f"Seudonimizados {len(mapa)} datos.", file=sys.stderr)

    claude, chatgpt = MiembroClaude(), MiembroOpenAI()
    presidente = claude if args.presidente == "claude" else chatgpt
    consejo = Consejo([claude, chatgpt], presidente=presidente,
                      registro=partial(print, file=sys.stderr))
    resultado = consejo.deliberar(tarea, documento, modo=args.modo)

    restaurar = partial(privacidad.restaurar, mapa=mapa) if mapa else None
    ruta_md, ruta_json = guardar(resultado, args.salida, restaurar=restaurar)
    print(f"Informe: {ruta_md}\nRegistro de auditoría: {ruta_json}", file=sys.stderr)
    if mapa:
        # El mapa contiene los datos reales: se guarda aparte para poder custodiarlo.
        (ruta_json.parent / f"mapa_{ruta_json.stem}.json").write_text(
            json.dumps(mapa, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
