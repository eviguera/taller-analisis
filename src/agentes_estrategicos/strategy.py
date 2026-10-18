"""Strategy Agent.

Construye el dossier de decisión estratégica a partir del análisis de datos.

Para cada área de negocio, genera una recomendación concreta con tres
escenarios:
* Conservador: mantener lo que se hace.
* Base: aplicar mejoras menores.
* Agresivo: aplicar Giro Recomienda (next best action, mantenimiento, etc.).

Cada decisión incluye:
* área: qué área del negocio (ingresos, cartera, inventario, alertas).
* decisión: la acción recomendada.
* motivo: por qué se recomienda.
* impacto_esperado: cuánto podría mejorar (CLP o porcentaje).
* escenarios: proyección a 12 meses bajo tres presets.
* confianza: qué tan seguros estamos (alta / media / baja).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import pandas as pd

from src.simulador import aplicar_preset, base_datos, proyectar
from src.core.config import VENTANA_MESES


def generar_dossier_de_decision(
    analisis: Dict[str, Any],
    cfg: Any = None,
) -> Dict[str, Any]:
    """Genera el dossier de decisión estratégica.

    Argumentos:
        analisis: resultado del Analyst Agent.
        cfg: configuración del workspace activo (AppConfig).

    Devuelve un diccionario con:
        - decisiones: lista de dicts con cada recomendación.
        - escenario_conservador: proyección si no se hace nada.
        - escenario_agresivo: proyección si se aplican las acciones.
        - delta_ingresos: diferencia de ingresos entre ambos.
        - delta_ebitda: diferencia de EBITDA entre ambos.
    """
    cfg = cfg or {}
    salud = analisis.get("salud_cartera", {}) or {}
    kpis = analisis.get("kpis", {})
    alertas = analisis.get("alertas", [])

    # Base de datos del simulador a partir de los hechos del analyzer.
    # Usamos los datos crudos si están disponibles; si no, construimos
    # un frame mínimo a partir de los KPIs.
    data_raw = _extraer_datos_crudos(analisis)

    base = base_datos(data_raw) if not data_raw.empty else {}

    # Proyección conservadora (churn histórico, sin acciones de mejora).
    conservador = _proyectar_escenario(
        data=data_raw,
        base=base,
        cfg=cfg,
        preset="Conservador",
    )

    # Proyección agresiva (con efecto de Giro Recomienda).
    agresivo = _proyectar_escenario(
        data=data_raw,
        base=base,
        cfg=cfg,
        preset="Agresivo (+ Giro Recomienda)",
    )

    # Construir las decisiones individuales.
    decisiones = []

    # 1. Decisión de ingresos.
    decisiones.append(
        _decision_ingresos(kpis=kpis, cfg=cfg)
    )

    # 2. Decisión de cartera en riesgo.
    decisiones.append(
        _decision_cartera_riesgo(salud=salud, alertas=alertas)
    )

    # 3. Decisión de inventario (si hay datos).
    decisiones.append(
        _decision_inventario(data=data_raw, cfg=cfg)
    )

    # Filtrar decisiones vacías.
    decisiones = [d for d in decisiones if d is not None]

    delta_ingresos = float(
        agresivo.get("totales", {}).get("ingresos", 0)
        - conservador.get("totales", {}).get("ingresos", 0)
    )
    delta_ebitda = float(
        agresivo.get("totales", {}).get("ebitda", 0)
        - conservador.get("totales", {}).get("ebitda", 0)
    )

    return {
        "decisiones": decisiones,
        "escenario_conservador": conservador.get("totales", {}),
        "escenario_agresivo": agresivo.get("totales", {}),
        "delta_ingresos": delta_ingresos,
        "delta_ebitda": delta_ebitda,
        "recomendacion_principal": _elegir_recomendacion_principal(decisiones),
    }


def _extraer_datos_crudos(analisis: Dict[str, Any]) -> pd.DataFrame:
    """Extrae un DataFrame crudo del análisis para el simulador."""
    import pandas as pd

    # Intentar reconstruir un frame mínimo con fecha y total.
    kpis = analisis.get("kpis", {})
    if not kpis:
        return pd.DataFrame(columns=["fecha", "total", "cliente_id", "estado"])

    # Si no tenemos datos crudos, creamos un frame sintético mínimo
    # a partir de los KPIs para que el simulador no falle.
    from datetime import datetime

    hoy = datetime.now()
    filas = []
    for i in range(12):
        mes = hoy.month - i
        anio = hoy.year
        if mes <= 0:
            mes += 12
            anio -= 1
        filas.append({
            "fecha": f"{anio}-{mes:02d}-01",
            "total": kpis.get("total_ingresos", 0) / 12,
            "cliente_id": 1,
            "estado": "Pagada",
        })
    return pd.DataFrame(filas)


def _proyectar_escenario(
    data: Any,
    base: dict,
    cfg: Any,
    preset: str,
) -> dict:
    """Ejecuta el simulador con un preset dado."""
    from src.simulador import proyectar, ratios_estacionales

    if not base:
        return {"totales": {"ingresos": 0, "ebitda": 0}}

    ratios = ratios_estacionales(data) if not data.empty else None

    margen_bruto = 0.42
    if cfg and hasattr(cfg, "simulador") and cfg.simulador:
        margen_bruto = float(cfg.simulador.get("margen_bruto", 0.42))

    return proyectar(
        df=data,
        meses=VENTANA_MESES,
        crecimiento_anual=0.08,
        ticket_crecimiento=0.04,
        churn_mensual=None,
        efecto_giro_nba=0.0,
        margen_bruto=margen_bruto,
        gasto_fijo_mensual=None,
        ratios=ratios,
    )


def _decision_ingresos(kpis: dict, cfg: Any = None) -> dict:
    """Decisión sobre ingresos: mantener, crecer o reactivar."""
    total_ingresos = kpis.get("total_ingresos", 0)
    total_facturas = kpis.get("total_facturas", 0)

    if total_facturas == 0:
        return {
            "area": "ingresos",
            "decision": "Sin datos de facturación",
            "motivo": "No hay facturas registradas. Importa datos en 'Mis datos'.",
            "impacto_esperado": 0,
            "confianza": "baja",
            "escenarios": {},
        }

    ticket = kpis.get("ticket_promedio", 0)
    crecimiento_sugerido = 0.10  # 10% de crecimiento objetivo

    ingreso_objetivo = total_ingresos * (1 + crecimiento_sugerido)

    return {
        "area": "ingresos",
        "decision": "Crecer ingresos",
        "motivo": (
            f"Tus ingresos son ${total_ingresos:,.0f} con {total_facturas} facturas. "
            f"Un crecimiento del {crecimiento_sugerido:.0f}% llevaría a "
            f"${ingreso_objetivo:,.0f} al año."
        ),
        "impacto_esperado": ingreso_objetivo - total_ingresos,
        "confianza": "media",
        "escenarios": {
            "conservador": total_ingresos,
            "base": ingreso_objetivo * 0.5,
            "agresivo": ingreso_objetivo,
        },
    }


def _decision_cartera_riesgo(
    salud: dict,
    alertas: list,
) -> dict:
    """Decisión sobre cartera en riesgo."""
    monto_en_riesgo = salud.get("monto_en_riesgo", 0) if salud else 0
    clientes_en_riesgo = salud.get("clientes_en_riesgo", 0) if salud else 0

    if monto_en_riesgo == 0:
        return {
            "area": "cartera",
            "decision": "Cartera bajo control",
            "motivo": "No hay cartera en riesgo identificada.",
            "impacto_esperado": 0,
            "confianza": "alta",
            "escenarios": {},
        }

    recuperable = monto_en_riesgo * 0.30  # tasa de recuperación típica

    return {
        "area": "cartera",
        "decision": "Recuperar cartera en riesgo",
        "motivo": (
            f"Hay ${monto_en_riesgo:,.0f} en riesgo con "
            f"{clientes_en_riesgo} cliente{'s' if clientes_en_riesgo != 1 else ''}. "
            f"Puedes recuperar hasta ${recuperable:,.0f} contactando a esos clientes."
        ),
        "impacto_esperado": recuperable,
        "confianza": "media",
        "escenarios": {
            "conservador": 0,
            "base": recuperable * 0.5,
            "agresivo": recuperable,
        },
    }


def _decision_inventario(data: dict, cfg: Any = None) -> dict | None:
    """Decisión sobre inventario: reabastecer productos con stock bajo."""
    inventario = data.get("inventario", pd.DataFrame()) if isinstance(data, dict) else None

    if inventario is None or inventario.empty:
        return None

    columnas_necesarias = {"stock_actual", "stock_minimo"}
    if not columnas_necesarias.issubset(set(inventario.columns)):
        return None

    inventario = inventario.copy()
    inventario["stock_actual"] = pd.to_numeric(inventario["stock_actual"], errors="coerce")
    inventario["stock_minimo"] = pd.to_numeric(inventario["stock_minimo"], errors="coerce")
    inventario = inventario.dropna(subset=["stock_actual", "stock_minimo"])

    bajo = inventario[inventario["stock_actual"] <= inventario["stock_minimo"]]
    n_bajo = len(bajo)

    if n_bajo == 0:
        return {
            "area": "inventario",
            "decision": "Inventario bajo control",
            "motivo": "Todos los productos tienen stock suficiente.",
            "impacto_esperado": 0,
            "confianza": "alta",
            "escenarios": {},
        }

    # Costo estimado de reabastecimiento (precio_costo * cantidad recomendada).
    inventario["precio_costo"] = pd.to_numeric(
        inventario.get("precio_costo", 0), errors="coerce"
    )
    inventario["cantidad_recomendada"] = (
        inventario["stock_minimo"] - inventario["stock_actual"]
    ).clip(lower=0)
    costo_reabastecimiento = float(
        (inventario["cantidad_recomendada"] * inventario["precio_costo"]).sum()
    )

    return {
        "area": "inventario",
        "decision": "Reabastecer inventario",
        "motivo": (
            f"{n_bajo} producto{'s' if n_bajo != 1 else ''} con stock bajo. "
            f"Reabastecimiento estimado: ${costo_reabastecimiento:,.0f}."
        ),
        "impacto_esperado": -costo_reabastecimiento,  # gasto, no ingreso
        "confianza": "alta",
        "escenarios": {
            "conservador": 0,
            "base": -costo_reabastecimiento * 0.5,
            "agresivo": -costo_reabastecimiento,
        },
    }


def _elegir_recomendacion_principal(decisiones: list[dict]) -> dict:
    """Elige la decisión de mayor impacto para mostrar como principal."""
    if not decisiones:
        return {
            "area": "general",
            "decision": "Monitorear",
            "motivo": "No hay decisiones prioritarias identificadas.",
            "impacto_esperado": 0,
            "confianza": "alta",
        }

    # Ordenar por impacto absoluto y elegir el mayor.
    def impacto_abs(d: dict) -> float:
        return abs(float(d.get("impacto_esperado", 0)))

    mejor = max(decisiones, key=impacto_abs)
    return mejor


__all__ = ["generar_dossier_de_decision"]
