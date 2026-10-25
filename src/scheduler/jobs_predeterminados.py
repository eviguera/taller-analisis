"""Jobs predeterminados del scheduler de GIRO.

Se registran al importar este modulo (efecto benigno: solo anaden al registro
_JOBS, no leen disco ni arrancan procesos). El entrypoint del contenedor los
importa antes de arrancar el loop del scheduler, de modo que este empieza a
ejecutar acciones utiles desde el primer segundo.

Jobs:
  * evaluar_alertas: reevaluar reglas de negocio del workspace activo.
"""

from __future__ import annotations

from src.data_loader import load_all
from src.scheduler import registrar_job


def _job_evaluar_alertas(cfg) -> None:
    """Reevalua las alertas del workspace y las registra en el ledger."""
    from src.alertas_avanzadas import evaluar_alertas_avanzadas

    data = load_all(cfg)
    evaluar_alertas_avanzadas(cfg, data)


registrar_job("evaluar_alertas", _job_evaluar_alertas)


def registrar_todos() -> None:
    """Registra todos los jobs predeterminados (idempotente)."""
    # Ya se registraron arriba al importar este modulo. Esta funcion existe
    # para claridad y para permitir registro explícito desde otros puntos.
    pass


__all__ = ["_job_evaluar_alertas", "registrar_todos"]
