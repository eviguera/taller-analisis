"""Puerto para el agente de asesoría de negocio con IA.

Define la interfaz que deben implementar los adaptadores LLM
(OpenRouter, Ollama, etc.). Mantiene el hexágono aislado de proveedores.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol


@dataclass
class AccionPrioritaria:
    """Acción priorizada sugerida por el agente."""

    titulo: str
    descripcion: str
    prioridad: str  # alta | media | baja
    esfuerzo: str  # bajo | medio | alto
    impacto: str  # alto | medio | bajo
    plazo: str  # inmediato | 30_dias | 60_dias | 90_dias
    categoria: str = "general"  # ventas | clientes | inventario | facturacion | finanzas | general


@dataclass
class Hallazgo:
    """Hallazgo clave derivado de los datos."""

    titulo: str
    descripcion: str
    severidad: str  # critica | alta | media | baja | ok
    evidencia: List[str] = field(default_factory=list)


@dataclass
class Riesgo:
    """Riesgo identificado."""

    titulo: str
    descripcion: str
    probabilidad: str  # alta | media | baja
    impacto: str  # alto | medio | bajo
    mitigacion: str = ""


@dataclass
class RespuestaAsesor:
    """Respuesta estructurada y validable del agente IA."""

    resumen_ejecutivo: str
    hallazgos: List[Hallazgo] = field(default_factory=list)
    acciones: List[AccionPrioritaria] = field(default_factory=list)
    riesgos: List[Riesgo] = field(default_factory=list)
    preguntas_para_aclarar: List[str] = field(default_factory=list)
    fuentes_usadas: List[str] = field(default_factory=list)
    datos_usados: Dict[str, Any] = field(default_factory=dict)
    modelo: str = ""
    proveedor: str = ""


class PuertoAgenteIA(Protocol):
    """Interfaz para adaptadores de LLM."""

    def disponible(self) -> bool:
        """Indica si el adaptador tiene credenciales para operar."""
        ...

    def generar_respuesta(
        self,
        contexto_datos: Dict[str, Any],
        instrucciones: str,
        respuesta_json_esperada: bool = True,
    ) -> RespuestaAsesor:
        """Genera una respuesta estructurada basada en contexto grounded."""
        ...
