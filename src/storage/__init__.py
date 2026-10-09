"""Capa de persistencia (DuckDB + cache parquet, PostgreSQL)."""

from .dialecto import Dialecto, DialectoDuckDB, DialectoPostgres
from .postgres import AlmacenPostgres
from .store import DataStore

__all__ = ["DataStore", "AlmacenPostgres", "Dialecto", "DialectoDuckDB",
           "DialectoPostgres"]
