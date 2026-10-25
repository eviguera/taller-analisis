"""Memoria operativa de GIRO (ledger de decisiones, iniciativas y consejos).

Captura lo que el sistema recomienda, lo que el usuario decide y el resultado
real, para que no sea "dispara y olvida". Cada workspace tiene su propia base
SQLite aislada (regla 1 del repositorio).

Arquitectura inspirada en OpenExecutive (SenteLabsAI): decisiones,
iniciativas y consejos registrados con deduplicacion por ventana de tiempo y
consultas recientes / pendientes de resultado.
"""

from __future__ import annotations

from .episodico import (
    DB_PATH,
    Decision,
    Iniciativa,
    Consejo,
    AccionProgramada,
    AlertaMute,
    HistorialEjecucion,
    inicializar_db,
    registrar_decision,
    registrar_iniciativa,
    registrar_consejo,
    obtener_decisiones_recientes,
    obtener_iniciativas_activas,
    obtener_consejos_recientes,
    decisiones_pendientes_resultado,
    actualizar_resultado_decision,
    listar_decisiones,
    listar_iniciativas,
    listar_consejos,
    ruta_db_por_workspace,
    obtener_acciones_pendientes,
    programar_accion,
    marcar_accion_hecha,
    marcar_accion_fallida,
    # Mutes de alertas
    agregar_mute,
    listar_mutes,
    eliminar_mute,
    matches_mute,
    # Historial del scheduler
    registrar_ejecucion_scheduler,
    obtener_historial_scheduler,
    # Todas las acciones / iniciativas (incluidas completadas)
    obtener_todas_acciones,
    obtener_todas_iniciativas,
    eliminar_iniciativa,
)

__all__ = [
    "DB_PATH",
    "Decision",
    "Iniciativa",
    "Consejo",
    "AccionProgramada",
    "AlertaMute",
    "HistorialEjecucion",
    "inicializar_db",
    "registrar_decision",
    "registrar_iniciativa",
    "registrar_consejo",
    "obtener_decisiones_recientes",
    "obtener_iniciativas_activas",
    "obtener_consejos_recientes",
    "decisiones_pendientes_resultado",
    "actualizar_resultado_decision",
    "listar_decisiones",
    "listar_iniciativas",
    "listar_consejos",
    "ruta_db_por_workspace",
    "obtener_acciones_pendientes",
    "programar_accion",
    "marcar_accion_hecha",
    "marcar_accion_fallida",
    # Mutes de alertas
    "agregar_mute",
    "listar_mutes",
    "eliminar_mute",
    "matches_mute",
    # Historial del scheduler
    "registrar_ejecucion_scheduler",
    "obtener_historial_scheduler",
    # Todas las acciones / iniciativas (incluidas completadas)
    "obtener_todas_acciones",
    "obtener_todas_iniciativas",
    "eliminar_iniciativa",
]
