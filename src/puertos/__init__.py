"""Puertos (interfaces) del nucleo hexagonal.

Un **puerto** es el contrato que el nucleo de aplicacion exige al exterior.
El nucleo define *que* necesita (leer tablas, persistir modelos, cargar un
archivo); los **adaptadores** (`src/adaptadores/`, `src/storage/`,
`src/loaders/`, `ui/`, la API) deciden *como*.

Regla de direccion: `puertos` no importa a ningun adaptador. Si aqui aparece
un `import duckdb`, `import streamlit` o un `from ..storage`, la arquitectura
esta rota.

En este repo el tipo de intercambio compartido es `pandas.DataFrame`: el
nucleo es framework-free, pero no se ha abstraido el modelo de datos. Es
hexagonal practico, no hexagonal de manual.

Puertos:
  * `PuertoAlmacen`        -> persistencia analitica (DuckDB, Postgres, ...)
  * `PuertoRegistroModelos` -> modelos entrenados entre sesiones
  * `PuertoCarga`          -> lectura de archivos fuente (CSV, Excel, PSPP)
  * `PuertoIdentidad`      -> identidad federada (SSO/OIDC) de la peticion
  * `PuertoAgenteIA`        -> asesor de negocio con IA (grounded)
"""

from .almacen import PuertoAlmacen
from .carga import CargaResultado, PuertoCarga
from .identidad import PuertoIdentidad
from .modelos import PuertoRegistroModelos
from .agente_ia import (
    AccionPrioritaria,
    Hallazgo,
    PuertoAgenteIA,
    RespuestaAsesor,
    Riesgo,
)

__all__ = [
    "PuertoAlmacen",
    "PuertoRegistroModelos",
    "PuertoCarga",
    "PuertoIdentidad",
    "CargaResultado",
    "PuertoAgenteIA",
    "RespuestaAsesor",
    "Hallazgo",
    "AccionPrioritaria",
    "Riesgo",
]
