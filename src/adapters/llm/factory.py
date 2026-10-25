"""Factory para adaptador LLM según configuración."""
from __future__ import annotations

import os

from src.adapters.llm.openrouter import OpenRouterAdapter


def obtener_adaptador_llm():
    prov = (os.environ.get("GIRO_IA_PROVIDER") or "openrouter").strip().lower()
    if prov == "openrouter":
        return OpenRouterAdapter()
    # Por ahora solo OpenRouter en esta iteración
    return OpenRouterAdapter()
