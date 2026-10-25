"""Scheduler de jobs recurrentes para GIRO.

Un loop ligero (stdlib asyncio, sin dependencias nuevas) que ejecuta en
segundo plano tareas programadas por workspace: evaluar alertas,
re-entrenar modelos, generar reportes, refrescar caches.

Inspirado en OpenExecutive (scheduler/runner.py): claim de acciones debidas
para no disparar dos veces, requeue de huérfanos tras un crash, y heartbeats
de distintos tipos.

Cada workspace tiene su propia cola de acciones (misma base de memoria que
el ledger de decisiones, tabla memoria_acciones_programadas), de modo que el
aislamiento por tenant se respeta (regla 1).

El scheduler no arranca al importar: hay que instanciar Scheduler y llamar
a run(). Diseñado para ejecutarse como proceso adicional del contenedor
(entrypoint.sh) o como comando CLI (python main.py scheduler run).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Callable, Optional

from ..memoria.episodico import (
    obtener_acciones_pendientes,
    marcar_accion_hecha,
    marcar_accion_fallida,
    registrar_ejecucion_scheduler,
    obtener_historial_scheduler,
    ruta_db_por_workspace,
)

log = logging.getLogger("taller.scheduler")

# Registro global de jobs: nombre -> callable(cfg) -> None.
# Los jobs se registran al importar sus modulos (sin efectos secundarios en
# import: solo se anaden al diccionario, no se ejecutan).
_JOBS: dict[str, Callable] = {}


def registrar_job(nombre: str, fn: Callable) -> None:
    """Registra un job recurrente por nombre."""
    _JOBS[nombre] = fn


def listar_jobs() -> list[str]:
    return sorted(_JOBS)


class Scheduler:
    """Loop de polling que ejecuta acciones pendientes."""

    def __init__(
        self,
        directorio_datos,
        poll_interval_seconds: int = 30,
        db_path=None,
    ):
        self.directorio_datos = directorio_datos
        self.db_path = db_path or ruta_db_por_workspace(directorio_datos)
        self.poll_interval = poll_interval_seconds
        self._started_at: Optional[datetime] = None
        self._last_tick: Optional[tuple[datetime, str]] = None
        self._stop = False

    def heartbeat(self) -> tuple[Optional[datetime], Optional[tuple[datetime, str]]]:
        return self._started_at, self._last_tick

    def _beat(self, outcome: str) -> None:
        self._last_tick = (datetime.now(UTC), outcome)

    async def run(self) -> None:
        """Bucle principal. Se detiene cuando se establece `self._stop = True`."""
        self._started_at = datetime.now(UTC)
        self._last_tick = None
        self._stop = False
        log.info("scheduler iniciado (poll_interval=%ds)", self.poll_interval)

        while not self._stop:
            try:
                ahora = datetime.now(UTC)
                pendientes = obtener_acciones_pendientes(self.db_path)
                if pendientes:
                    log.info("scheduler: %d accion(es) debida(s)", len(pendientes))
                for accion in pendientes:
                    try:
                        await self._ejecutar_accion(accion)
                        marcar_accion_hecha(accion.id, self.db_path)
                        registrar_ejecucion_scheduler(
                            job=accion.tipo,
                            estado="ok",
                            filas_afectadas=1,
                            db_path=self.db_path,
                        )
                    except Exception as exc:  # noqa: BLE001 — nunca se traga
                        log.exception("scheduler: accion %d fallo", accion.id)
                        marcar_accion_fallida(accion.id, str(exc), self.db_path)
                        registrar_ejecucion_scheduler(
                            job=accion.tipo,
                            estado="fallida",
                            error=str(exc),
                            db_path=self.db_path,
                        )
                self._beat("ran")
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — el tick nunca muere el scheduler
                log.exception("scheduler: tick fallo")
                self._beat("failed")
            try:
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                log.info("scheduler cancelado")
                raise

    def detener(self) -> None:
        self._stop = True

    async def _ejecutar_accion(self, accion) -> None:
        """Despacha una acción al job registrado que corresponda.

        `accion.tipo` debe coincidir con el nombre de un job registrado.
        """
        fn = _JOBS.get(accion.tipo)
        if fn is None:
            raise ValueError(f"No hay job registrado para el tipo {accion.tipo!r}")
        # Los jobs reciben la config del workspace. Se construye aqui para
        # no acoplar el scheduler a la UI ni a Streamlit.
        from .carga_config import carga_config_para_accion

        cfg = carga_config_para_accion(self.directorio_datos)
        # Ejecutar en thread para no bloquear el loop si el job es sincronico.
        await asyncio.to_thread(fn, cfg)

    async def ejecutar_job_ahora(self, nombre_job: str) -> None:
        """Ejecuta un job registrado bajo demanda (desde la UI o CLI).

        Registra el resultado en el historial del scheduler.
        """
        fn = _JOBS.get(nombre_job)
        if fn is None:
            raise ValueError(f"No hay job registrado para {nombre_job!r}")
        from .carga_config import carga_config_para_accion

        cfg = carga_config_para_accion(self.directorio_datos)
        try:
            await asyncio.to_thread(fn, cfg)
            registrar_ejecucion_scheduler(
                job=nombre_job,
                estado="ok",
                db_path=self.db_path,
            )
            log.info("scheduler: job %s ejecutado bajo demanda", nombre_job)
        except Exception as exc:  # noqa: BLE001
            registrar_ejecucion_scheduler(
                job=nombre_job,
                estado="fallida",
                error=str(exc),
                db_path=self.db_path,
            )
            log.exception("scheduler: job %s bajo demanda fallo", nombre_job)
            raise

    def obtener_historial(self) -> list:
        """Devuelve el historial de ejecuciones del scheduler."""
        return obtener_historial_scheduler(db_path=self.db_path)
