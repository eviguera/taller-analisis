"""Suite de evaluación determinística para GIRO.

Escenarios que verifican que las recomendaciones y alertas se comportan
según lo esperado, sin depender de un LLM. Cada escenario define datos de
entrada simulados, la función bajo prueba y las aserciones esperadas.

Inspirado en OpenExecutive (evals/): escenarios con rubrica y umbral, pero
ejecutados con unittest (la stdlib que ya usa el repo en tests/), sin
dependencias nuevas.

Ejecutar:
    .venv/bin/python -m unittest discover -s src/evaluacion
"""

from __future__ import annotations

from .scenarios import ESCENARIOS, ejecutar_todos, escenario_recomendacion_churn, escenario_alerta_stock_bajo, escenario_proximo_servicio

__all__ = [
    "ESCENARIOS",
    "ejecutar_todos",
    "escenario_recomendacion_churn",
    "escenario_alerta_stock_bajo",
    "escenario_proximo_servicio",
]
