"""Modelo dimensional del almacen DuckDB.

Esquemas que estructura el almacen:
  * ``core``      -> tablas normalizadas con claves primarias y foraneas.
  * ``analitica`` -> vistas desnormalizadas que los paneles consumen
                     directamente (hechos + dimensiones, RFM, demanda, ...).

El pipeline registra los datasets cargados en ``main.*`` (compatibilidad y
consultas SQL directas) y, ademas, materializa ``core.*`` con claves y crea
las vistas ``analitica.*`` en ``construir_estructura``.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd

# ------------------------------------------------------------------
#  Orden de carga respetando dependencias (cliente -> vehiculo -> factura)
# ------------------------------------------------------------------
ORDEN_CARGA: List[str] = ["clientes", "servicios", "vehiculos", "facturas", "inventario"]

# ------------------------------------------------------------------
#  Especificacion de cada tabla del esquema `core`
# ------------------------------------------------------------------
ESPECIFICACIONES: Dict[str, Dict] = {
    "clientes": {
        "pk": ["id"],
        "fks": [],
    },
    "servicios": {
        "pk": ["id"],
        "fks": [],
    },
    "vehiculos": {
        "pk": ["id"],
        "fks": [("cliente_id", "core.clientes(id)")],
    },
    "facturas": {
        "pk": ["id"],
        "fks": [
            ("cliente_id", "core.clientes(id)"),
            ("vehiculo_id", "core.vehiculos(id)"),
        ],
    },
    "inventario": {
        "pk": ["id"],
        "fks": [],
    },
}

# ------------------------------------------------------------------
#  Tipos: pandas -> DuckDB
# ------------------------------------------------------------------

def sql_tipo(dtype: str) -> str:
    """Convierte un dtype de pandas a un tipo SQL de DuckDB."""
    if pd.api.types.is_integer_dtype(dtype):
        return "BIGINT"
    if pd.api.types.is_float_dtype(dtype):
        return "DOUBLE"
    if pd.api.types.is_bool_dtype(dtype):
        return "BOOLEAN"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "TIMESTAMP"
    return "VARCHAR"


def ddl_tabla_core(nombre: str, df: pd.DataFrame, con_claves: bool = True) -> str:
    """Genera el DDL de ``core.<nombre>`` a partir de las columnas de ``df``.

    Las columnas conocidas se tipan; el resto se guarda como VARCHAR para no
    perder datos. Las claves (PK/FK) se incluyen solo si ``con_claves``.
    """
    spec = ESPECIFICACIONES.get(nombre, {"pk": [], "fks": []})
    columnas = []
    for col in df.columns:
        columnas.append(f'"{col}" {sql_tipo(df[col].dtype)}')
    if con_claves:
        for pk in spec.get("pk", []):
            if pk in df.columns:
                columnas.append(f'PRIMARY KEY ("{pk}")')
        for col, ref in spec.get("fks", []):
            if col in df.columns:
                columnas.append(f'FOREIGN KEY ("{col}") REFERENCES {ref}')
    return f'CREATE TABLE IF NOT EXISTS core."{nombre}" (\n  ' + ",\n  ".join(columnas) + "\n);"


# ------------------------------------------------------------------
#  Vistas analiticas sobre el esquema `core`
# ------------------------------------------------------------------
VISTAS_ANALITICA: Dict[str, str] = {
    # ------- Hechos + dimensiones ---------------------------------
    "facturas_con_dimensiones": """
    CREATE OR REPLACE VIEW analitica.facturas_con_dimensiones AS
    SELECT f."id"          AS factura_id,
           f."fecha",
           f."total",
           f."descuento",
           f."estado",
           f."cliente_id",
           c."nombre"      AS cliente,
           c."email"       AS email_cliente,
           f."vehiculo_id",
           v."marca",
           v."modelo",
           v."anio",
           v."placa",
           v."color",
           v."kilometraje"
    FROM core.facturas f
    LEFT JOIN core.clientes c ON c."id" = f."cliente_id"
    LEFT JOIN core.vehiculos v ON v."id" = f."vehiculo_id";
    """,

    # ------- Series de ingresos -----------------------------------
    "ingresos_mensuales": """
    CREATE OR REPLACE VIEW analitica.ingresos_mensuales AS
    SELECT strftime(f."fecha", '%Y-%m') AS anio_mes,
           round(SUM(f."total"), 2)     AS ingresos,
           COUNT(*)                     AS facturas,
           round(AVG(f."total"), 2)     AS ticket_promedio
    FROM core.facturas f
    WHERE f."estado" <> 'Cancelada'
    GROUP BY 1;
    """,

    "ingresos_por_marca": """
    CREATE OR REPLACE VIEW analitica.ingresos_por_marca AS
    SELECT v."marca",
           round(SUM(f."total"), 2) AS ingresos,
           COUNT(*)                 AS facturas,
           round(AVG(f."total"), 2) AS promedio
    FROM core.facturas f
    LEFT JOIN core.vehiculos v ON v."id" = f."vehiculo_id"
    WHERE f."estado" <> 'Cancelada'
    GROUP BY 1;
    """,

    # ------- Ingresos por vehiculo --------------------------------
    "ingresos_por_vehiculo": """
    CREATE OR REPLACE VIEW analitica.ingresos_por_vehiculo AS
    SELECT v."id"                              AS vehiculo_id,
           v."marca",
           v."modelo",
           v."placa",
           v."anio",
           v."color",
           v."kilometraje",
           COUNT(f."id")                       AS facturas,
           round(SUM(f."total"), 2)            AS ingresos,
           MAX(f."fecha")                      AS ultima_visita
    FROM core.facturas f
    LEFT JOIN core.vehiculos v ON v."id" = f."vehiculo_id"
    WHERE f."estado" <> 'Cancelada'
    GROUP BY 1, 2, 3, 4, 5, 6, 7;
    """,

    # ------- Detalle de servicios --------------------------------
    "detalle_servicios": """
    CREATE OR REPLACE VIEW analitica.detalle_servicios AS
    SELECT f."id"                                    AS factura_id,
           f."fecha",
           f."cliente_id",
           c."nombre"                                AS cliente,
           TRY_CAST(split_part(t.det, ':', 1) AS BIGINT) AS servicio_id,
           COALESCE(s."nombre", TRIM(COALESCE(split_part(t.det, ':', 1), '')))
                                                       AS servicio,
           TRY_CAST(split_part(t.det, ':', 2) AS BIGINT) AS cantidad,
           TRY_CAST(split_part(t.det, ':', 3) AS DOUBLE) AS subtotal
    FROM core.facturas f
    LEFT JOIN core.clientes c ON c."id" = f."cliente_id"
    LEFT JOIN UNNEST(STRING_SPLIT(COALESCE(f."detalles", ''), ';')) AS t(det)
        ON TRIM(t.det) <> ''
    LEFT JOIN core.servicios s
        ON TRY_CAST(split_part(t.det, ':', 1) AS BIGINT) = s."id";
    """,

    "demanda_servicios_mensual": """
    CREATE OR REPLACE VIEW analitica.demanda_servicios_mensual AS
    SELECT d."servicio",
           strftime(d."fecha", '%Y-%m') AS anio_mes,
           SUM(COALESCE(d."cantidad", 1)) AS demanda
    FROM analitica.detalle_servicios d
    WHERE d."servicio_id" IS NOT NULL
    GROUP BY 1, 2;
    """,

    # ------- RFM / churn -----------------------------------------
    "rfm_clientes": """
    CREATE OR REPLACE VIEW analitica.rfm_clientes AS
    SELECT f."cliente_id",
           c."nombre",
           CAST(date_diff('day',
                         MAX(f."fecha"),
                         (SELECT MAX("fecha") FROM core.facturas WHERE "estado" <> 'Cancelada')
           ) AS BIGINT)             AS recencia_dias,
           COUNT(*)                 AS frecuencia,
           round(SUM(f."total"), 2) AS monto
    FROM core.facturas f
    LEFT JOIN core.clientes c ON c."id" = f."cliente_id"
    WHERE f."estado" <> 'Cancelada'
    GROUP BY 1, 2;
    """,

    "churn_clientes": """
    CREATE OR REPLACE VIEW analitica.churn_clientes AS
    SELECT r.*,
           (r."recencia_dias" > 90) AS en_riesgo
    FROM analitica.rfm_clientes r;
    """,

    # ------- Inventario ------------------------------------------
    "inventario_estado": """
    CREATE OR REPLACE VIEW analitica.inventario_estado AS
    SELECT p."id",
           p."producto",
           p."categoria",
           p."precio_costo",
           p."precio_venta",
           p."stock_actual",
           p."stock_minimo",
           round(p."stock_actual" * p."precio_costo", 2)                               AS valor_inventario,
           round(p."precio_venta" - p."precio_costo", 2)                               AS margen,
           round((p."precio_venta" - p."precio_costo") / NULLIF(p."precio_costo", 0) * 100, 1) AS margen_pct,
           CASE
               WHEN p."stock_actual" <= p."stock_minimo"                     THEN 'Bajo'
               WHEN p."stock_actual" <= p."stock_minimo" * 1.5               THEN 'Medio'
               ELSE 'Optimo'
           END AS estado_stock
    FROM core.inventario p;
    """,
}

# ------------------------------------------------------------------
#  DDL de arranque: presencia de esquemas
# ------------------------------------------------------------------
SQL_ARRANQUE = [
    'CREATE SCHEMA IF NOT EXISTS core;',
    'CREATE SCHEMA IF NOT EXISTS analitica;',
]