"""BaseAgent: clase base para agentes de decisión de GIRO.

Inspirada en OpenExecutive (agents/base.py) pero adaptada a GIRO: los agentes
de GIRO operan sobre datos ya cargados del almacén (dict de DataFrames + AppConfig),
no sobre conversación de chat. Proporciona:

  * Registro de agentes por nombre (`REGISTRO`).
  * Interfaz común: `ejecutar(data, cfg) -> dict`.
  * Metadatos: nombre, dominio, visibilidad (core/internal), versión.
  * Sobrescritura de prompt/config desde config.yaml (opcional, para cuando
    un agente delegue en un LLM en el futuro).

Ningún agente importa streamlit, duckdb ni fastapi. Cero efectos secundarios
en import: solo se definen clases y el registro.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

AgentVisibility = str  # "core" | "internal"

_REGISTRO: dict[str, type["BaseAgent"]] = {}


def registrar_agente(clase: type["BaseAgent"]) -> type["BaseAgent"]:
    """Registra una subclase de BaseAgent por su atributo `name`."""
    nombre = getattr(clase, "name", None)
    if not nombre:
        raise ValueError(f"La clase {clase.__name__} no define `name`.")
    _REGISTRO[nombre] = clase
    return clase


def listar_agentes() -> list[str]:
    return sorted(_REGISTRO)


def obtener_agente(nombre: str) -> type["BaseAgent"]:
    if nombre not in _REGISTRO:
        raise KeyError(
            f"Agente {nombre!r} no registrado. Disponibles: {listar_agentes()}"
        )
    return _REGISTRO[nombre]


@dataclass
class ResultadoAgente:
    """Resultado estandarizado de un agente."""
    agente: str
    dominio: str
    datos: dict[str, Any] = field(default_factory=dict)
    resumen: str = ""
    metricas: dict[str, Any] = field(default_factory=dict)
    alertas: list[dict] = field(default_factory=list)
    recomendaciones: list[dict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """Base para agentes de decisión de GIRO.

    Atributos de clase:
        name: nombre corto, único, usado como clave en el registro.
        domain: dominio de negocio (p. ej. "clientes", "inventario", "finanzas").
        visibility: "core" (visible al usuario) o "internal" (uso interno).
        version: versión del agente (para trazabilidad de decisiones).
    """

    name: str = ""
    domain: str = ""
    visibility: AgentVisibility = "internal"
    version: str = "1.0.0"

    @abstractmethod
    def ejecutar(self, data: dict[str, Any], cfg: Any) -> ResultadoAgente:
        """Ejecuta el agente sobre los datos del workspace y devuelve un resultado."""

    def descripcion(self) -> str:
        """Descripción legible del agente para la UI."""
        return f"{self.name} ({self.domain}) v{self.version}"

    def configuracion(self, cfg: Any) -> dict:
        """Lee la configuración específica del agente desde cfg, si existe.

        Por defecto devuelve {}; las subclases pueden sobrescribir para leer
        claves de config/config.yaml (p. ej. cfg.alertas, cfg.mantenimiento).
        """
        return {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, domain={self.domain!r})"


__all__ = [
    "BaseAgent",
    "ResultadoAgente",
    "registrar_agente",
    "listar_agentes",
    "obtener_agente",
    "AgentVisibility",
]
