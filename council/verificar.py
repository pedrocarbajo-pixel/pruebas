"""Comprueba que cada proveedor responde con la clave y el modelo configurados.

Uso:
    python -m council.verificar             # nivel estándar
    python -m council.verificar --extremo   # además, los modelos del nivel extremo

Hace una llamada mínima por proveedor y nivel, con un coste muy reducido.
"""

from __future__ import annotations

import argparse
import os
import sys

from .config import cargar_env
from .servicio import CLAVES_API, FABRICAS, NOMBRES

SISTEMA = "Responde exclusivamente con la palabra OK."
MENSAJE = "Prueba de conexión."


def verificar(niveles: list[str], fabricas: dict | None = None, claves: dict | None = None,
              escribir=print) -> int:
    """Devuelve el número de miembros que pueden formar consejo en todos los niveles pedidos."""
    fabricas = fabricas or FABRICAS
    claves = CLAVES_API if claves is None else claves
    operativos = 0
    for clave, fabrica in fabricas.items():
        nombre = NOMBRES.get(clave, clave)
        if clave in claves and not _hay_clave(claves[clave]):
            escribir(f"[ -- ] {nombre}: sin clave ({claves[clave]} vacía en .env); no participará.")
            continue
        correcto = True
        for nivel in niveles:
            try:
                miembro = fabrica(nivel=nivel)
                respuesta = miembro.preguntar(SISTEMA, MENSAJE)
                modelo = miembro.descripcion() if hasattr(miembro, "descripcion") else miembro.modelo
                escribir(f"[ OK ] {nombre} · {nivel}: {modelo} → «{respuesta.strip()[:40]}»")
            except Exception as e:
                correcto = False
                escribir(f"[FALLO] {nombre} · {nivel}: {_explicar(e)}")
                escribir(f"        Detalle técnico: {type(e).__name__}: {str(e)[:200]}")
        operativos += correcto
    if operativos >= 2:
        escribir(f"\nConsejo operativo con {operativos} miembros.")
    else:
        escribir("\nHacen falta al menos dos miembros operativos. Revise las claves y los modelos en .env.")
    return operativos


def _explicar(error: Exception) -> str:
    """Traduce los errores más habituales a una indicación de cómo resolverlos."""
    estado = getattr(error, "status_code", None)
    nombre = type(error).__name__
    if estado == 401 or nombre == "AuthenticationError":
        return "la clave de API no es válida. Cópiela de nuevo desde la consola del proveedor."
    if estado == 403 or nombre == "PermissionDeniedError":
        return "la cuenta no tiene acceso a este modelo o función. Revise el plan contratado."
    if estado == 404 or nombre == "NotFoundError":
        return "el modelo indicado no existe o no está disponible. Revise su nombre en .env."
    if estado == 402 or "credit" in str(error).lower() or "quota" in str(error).lower():
        return "no hay saldo o se ha alcanzado el límite de gasto. Revise la facturación."
    if estado == 429 or nombre == "RateLimitError":
        return "límite de peticiones alcanzado. Espere unos minutos y vuelva a intentarlo."
    if estado == 400 or nombre == "BadRequestError":
        return "el proveedor ha rechazado la petición (parámetro o modelo no admitido)."
    if "Connection" in nombre or "Timeout" in nombre:
        return "no se ha podido conectar. Compruebe la conexión a internet o el cortafuegos."
    return "error inesperado; consulte el detalle técnico."


def _hay_clave(variable: str) -> bool:
    return bool(os.getenv(variable))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="council.verificar", description=__doc__.splitlines()[0])
    p.add_argument("--extremo", action="store_true", help="verifica también el nivel extremo")
    args = p.parse_args(argv)
    cargar_env()
    niveles = ["estandar", "extremo"] if args.extremo else ["estandar"]
    return 0 if verificar(niveles) >= 2 else 1


if __name__ == "__main__":
    sys.exit(main())
