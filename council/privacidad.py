"""Seudonimización reversible de datos personales antes de enviarlos a los proveedores.

Detecta patrones habituales en documentos españoles (DNI, NIE, CIF, IBAN, correo electrónico
y teléfono). No detecta nombres propios ni direcciones: revise el documento antes de enviarlo.
"""

from __future__ import annotations

import re

PATRONES = {
    "EMAIL": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    "IBAN": r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){4,7}(?:[ ]?[A-Z0-9]{1,3})?\b",
    "DNI": r"\b\d{8}[ -]?[A-Z]\b",
    "NIE": r"\b[XYZ][ -]?\d{7}[ -]?[A-Z]\b",
    "CIF": r"\b[ABCDEFGHJNPQRSUVW][ -]?\d{7}[ -]?[0-9A-J]\b",
    "TELEFONO": r"(?<!\w)(?:\+34[ ]?)?[6789]\d{2}(?:[ ]?\d{3}){2}(?!\w)",
}


def seudonimizar(texto: str) -> tuple[str, dict[str, str]]:
    """Sustituye los datos detectados por marcadores [TIPO_n] y devuelve el mapa inverso."""
    mapa: dict[str, str] = {}
    vistos: dict[str, str] = {}
    for tipo, patron in PATRONES.items():
        def sustituir(m: re.Match) -> str:
            valor = m.group(0)
            if valor not in vistos:
                marcador = f"[{tipo}_{sum(k.startswith(f'[{tipo}_') for k in mapa) + 1}]"
                vistos[valor] = marcador
                mapa[marcador] = valor
            return vistos[valor]

        texto = re.sub(patron, sustituir, texto)
    return texto, mapa


def restaurar(texto: str, mapa: dict[str, str]) -> str:
    for marcador, valor in mapa.items():
        texto = texto.replace(marcador, valor)
    return texto
