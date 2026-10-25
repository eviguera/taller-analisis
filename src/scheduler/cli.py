"""Punto de entrada CLI del scheduler de GIRO.

Uso:
    python -m src.scheduler.cli

Registra los jobs predeterminados y arranca el loop de polling.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from . import Scheduler
from .jobs_predeterminados import registrar_todos  # noqa: F401 — registra jobs al importar


def main() -> None:
    datos_dir = Path(os.environ.get("GIRO_DATA_DIR", "data"))
    sched = Scheduler(datos_dir)
    print(f"Scheduler iniciado para {datos_dir} (Ctrl+C para detener).")
    asyncio.run(sched.run())


if __name__ == "__main__":
    main()
