"""Modelos que usa cada miembro del consejo, por nivel.

Cada lista va de más preferido a menos: si la cuenta no tiene acceso a un modelo (o el
proveedor lo retira), el miembro pasa automáticamente al siguiente y el informe lo indica.
Este archivo se revisa periódicamente para incorporar los modelos nuevos que se publiquen.

Las variables de entorno (.env) tienen prioridad y admiten también listas separadas por
comas, p. ej. OPENAI_MODEL=gpt-6.1-sol,gpt-6-sol.
"""

from __future__ import annotations

import os

REVISADO = "2026-10-21"

MODELOS: dict[str, dict[str, list[str]]] = {
    "claude": {
        "estandar": ["claude-opus-5-5"],
        "extremo": ["claude-opus-5-5"],
    },
    "chatgpt": {
        "estandar": ["gpt-6.1-sol", "gpt-6-sol", "gpt-5"],
        "extremo": ["gpt-6-astra", "gpt-6.1-sol", "gpt-5.5-pro"],
    },
    # Presets de la Agent API de Perplexity. Según su guía de migración, «high» equivale a
    # Sonar Deep Research y «low» a Sonar Reasoning Pro; «fast», a Sonar Pro.
    "perplexity": {
        "estandar": ["sonar-pro", "fast"],
        "extremo": ["high", "low", "sonar-pro"],
    },
}

VARIABLES = {
    ("claude", "estandar"): "CLAUDE_MODEL",
    ("claude", "extremo"): "CLAUDE_MODEL_EXTREMO",
    ("chatgpt", "estandar"): "OPENAI_MODEL",
    ("chatgpt", "extremo"): "OPENAI_MODEL_EXTREMO",
    ("perplexity", "estandar"): "PERPLEXITY_PRESET",
    ("perplexity", "extremo"): "PERPLEXITY_PRESET_EXTREMO",
}


def candidatos(proveedor: str, nivel: str) -> list[str]:
    """Modelos a probar, en orden: los de .env si están definidos; si no, los de este archivo."""
    valor = os.getenv(VARIABLES[(proveedor, nivel)], "")
    propios = [m.strip() for m in valor.split(",") if m.strip()]
    return propios or list(MODELOS[proveedor][nivel])
