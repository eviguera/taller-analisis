"""Wrappers BaseAgent sobre los agentes existentes de GIRO.

Cada clase hereda de `src.core.agente.BaseAgent` y delega en la función pura
que ya existía (analizar_datos_negocio, generar_dossier_de_decision, etc.).
Así se añade la arquitectura de registro/agentes sin romper la API actual.

No importa streamlit, duckdb ni fastapi.
"""

from __future__ import annotations

from typing import Any

from src.core.agente import BaseAgent, ResultadoAgente, registrar_agente

from .analyst import analizar_datos_negocio
from .strategy import generar_dossier_de_decision
from .governance import validar_recomendaciones
from .report import generar_reporte_ejecutivo


@registrar_agente
class AnalystAgent(BaseAgent):
    name = "analyst"
    domain = "clientes"
    visibility = "core"
    version = "1.0.0"

    def ejecutar(self, data: dict[str, Any], cfg: Any) -> ResultadoAgente:
        res = analizar_datos_negocio(data, cfg)
        return ResultadoAgente(
            agente=self.name,
            dominio=self.domain,
            datos=res if isinstance(res, dict) else {"resultado": res},
            resumen=res.get("hecho_clave", "") if isinstance(res, dict) else "",
            metricas=res.get("kpis", {}) if isinstance(res, dict) else {},
            alertas=res.get("alertas", []) if isinstance(res, dict) else [],
        )


@registrar_agente
class StrategyAgent(BaseAgent):
    name = "strategy"
    domain = "finanzas"
    visibility = "core"
    version = "1.0.0"

    def ejecutar(self, data: dict[str, Any], cfg: Any) -> ResultadoAgente:
        res = generar_dossier_de_decision(data, cfg)
        return ResultadoAgente(
            agente=self.name,
            dominio=self.domain,
            datos=res if isinstance(res, dict) else {"resultado": res},
            resumen=res.get("resumen_ejecutivo", "") if isinstance(res, dict) else "",
            recomendaciones=res.get("recomendaciones", []) if isinstance(res, dict) else [],
        )


@registrar_agente
class GovernanceAgent(BaseAgent):
    name = "governance"
    domain = "calidad"
    visibility = "internal"
    version = "1.0.0"

    def ejecutar(self, data: dict[str, Any], cfg: Any) -> ResultadoAgente:
        res = validar_recomendaciones(data, cfg)
        return ResultadoAgente(
            agente=self.name,
            dominio=self.domain,
            datos=res if isinstance(res, dict) else {"resultado": res},
            resumen=res.get("resumen", "") if isinstance(res, dict) else "",
        )


@registrar_agente
class ReportAgent(BaseAgent):
    name = "report"
    domain = "reportes"
    visibility = "core"
    version = "1.0.0"

    def ejecutar(self, data: dict[str, Any], cfg: Any) -> ResultadoAgente:
        res = generar_reporte_ejecutivo(data, cfg)
        return ResultadoAgente(
            agente=self.name,
            dominio=self.domain,
            datos=res if isinstance(res, dict) else {"resultado": res},
            resumen=res.get("resumen", "") if isinstance(res, dict) else "",
        )
