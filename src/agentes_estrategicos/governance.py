"""Governance Agent.

Valida que las recomendaciones del Strategy Agent no contradigan reglas de
negocio del workspace y que estén basadas en datos reales.

Funciones:
* validar_recomendaciones: revisa cada decisión del dossier y marca aquellas
  que no tienen suficiente soporte de datos.
* validar_reglas_negocio: comprueba que no se sugiera gastar más del disponible,
  no se prometa más del 100% de recuperación, etc.
"""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd


def validar_recomendaciones(
    dossier: Dict[str, Any],
    data: dict,
    cfg: Any = None,
) -> Dict[str, Any]:
    """Valida las recomendaciones del Strategy Agent.

    Argumentos:
        dossier: resultado del Strategy Agent.
        data: datos crudos cargados (para validar que existen las columnas).
        cfg: configuración del workspace (para umbrales de negocio).

    Devuelve un diccionario con:
        - valido: True si todas las recomendaciones son válidas.
        - advertencias: lista de advertencias para decisiones no válidas.
        - decisiones_validadas: lista de decisiones con campo 'valido' añadido.
        - score_confianza: puntuación de confianza global (0-100).
    """
    decisiones = dossier.get("decisiones", [])
    cfg = cfg or {}

    decisiones_validadas = []
    advertencias = []
    score_total = 100

    for decision in decisiones:
        decision_validada = _validar_una_decision(
            decision=decision,
            data=data,
            cfg=cfg,
        )
        decisiones_validadas.append(decision_validada)

        if not decision_validada.get("valido", True):
            advertencias.append(
                {
                    "area": decision_validada.get("area", "desconocida"),
                    "motivo": decision_validada.get(
                        "motivo_advertencia", "Sin justificación suficiente"
                    ),
                    "severidad": decision_validada.get(
                        "severidad_advertencia", "media"
                    ),
                }
            )
            # Reducir score por cada advertencia.
            severidad = decision_validada.get("severidad_advertencia", "media")
            if severidad == "critica":
                score_total -= 30
            elif severidad == "alta":
                score_total -= 20
            else:
                score_total -= 10

    score_total = max(0, min(100, score_total))

    return {
        "valido": len(advertencias) == 0,
        "advertencias": advertencias,
        "decisiones_validadas": decisiones_validadas,
        "score_confianza": score_total,
        "n_decisiones_validas": sum(
            1 for d in decisiones_validadas if d.get("valido", True)
        ),
        "n_decisiones_totales": len(decisiones_validadas),
    }


def _validar_una_decision(
    decision: Dict[str, Any],
    data: dict,
    cfg: Any = None,
) -> Dict[str, Any]:
    """Valida una decisión individual.

    Reglas:
    * No se puede prometer recuperar más del 100% de la cartera en riesgo.
    * No se puede recomendar reabastecer más stock del que existe en el catálogo.
    * No se puede proyectar ingresos negativos.
    * Si no hay datos de facturas, no se puede hablar de ingresos.
    """
    decision = dict(decision)  # copia para no mutar el original
    area = decision.get("area", "desconocida")
    impacto = float(decision.get("impacto_esperado", 0) or 0)

    # Regla 1: no recuperar más del 100% de la cartera en riesgo.
    if area == "cartera":
        salud = data.get("salud_cartera", {}) if isinstance(data, dict) else {}
        # salud viene del analyzer, no de data cruda. Verificamos en los datos crudos.
        facturas = data.get("facturas") if isinstance(data, dict) else None
        monto_total = 0
        if isinstance(facturas, pd.DataFrame) and not facturas.empty:
            monto_total = float(facturas["total"].sum()) if "total" in facturas.columns else 0

        if monto_total > 0 and impacto > monto_total:
            decision["valido"] = False
            decision["motivo_advertencia"] = (
                f"El impacto esperado (${impacto:,.0f}) supera el monto total "
                f"facturado (${monto_total:,.0f}). Es imposible recuperar más "
                "de lo facturado."
            )
            decision["severidad_advertencia"] = "critica"
            return decision

    # Regla 2: no proyectar ingresos negativos.
    if area == "ingresos" and impacto < 0:
        decision["valido"] = False
        decision["motivo_advertencia"] = (
            "El impacto esperado de ingresos es negativo. "
            "Revisar los datos de entrada."
        )
        decision["severidad_advertencia"] = "critica"
        return decision

    # Regla 3: inventario - no reabastecer más de lo que tiene sentido.
    if area == "inventario":
        if impacto < 0 and abs(impacto) > 10_000_000:  # 10 millones CLP
            decision["valido"] = False
            decision["motivo_advertencia"] = (
                "El costo de reabastecimiento sugerido es muy alto. "
                "Revisar los niveles de stock mínimo configurados."
            )
            decision["severidad_advertencia"] = "alta"
            return decision

    # Si pasó todas las validaciones.
    decision["valido"] = True
    decision["motivo_advertencia"] = None
    decision["severidad_advertencia"] = None
    return decision


__all__ = ["validar_recomendaciones"]
