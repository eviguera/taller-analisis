"""Briefing ejecutivo narrativo para GIRO.

Genera un resumen en lenguaje natural (espanol) de lo que esta pasando en el
negocio del workspace: que cambio desde la ultima vez, que necesita atencion,
que esta en riesgo y cual es la llamada principal del dia.

Inspirado en OpenExecutive (briefing/narrative.py): secciones de "Top call",
"Today", "What changed", "Needs you", "Waiting on", "At risk", y dias
tranquilos. Reglas de grounding: solo se citan personas, montos y fechas que
aparecen en los datos reales del workspace.

Por defecto usa plantillas determinísticas sobre los KPIs y alertas ya
calculados (sin costo de LLM). Si se configura un proveedor de LLM, se puede
sobreescribir `generar_briefing` para usar lenguaje generativo.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from .narrativo import (
    generar_briefing,
    resumen_ejecutivo,
    dia_tranquilo,
)

__all__ = ["generar_briefing", "resumen_ejecutivo", "dia_tranquilo"]
