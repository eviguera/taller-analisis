"""Puerto de persistencia analitica.

Es el contrato que permite sustituir el motor de almacenamiento (Hoy DuckDB
embebido; con Postgres detras, el mismo nucleo) sin tocar la logica de
negocio ni la UI.

Los metodos declarados aqui son los que el resto del sistema llama de
fuera de `DataStore`. El resto (`ejecutar`, `columnas`, `listar_tablas`,
`existe_tabla`, `query_one`, `leer_cache`) son **internos del adaptador**:
se usan dentro de la propia implementacion y no forman parte del contrato.
Declararlos aqui obligaria a cada adaptador a reimplementar detalle que no
le concierne (p. ej. la cache en parquet es exclusiva de DuckDB).

El SQL que pasa por `consulta()` es del dialecto del adaptador que lo
implemente: validar que es de solo lectura es responsabilidad del llamador
(`src/core/conector_sql.validar_solo_lectura`), no del puerto.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

import pandas as pd


class PuertoAlmacen(ABC):
    """Contrato del almacen analitico (tablas `main`, esquema `core`, vistas `analitica`)."""

    # ---------- registro ----------
    @abstractmethod
    def registrar_tabla(self, nombre: str, df: pd.DataFrame,
                        sobreescribir: bool = True, cache: bool = True) -> str:
        """Carga un dataframe como tabla. Devuelve el nombre normalizado."""

    @abstractmethod
    def registrar_tablas(self, tablas: Dict[str, pd.DataFrame]) -> None:
        """Carga varios datasets de una vez."""

    @abstractmethod
    def registrar_tabla_core(self, nombre: str, df: pd.DataFrame,
                             con_claves: bool = True) -> str:
        """Materializa una tabla derivada en el esquema `core`, con claves."""

    # ---------- firma de la ultima carga ----------
    @abstractmethod
    def firma_carga(self, clave: str = "datos") -> str:
        """Firma guardada de la ultima carga, o '' si no la hay."""

    @abstractmethod
    def guardar_firma(self, firma: str, clave: str = "datos") -> None:
        """Persiste la firma de la ultima carga."""

    # ---------- esquema y consulta ----------
    @abstractmethod
    def construir_estructura(self, tablas: Dict[str, pd.DataFrame]) -> Dict[str, int]:
        """Materializa `core.*` y crea las vistas `analitica.*`. Devuelve `{tabla: filas}`."""

    @abstractmethod
    def consulta(self, sql: str) -> pd.DataFrame:
        """Ejecuta una consulta y devuelve un dataframe."""

    @abstractmethod
    def consultar_vista(self, nombre: str) -> pd.DataFrame:
        """Consulta una vista del esquema `analitica`."""

    @abstractmethod
    def consultar_objeto(self, esquema: str, nombre: str) -> pd.DataFrame:
        """Lee `<esquema>.<nombre>` con lista explicita de columnas."""

    @abstractmethod
    def info_estructura(self) -> pd.DataFrame:
        """Catalogo del almacen: esquema, objeto y tipo (tabla/vista)."""

    @abstractmethod
    def tabla(self, nombre: str) -> pd.DataFrame:
        """Lee una tabla por su nombre."""

    # ---------- ciclo de vida ----------
    @abstractmethod
    def cerrar(self) -> None:
        """Libera la conexion. Idempotente."""

    def __enter__(self) -> "PuertoAlmacen":
        return self

    def __exit__(self, *exc) -> None:
        self.cerrar()


__all__ = ["PuertoAlmacen"]
