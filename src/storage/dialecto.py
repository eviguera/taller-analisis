"""Dialectos SQL del almacen analitico: DuckDB y PostgreSQL.

`schema.py` declara el modelo dimensional (DDL de ``core.*`` y las 11 vistas
``analitica.*``) en dialecto DuckDB. Este modulo aporta la capa que permite
que otro motor ejecute el mismo esquema sin tocar ``schema.py``:

  * `DialectoDuckDB`   -> devuelve literalmente el SQL actual: ``sql_tipo``
                          delega en ``schema.sql_tipo`` y ``vistas()``
                          devuelve ``VISTAS_ANALITICA``, de modo que el
                          comportamiento de DuckDB no puede divergir sin que
                          cambie ``schema.py`` (lo comprueba
                          ``tests/test_postgres.py``).
  * `DialectoPostgres` -> SQL reescrito para PostgreSQL 16 y verificado
                          contra el motor real:

        - ``strftime(x, '%Y-%m')``        -> ``to_char(x, 'YYYY-MM')``
        - ``TRY_CAST(x AS BIGINT/DOUBLE)`` -> funciones ``giro_try_*`` que
          degradan a NULL como TRY_CAST (unico fin de su excepcion)
        - ``LEFT JOIN UNNEST(STRING_SPLIT(...))`` -> ``LEFT JOIN LATERAL
          unnest(string_to_array(...))``
        - ``date_diff('day', a, b)``      -> diferencia de fechas (Postgres
          16 no trae ``date_diff``; comprobado en el motor)
        - ``round(x, n)``                 -> ``giro_redondea`` (Postgres no
          admite ``round(double precision, integer)``)
        - division entera de enteros      -> ``::double precision`` (en
          Postgres ``entero / entero`` trunca; DuckDB divide siempre)

Contrato (`Dialecto`): ``sql_tipo``, ``sql_arranque``, ``vistas``, los
helpers ``try_cast``/``fecha_a_mes``/``redondea`` (cada expresion no
portable vive en un helper, no repartida por las vistas) y ``ddl_tabla``
para componer el DDL de una tabla.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List

import pandas as pd

from .schema import (
    ESPECIFICACIONES,
    SQL_ARRANQUE,
    VISTAS_ANALITICA,
    _ident,
    sql_tipo as _sql_tipo_duckdb,
)


class Dialecto(ABC):
    """Contrato de un dialecto SQL del almacen."""

    #: Nombre corto del motor ("duckdb", "postgresql").
    nombre: str = ""

    # ---------- tipos y DDL ----------

    @abstractmethod
    def sql_tipo(self, dtype) -> str:
        """Convierte un dtype de pandas a un tipo SQL de este motor."""

    @abstractmethod
    def sql_arranque(self) -> List[str]:
        """Sentencias DDL que deben ejecutarse antes de usar el almacen."""

    @abstractmethod
    def vistas(self) -> Dict[str, str]:
        """``{nombre: DDL}`` de las vistas ``analitica.*`` de este motor."""

    # ---------- fragmentos no portables ----------

    @abstractmethod
    def try_cast(self, expresion: str, tipo: str) -> str:
        """Conversion tolerante (degrada a NULL, nunca lanza)."""

    @abstractmethod
    def fecha_a_mes(self, expresion: str) -> str:
        """La fecha/expresion como ``AAAA-MM``."""

    @abstractmethod
    def redondea(self, expresion: str, decimales: int) -> str:
        """Redondeo a ``decimales`` digitos."""

    # ---------- DDL de tablas ----------

    def ddl_tabla(self, esquema: str, nombre: str, df: pd.DataFrame,
                  con_claves: bool = True) -> str:
        """Genera el DDL de ``esquema.<nombre>`` a partir de las columnas de ``df``.

        Estructura identica a ``schema.ddl_tabla_core`` (columnas conocidas
        tipadas, el resto VARCHAR, claves solo si ``con_claves``); la unica
        variacion es el tipo decimal, que decide cada dialecto.
        """
        spec = ESPECIFICACIONES.get(nombre, {"pk": [], "fks": []})
        columnas = []
        for col in df.columns:
            columnas.append(f'{_ident(col)} {self.sql_tipo(df[col].dtype)}')
        if con_claves:
            for pk in spec.get("pk", []):
                if pk in df.columns:
                    columnas.append(f'PRIMARY KEY ({_ident(pk)})')
            for col, ref in spec.get("fks", []):
                if col in df.columns:
                    columnas.append(f'FOREIGN KEY ({_ident(col)}) REFERENCES {ref}')
        return (f'CREATE TABLE IF NOT EXISTS {esquema}.{_ident(nombre)} (\n  '
                + ",\n  ".join(columnas) + "\n);")

    def ddl_tabla_core(self, nombre: str, df: pd.DataFrame,
                       con_claves: bool = True) -> str:
        """DDL de ``core.<nombre>``."""
        return self.ddl_tabla("core", nombre, df, con_claves=con_claves)


class DialectoDuckDB(Dialecto):
    """Dialecto DuckDB: el SQL actual de ``schema.py``, literal."""

    nombre = "duckdb"

    def sql_tipo(self, dtype) -> str:
        # Delegacion literal: cero copia de la logica de tipos, cero deriva.
        return _sql_tipo_duckdb(dtype)

    def sql_arranque(self) -> List[str]:
        return list(SQL_ARRANQUE)

    def vistas(self) -> Dict[str, str]:
        return dict(VISTAS_ANALITICA)

    def try_cast(self, expresion: str, tipo: str) -> str:
        return f"TRY_CAST({expresion} AS {tipo})"

    def fecha_a_mes(self, expresion: str) -> str:
        return f"strftime({expresion}, '%Y-%m')"

    def redondea(self, expresion: str, decimales: int) -> str:
        return f"round({expresion}, {decimales})"


class DialectoPostgres(Dialecto):
    """Dialecto PostgreSQL 16.

    Las vistas se componen con los helpers de la clase base: cada
    diferencia de dialecto (mes, cast tolerante, redondeo) pasa por una
    funcion, no esta suelta por el SQL. Las diferencias que no tienen
    helper (LATERAL, division en punto flotante) van escritas en la vista,
    comentadas.
    """

    nombre = "postgresql"

    def sql_tipo(self, dtype) -> str:
        # La logica de mapeo vive en schema.sql_tipo; solo cambia el nombre
        # del tipo decimal (Postgres no acepta `DOUBLE` a secas).
        tipo = _sql_tipo_duckdb(dtype)
        return "DOUBLE PRECISION" if tipo == "DOUBLE" else tipo

    def sql_arranque(self) -> List[str]:
        funciones = [
            # TRY_CAST no existe en Postgres. Dos funciones tolerantes que
            # degradan a NULL en los mismos casos: entrada ilegible o
            # fuera de rango. Cualquier otro error SQL sube y se ve
            # (regla 8: la excepcion es el contrato, no un `pass`).
            """
            CREATE OR REPLACE FUNCTION giro_meta.giro_try_entero(p_texto text)
            RETURNS bigint LANGUAGE plpgsql IMMUTABLE AS $cuerpo$
            BEGIN
                RETURN p_texto::bigint;
            EXCEPTION
                WHEN invalid_text_representation
                  OR numeric_value_out_of_range THEN
                    RETURN NULL;
            END;
            $cuerpo$;
            """,
            """
            CREATE OR REPLACE FUNCTION giro_meta.giro_try_decimalo(p_texto text)
            RETURNS double precision LANGUAGE plpgsql IMMUTABLE AS $cuerpo$
            BEGIN
                RETURN p_texto::double precision;
            EXCEPTION
                WHEN invalid_text_representation THEN
                    RETURN NULL;
            END;
            $cuerpo$;
            """,
            # Postgres no admite `round(double precision, integer)`: pasa
            # por numeric (el redondeo es el mismo que el de DuckDB) y
            # vuelve a double precision para que el tipo de la vista
            # coincida con el de DuckDB.
            """
            CREATE OR REPLACE FUNCTION giro_meta.giro_redondea(
                p_valor double precision, p_decimales integer)
            RETURNS double precision LANGUAGE sql IMMUTABLE AS $cuerpo$
                SELECT round(p_valor::numeric, p_decimales)::double precision;
            $cuerpo$;
            """,
        ]
        return [
            'CREATE SCHEMA IF NOT EXISTS core;',
            'CREATE SCHEMA IF NOT EXISTS analitica;',
            'CREATE SCHEMA IF NOT EXISTS giro_meta;',
            # DuckDB trabaja en su esquema por defecto `main`; Postgres no
            # tiene equivalente, asi que se crea para las tablas que se
            # registran "tal cual" (registrar_tabla).
            'CREATE SCHEMA IF NOT EXISTS main;',
        ] + funciones

    def try_cast(self, expresion: str, tipo: str) -> str:
        funciones = {
            "BIGINT": "giro_meta.giro_try_entero",
            "DOUBLE": "giro_meta.giro_try_decimalo",
            "DOUBLE PRECISION": "giro_meta.giro_try_decimalo",
        }
        clave = str(tipo).upper()
        if clave not in funciones:
            raise ValueError(
                f"try_cast sin traduccion para el tipo {tipo!r} en PostgreSQL")
        return f"{funciones[clave]}({expresion})"

    def fecha_a_mes(self, expresion: str) -> str:
        return f"to_char({expresion}, 'YYYY-MM')"

    def redondea(self, expresion: str, decimales: int) -> str:
        return f"giro_meta.giro_redondea({expresion}, {decimales})"

    def vistas(self) -> Dict[str, str]:
        """Las 11 vistas de ``schema.py`` traducidas a PostgreSQL 16.

        Cada vista se precede de ``DROP VIEW ... CASCADE``: Postgres no
        permite que ``CREATE OR REPLACE VIEW`` cambie las columnas de una
        vista existente, y DuckDB si. El DROP deja la sustitucion libre en
        ambos motores. El orden de este dict respeta las dependencias
        (``detalle_servicios`` antes que ``demanda_servicios_mensual``,
        ``rfm_clientes`` antes que ``churn_clientes``).
        """
        mes = self.fecha_a_mes
        entero = lambda e: self.try_cast(e, "BIGINT")  # noqa: E731 — alias local
        decimal = lambda e: self.try_cast(e, "DOUBLE")  # noqa: E731
        red = self.redondea

        return {
            # ------- Hechos + dimensiones ---------------------------------
            "facturas_con_dimensiones": """
            DROP VIEW IF EXISTS analitica.facturas_con_dimensiones CASCADE;
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
            "ingresos_mensuales": f"""
            DROP VIEW IF EXISTS analitica.ingresos_mensuales CASCADE;
            CREATE OR REPLACE VIEW analitica.ingresos_mensuales AS
            SELECT {mes('f."fecha"')}  AS anio_mes,
                   {red('SUM(f."total")', 2)}        AS ingresos,
                   COUNT(*)                         AS facturas,
                   {red('AVG(f."total")', 2)}        AS ticket_promedio
            FROM core.facturas f
            WHERE f."estado" <> 'Cancelada'
            GROUP BY 1;
            """,

            "ingresos_por_marca": f"""
            DROP VIEW IF EXISTS analitica.ingresos_por_marca CASCADE;
            CREATE OR REPLACE VIEW analitica.ingresos_por_marca AS
            SELECT v."marca",
                   {red('SUM(f."total")', 2)}        AS ingresos,
                   COUNT(*)                         AS facturas,
                   {red('AVG(f."total")', 2)}        AS promedio
            FROM core.facturas f
            LEFT JOIN core.vehiculos v ON v."id" = f."vehiculo_id"
            WHERE f."estado" <> 'Cancelada'
            GROUP BY 1;
            """,

            # ------- Ingresos por vehiculo --------------------------------
            "ingresos_por_vehiculo": f"""
            DROP VIEW IF EXISTS analitica.ingresos_por_vehiculo CASCADE;
            CREATE OR REPLACE VIEW analitica.ingresos_por_vehiculo AS
            SELECT v."id"                              AS vehiculo_id,
                   v."marca",
                   v."modelo",
                   v."placa",
                   v."anio",
                   v."color",
                   v."kilometraje",
                   COUNT(f."id")                       AS facturas,
                   {red('SUM(f."total")', 2)}          AS ingresos,
                   MAX(f."fecha")                      AS ultima_visita
            FROM core.facturas f
            LEFT JOIN core.vehiculos v ON v."id" = f."vehiculo_id"
            WHERE f."estado" <> 'Cancelada'
            GROUP BY 1, 2, 3, 4, 5, 6, 7;
            """,

            # ------- Detalle de servicios --------------------------------
            # El UNNEST de DuckDB necesita LATERAL en Postgres: la funcion
            # se evalua por fila de la facturas que la precede en el FROM.
            "detalle_servicios": f"""
            DROP VIEW IF EXISTS analitica.detalle_servicios CASCADE;
            CREATE OR REPLACE VIEW analitica.detalle_servicios AS
            SELECT f."id"                                    AS factura_id,
                   f."fecha",
                   f."cliente_id",
                   c."nombre"                                AS cliente,
                   {entero("split_part(t.det, ':', 1)")}     AS servicio_id,
                   COALESCE(s."nombre",
                            TRIM(COALESCE(split_part(t.det, ':', 1), '')))
                                                              AS servicio,
                   {entero("split_part(t.det, ':', 2)")}     AS cantidad,
                   {decimal("split_part(t.det, ':', 3)")}     AS subtotal
            FROM core.facturas f
            LEFT JOIN core.clientes c ON c."id" = f."cliente_id"
            LEFT JOIN LATERAL unnest(string_to_array(
                       COALESCE(f."detalles", ''), ';')) AS t(det)
                ON btrim(t.det) <> ''
            LEFT JOIN core.servicios s
                ON {entero("split_part(t.det, ':', 1)")} = s."id";
            """,

            # ------- Hechos relacionales (Idea 1) ------------------------
            # Materializados por el ETL como core.factura_detalle
            "factura_detalle_desnormalizado": """
            DROP VIEW IF EXISTS analitica.factura_detalle_desnormalizado CASCADE;
            CREATE OR REPLACE VIEW analitica.factura_detalle_desnormalizado AS
            SELECT d."factura_id",
                   d."fecha",
                   d."cliente_id",
                   c."nombre"     AS cliente,
                   d."vehiculo_id",
                   v."marca",
                   v."modelo",
                   v."placa",
                   d."servicio_id",
                   s."nombre"     AS servicio,
                   d."cantidad",
                   d."subtotal"
            FROM core.factura_detalle d
            LEFT JOIN core.clientes c      ON c."id" = d."cliente_id"
            LEFT JOIN core.vehiculos v     ON v."id" = d."vehiculo_id"
            LEFT JOIN core.servicios s     ON s."id" = d."servicio_id";
            """,

            "ingresos_por_servicio_mensual": f"""
            DROP VIEW IF EXISTS analitica.ingresos_por_servicio_mensual CASCADE;
            CREATE OR REPLACE VIEW analitica.ingresos_por_servicio_mensual AS
            SELECT d."servicio",
                   {mes('d."fecha"')}  AS anio_mes,
                   {red('SUM(d."subtotal")', 2)} AS ingresos,
                   SUM(d."cantidad")            AS unidades
            FROM core.factura_detalle d
            WHERE d."servicio_id" IS NOT NULL
            GROUP BY 1, 2;
            """,

            "demanda_servicios_mensual": f"""
            DROP VIEW IF EXISTS analitica.demanda_servicios_mensual CASCADE;
            CREATE OR REPLACE VIEW analitica.demanda_servicios_mensual AS
            SELECT d."servicio",
                   {mes('d."fecha"')}  AS anio_mes,
                   SUM(COALESCE(d."cantidad", 1)) AS demanda
            FROM analitica.detalle_servicios d
            WHERE d."servicio_id" IS NOT NULL
            GROUP BY 1, 2;
            """,

            # ------- RFM / churn -----------------------------------------
            # Postgres 16 no tiene date_diff: `fecha - fecha` da los dias
            # completos (mismo recuento de cambios de dia que date_diff).
            "rfm_clientes": f"""
            DROP VIEW IF EXISTS analitica.rfm_clientes CASCADE;
            CREATE OR REPLACE VIEW analitica.rfm_clientes AS
            WITH max_fecha AS (
                SELECT MAX("fecha") AS max_f FROM core.facturas WHERE "estado" <> 'Cancelada'
            )
            SELECT f."cliente_id",
                   c."nombre",
                   CAST(CAST((SELECT max_f FROM max_fecha) AS date)
                        - CAST(MAX(f."fecha") AS date) AS BIGINT) AS recencia_dias,
                   COUNT(*)                 AS frecuencia,
                   {red('SUM(f."total")', 2)} AS monto
            FROM core.facturas f
            LEFT JOIN core.clientes c ON c."id" = f."cliente_id"
            WHERE f."estado" <> 'Cancelada'
            GROUP BY 1, 2;
            """,

            "churn_clientes": """
            DROP VIEW IF EXISTS analitica.churn_clientes CASCADE;
            CREATE OR REPLACE VIEW analitica.churn_clientes AS
            SELECT r.*,
                   (r."recencia_dias" > 90) AS en_riesgo
            FROM analitica.rfm_clientes r;
            """,

            # ------- Inventario ------------------------------------------
            # En Postgres `entero / entero` trunca (230/120 = 1) y en
            # DuckDB no: el numerador sube a double antes de dividir.
            "inventario_estado": f"""
            DROP VIEW IF EXISTS analitica.inventario_estado CASCADE;
            CREATE OR REPLACE VIEW analitica.inventario_estado AS
            SELECT p."id",
                   p."producto",
                   p."categoria",
                   p."precio_costo",
                   p."precio_venta",
                   p."stock_actual",
                   p."stock_minimo",
                   {red('p."stock_actual" * p."precio_costo"', 2)}     AS valor_inventario,
                   {red('p."precio_venta" - p."precio_costo"', 2)}     AS margen,
                   {red('(p."precio_venta" - p."precio_costo")::double precision / NULLIF(p."precio_costo", 0) * 100', 1)} AS margen_pct,
                   CASE
                       WHEN p."stock_actual" <= p."stock_minimo"                     THEN 'Bajo'
                       WHEN p."stock_actual" <= p."stock_minimo" * 1.5               THEN 'Medio'
                       ELSE 'Optimo'
                   END AS estado_stock
            FROM core.inventario p;
            """,
        }


__all__ = ["Dialecto", "DialectoDuckDB", "DialectoPostgres"]
