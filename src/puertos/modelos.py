"""Puerto de persistencia de modelos entrenados.

Separado del almacen analitico a proposito: los modelos se serializan con
joblib, un formato binario con deserializacion arbitraria. Mantenerlo como
puerto propio deja aislado el riesgo (`src/model_registry.py` valida origen,
version de sklearn y confinamiento de rutas) en un unico adaptador.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class PuertoRegistroModelos(ABC):
    """Guardado/carga de modelos por tipo (churn, ingresos, demanda, ...)."""

    @abstractmethod
    def guardar(self, tipo: str, modelo: Any, metadatos: Optional[dict] = None) -> dict:
        """Serializa el modelo y sus metadatos. Devuelve los metadatos persistidos."""

    @abstractmethod
    def cargar(self, tipo: str) -> tuple[Any, Optional[dict]]:
        """Devuelve `(modelo, metadatos)` o `(None, None)` si no existe."""

    @abstractmethod
    def borrar(self, tipo: str) -> None:
        """Elimina un modelo guardado (para forzar reentrenamiento)."""

    @abstractmethod
    def listar(self) -> list[dict]:
        """Catalogo de modelos persistidos con sus metadatos."""

    @abstractmethod
    def es_fresco(self, tipo: str, n_minimo: int = 0) -> bool:
        """True si el modelo existe y fue entrenado con al menos `n_minimo` muestras."""


__all__ = ["PuertoRegistroModelos"]
