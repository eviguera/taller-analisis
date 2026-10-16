"""Caso de uso de publicacion a warehouse SQL central (multi-DB).

Publicar el almacen hacia un warehouse externo (Postgres/Neon, MySQL,
Azure SQL, ...) era un bucle que la UI y el CLI disparaban llamando
directo a ``src.core.warehouse``: la orquestacion vivia en el nucleo y
cada adaptador la repetia a su manera (mismo DSN, mismo prefijo, misma
salida).

Aqui **no** hay ``import streamlit`` ni ``import sqlalchemy``: el DSN
llega como parametro (lo escribe el operador en la UI o en la CLI) y el
caso de uso delega en el nucleo, que es el unico que sabe de
SQLAlchemy. El enmascaramiento del DSN en los mensajes de error sigue
siendo cosa del llamador, que es el unico que sabe donde se lo enseña.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

import pandas as pd

if TYPE_CHECKING:
    from ..core.config import AppConfig

#: Esquemas del almacen que se publican, en el orden en que se publican.
ESQUEMAS_WAREHOUSE = ("datasets", "core", "analitica")


def publicar_warehouse(cfg: "AppConfig", dsn: str,
                       esquemas: tuple[str, ...] = ESQUEMAS_WAREHOUSE,
                       prefijo: str = "giro_") -> List[Dict]:
    """Publica el almacen del workspace hacia un warehouse SQL.

    Si el almacen esta vacio, el nucleo ejecuta el ETL antes de publicar
    (ver ``core.warehouse.sincronizar``): el warehouse refleja el mismo
    estado que ve la analitica.

    El DSN es del operador, no del tenant: viaja como parametro y nunca
    se devuelve sin enmascarar. El prefijo efectivo incluye la clave del
    workspace (``giro_<clave>_``), asi que dos workspaces que publican al
    mismo warehouse no se pisan (regla 1).
    """
    from ..core.warehouse import sincronizar  # noqa: PLC0415 — nucleo, sin adaptadores

    return sincronizar(cfg, dsn, esquemas=tuple(esquemas), prefijo=prefijo)


def ver_warehouse(cfg: "AppConfig", dsn: str,
                  prefijo: str = "giro_") -> pd.DataFrame:
    """Lista los objetos GIRO ya publicados en el warehouse destino.

    El filtro por prefijo incluye la clave del workspace: cada tenant
    solo ve lo suyo, aunque el warehouse sea compartido.
    """
    from ..core.warehouse import ver  # noqa: PLC0415 — nucleo, sin adaptadores

    return ver(cfg, dsn, prefijo=prefijo)


__all__ = ["ESQUEMAS_WAREHOUSE", "publicar_warehouse", "ver_warehouse"]
