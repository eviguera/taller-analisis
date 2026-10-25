"""Ledger de decisiones, iniciativas y consejos por workspace.

Todo se guarda en una base SQLite propia de cada workspace:
`<directorio_datos>/memoria.sqlite`. Nunca se mezcla información de dos
tenants en la misma base (regla 1).

El schema usa migraciones aditivas (ALTER TABLE guardadas por PRAGMA) para que
un segundo arranque sea un no-op, igual que hace OpenExecutive con su
episodic_memory.db.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger("taller.memoria")

# Ruta por defecto: se resuelve por workspace al llamar a ruta_db_por_workspace().
# El valor a nivel de modulo es solo un placeholder para tests.
DB_PATH = Path(os.environ.get("GIRO_MEMORIA_DB", "data/memoria.sqlite"))

# Validacion de nombre de tabla/identificador: solo alfanumerico y guion bajo.
_IDENTIFICADOR_RE = re.compile(r"^[a-z0-9_]+$")

_background_tasks: set[threading.Thread] = set()


@dataclass
class Decision:
    id: Optional[int] = None
    timestamp: str = ""
    dominio: str = ""
    resumen: str = ""
    justificacion: str = ""
    resultado: str = ""
    etiquetas: str = ""
    sesion_id: str = ""


@dataclass
class Iniciativa:
    id: Optional[int] = None
    titulo: str = ""
    estado: str = ""
    creada_en: str = ""
    actualizada_en: str = ""
    resumen: str = ""


@dataclass
class Consejo:
    id: Optional[int] = None
    timestamp: str = ""
    dominio: str = ""
    resumen_consulta: str = ""
    resumen_consejo: str = ""
    sesion_id: str = ""


@dataclass
class AccionProgramada:
    id: Optional[int] = None
    creada_en: str = ""
    ejecutar_en: str = ""
    tipo: str = "ad_hoc"
    canal: str = "interno"
    canal_ref: str = ""
    texto_intencion: str = ""
    estado: str = "pendiente"
    intentos: int = 0
    ultimo_error: str = ""


def _validar_identificador(nombre: str) -> None:
    """Rechaza identificadores que no sean alfanumericos + guion bajo.

    Evita inyeccion SQL por nombre de tabla (no se pueden parametrizar en
    CREATE/ALTER, solo validar contra allowlist).
    """
    if not _IDENTIFICADOR_RE.match(nombre):
        raise ValueError(f"Identificador invalido: {nombre!r}")


def ruta_db_por_workspace(directorio_datos: Path) -> Path:
    """Ruta de la base SQLite de memoria para un workspace determinado.

    `directorio_datos` ya viene resuelta por `config_manager` (es
    `data/` para `principal` o `workspaces/<clave>/data/` para los demas).
    """
    directorio_datos = Path(directorio_datos)
    directorio_datos.mkdir(parents=True, exist_ok=True)
    return directorio_datos / "memoria.sqlite"


@contextmanager
def _get_conn(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def inicializar_db(db_path: Path = DB_PATH) -> None:
    """Crea las tablas de memoria si no existen. Idempotente."""
    with _get_conn(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS memoria_decisiones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                dominio TEXT NOT NULL,
                resumen TEXT NOT NULL,
                justificacion TEXT DEFAULT '',
                resultado TEXT DEFAULT '',
                etiquetas TEXT DEFAULT '',
                sesion_id TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS memoria_iniciativas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                estado TEXT NOT NULL,
                creada_en TEXT NOT NULL,
                actualizada_en TEXT NOT NULL,
                resumen TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS memoria_consejos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                dominio TEXT NOT NULL,
                resumen_consulta TEXT NOT NULL,
                resumen_consejo TEXT NOT NULL,
                sesion_id TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS memoria_acciones_programadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creada_en TEXT NOT NULL,
                ejecutar_en TEXT NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'ad_hoc',
                canal TEXT NOT NULL DEFAULT 'interno',
                canal_ref TEXT NOT NULL DEFAULT '',
                texto_intencion TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'pendiente',
                intentos INTEGER NOT NULL DEFAULT 0,
                ultimo_error TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_memoria_decisiones_dominio
                ON memoria_decisiones(dominio, timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_memoria_decisiones_sesion
                ON memoria_decisiones(sesion_id);
            CREATE INDEX IF NOT EXISTS idx_memoria_iniciativas_estado
                ON memoria_iniciativas(estado, actualizada_en DESC);
            CREATE INDEX IF NOT EXISTS idx_memoria_consejos_dominio
                ON memoria_consejos(dominio, timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_memoria_acciones_estado
                ON memoria_acciones_programadas(estado, ejecutar_en);
        """)


def _ahora_iso() -> str:
    return datetime.now(UTC).isoformat()


def _ventana_hace_dias(dias: int) -> str:
    return (datetime.now(UTC) - timedelta(days=dias)).isoformat()


def registrar_decision(
    dominio: str,
    resumen: str,
    justificacion: str = "",
    etiquetas: str = "",
    sesion_id: str = "",
    db_path: Path = DB_PATH,
) -> None:
    """Registra una decisión con deduplicación por ventana de 7 días.

    Si ya existe una decisión del mismo dominio y resumen (primeros 80 chars)
    en los últimos 7 días y misma sesión, no se duplica (solo se actualiza la
    justificación si la nueva la trae y la anterior no).
    """
    _validar_identificador(dominio.replace(" ", "_")) if " " in dominio else None
    # El dominio es libre texto de negocio, no un identificador SQL: no se usa
    # en nombres de tabla, solo en valores parametrizados.
    ahora = _ahora_iso()
    inicio_ventana = _ventana_hace_dias(7)
    resumen_prefijo = resumen[:80]
    with _get_conn(db_path) as conn:
        existente = conn.execute(
            """
            SELECT id, justificacion FROM memoria_decisiones
            WHERE dominio = ? AND timestamp > ? AND substr(resumen, 1, 80) = ?
              AND sesion_id = ?
            """,
            (dominio, inicio_ventana, resumen_prefijo, sesion_id),
        ).fetchone()
        if existente:
            if justificacion and not existente["justificacion"]:
                conn.execute(
                    "UPDATE memoria_decisiones SET justificacion = ? WHERE id = ?",
                    (justificacion, existente["id"]),
                )
            log.debug(
                "Decision duplicada en dominio=%s (fila %d), omitida",
                dominio, existente["id"],
            )
            return
        conn.execute(
            """
            INSERT INTO memoria_decisiones
                (timestamp, dominio, resumen, justificacion, etiquetas, sesion_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ahora, dominio, resumen, justificacion, etiquetas, sesion_id),
        )


def registrar_iniciativa(
    titulo: str,
    estado: str,
    resumen: str = "",
    db_path: Path = DB_PATH,
) -> None:
    """Crea o actualiza una iniciativa. Upsert por titulo."""
    ahora = _ahora_iso()
    with _get_conn(db_path) as conn:
        existente = conn.execute(
            "SELECT id, estado, resumen FROM memoria_iniciativas WHERE titulo = ?",
            (titulo,),
        ).fetchone()
        if existente:
            cambios = []
            params: list = []
            if estado is not None and estado != existente["estado"]:
                cambios.append("estado = ?"); params.append(estado)
            if resumen and resumen != (existente["resumen"] or ""):
                cambios.append("resumen = ?"); params.append(resumen)
            if cambios:
                cambios.append("actualizada_en = ?"); params.append(ahora)
                params.append(existente["id"])
                conn.execute(
                    f"UPDATE memoria_iniciativas SET {', '.join(cambios)} WHERE id = ?",
                    params,
                )
        else:
            conn.execute(
                """
                INSERT INTO memoria_iniciativas
                    (titulo, estado, creada_en, actualizada_en, resumen)
                VALUES (?, ?, ?, ?, ?)
                """,
                (titulo, estado, ahora, ahora, resumen),
            )


def registrar_consejo(
    dominio: str,
    resumen_consulta: str,
    resumen_consejo: str,
    sesion_id: str = "",
    db_path: Path = DB_PATH,
) -> None:
    """Registra un consejo dado por el sistema, con deduplicación de 7 días."""
    ahora = _ahora_iso()
    inicio_ventana = _ventana_hace_dias(7)
    consejo_prefijo = resumen_consejo[:80]
    with _get_conn(db_path) as conn:
        existente = conn.execute(
            """
            SELECT id FROM memoria_consejos
            WHERE dominio = ? AND timestamp > ? AND substr(resumen_consejo, 1, 80) = ?
              AND sesion_id = ?
            """,
            (dominio, inicio_ventana, consejo_prefijo, sesion_id),
        ).fetchone()
        if existente:
            log.debug(
                "Consejo duplicado en dominio=%s (fila %d), omitido",
                dominio, existente["id"],
            )
            return
        conn.execute(
            """
            INSERT INTO memoria_consejos
                (timestamp, dominio, resumen_consulta, resumen_consejo, sesion_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ahora, dominio, resumen_consulta, resumen_consejo, sesion_id),
        )


def obtener_decisiones_recientes(
    limite: int = 10,
    db_path: Path = DB_PATH,
    sesion_id: str = "",
) -> list[Decision]:
    """Devuelve las N decisiones más recientes, opcionalmente filtradas por sesión."""
    if not Path(db_path).exists():
        return []
    with _get_conn(db_path) as conn:
        if sesion_id:
            filas = conn.execute(
                "SELECT * FROM memoria_decisiones WHERE sesion_id = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (sesion_id, limite),
            ).fetchall()
        else:
            filas = conn.execute(
                "SELECT * FROM memoria_decisiones ORDER BY timestamp DESC LIMIT ?",
                (limite,),
            ).fetchall()
    return [Decision(**dict(f)) for f in filas]


def obtener_iniciativas_activas(
    db_path: Path = DB_PATH,
) -> list[Iniciativa]:
    """Iniciativas que no están completadas."""
    if not Path(db_path).exists():
        return []
    with _get_conn(db_path) as conn:
        filas = conn.execute(
            "SELECT * FROM memoria_iniciativas WHERE estado != 'completada' "
            "ORDER BY actualizada_en DESC"
        ).fetchall()
    return [Iniciativa(**dict(f)) for f in filas]


def obtener_consejos_recientes(
    limite: int = 5,
    db_path: Path = DB_PATH,
    sesion_id: str = "",
) -> list[Consejo]:
    if not Path(db_path).exists():
        return []
    with _get_conn(db_path) as conn:
        if sesion_id:
            filas = conn.execute(
                "SELECT * FROM memoria_consejos WHERE sesion_id = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (sesion_id, limite),
            ).fetchall()
        else:
            filas = conn.execute(
                "SELECT * FROM memoria_consejos ORDER BY timestamp DESC LIMIT ?",
                (limite,),
            ).fetchall()
    return [Consejo(**dict(f)) for f in filas]


def decisiones_pendientes_resultado(
    mas_antiguas_que: datetime,
    limite: int = 5,
    db_path: Path = DB_PATH,
) -> list[Decision]:
    """Decisiones sin resultadoregistrado, mas viejas que una fecha."""
    if not Path(db_path).exists():
        return []
    limite_iso = mas_antiguas_que.astimezone(UTC).isoformat() if mas_antiguas_que.tzinfo \
        else mas_antiguas_que.isoformat()
    with _get_conn(db_path) as conn:
        filas = conn.execute(
            "SELECT * FROM memoria_decisiones WHERE timestamp < ? "
            "AND TRIM(COALESCE(resultado, '')) = '' "
            "ORDER BY timestamp DESC LIMIT ?",
            (limite_iso, limite),
        ).fetchall()
    return [Decision(**dict(f)) for f in filas]


def actualizar_resultado_decision(
    decision_id: int,
    resultado: str,
    db_path: Path = DB_PATH,
) -> bool:
    """Marca el resultado real de una decisión (p. ej. 'cliente reactivado')."""
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            "UPDATE memoria_decisiones SET resultado = ? WHERE id = ?",
            (resultado, decision_id),
        )
        return cursor.rowcount > 0


def listar_decisiones(db_path: Path = DB_PATH) -> list[Decision]:
    if not Path(db_path).exists():
        return []
    with _get_conn(db_path) as conn:
        filas = conn.execute(
            "SELECT * FROM memoria_decisiones ORDER BY timestamp DESC"
        ).fetchall()
    return [Decision(**dict(f)) for f in filas]


def listar_iniciativas(db_path: Path = DB_PATH) -> list[Iniciativa]:
    if not Path(db_path).exists():
        return []
    with _get_conn(db_path) as conn:
        filas = conn.execute(
            "SELECT * FROM memoria_iniciativas ORDER BY actualizada_en DESC"
        ).fetchall()
    return [Iniciativa(**dict(f)) for f in filas]


def listar_consejos(db_path: Path = DB_PATH) -> list[Consejo]:
    if not Path(db_path).exists():
        return []
    with _get_conn(db_path) as conn:
        filas = conn.execute(
            "SELECT * FROM memoria_consejos ORDER BY timestamp DESC"
        ).fetchall()
    return [Consejo(**dict(f)) for f in filas]


def programar_accion(
    ejecutar_en: str,
    tipo: str = "ad_hoc",
    canal: str = "interno",
    canal_ref: str = "",
    texto_intencion: str = "",
    db_path: Path = DB_PATH,
) -> int:
    """Inserta una acción programada y devuelve su id."""
    ahora = _ahora_iso()
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO memoria_acciones_programadas
                (creada_en, ejecutar_en, tipo, canal, canal_ref, texto_intencion, estado)
            VALUES (?, ?, ?, ?, ?, ?, 'pendiente')
            """,
            (ahora, ejecutar_en, tipo, canal, canal_ref, texto_intencion),
        )
        return int(cursor.lastrowid)


def obtener_acciones_pendientes(
    db_path: Path = DB_PATH,
    limite: int = 50,
) -> list[AccionProgramada]:
    """Acciones cuyo estado es 'pendiente' y cuya hora de ejecucion ya paso."""
    if not Path(db_path).exists():
        return []
    ahora = _ahora_iso()
    with _get_conn(db_path) as conn:
        filas = conn.execute(
            """
            SELECT * FROM memoria_acciones_programadas
            WHERE estado = 'pendiente' AND ejecutar_en <= ?
            ORDER BY ejecutar_en ASC LIMIT ?
            """,
            (ahora, limite),
        ).fetchall()
    return [AccionProgramada(**dict(f)) for f in filas]


def marcar_accion_hecha(
    accion_id: int,
    db_path: Path = DB_PATH,
) -> bool:
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            "UPDATE memoria_acciones_programadas SET estado = 'hecha' WHERE id = ?",
            (accion_id,),
        )
        return cursor.rowcount > 0


def marcar_accion_fallida(
    accion_id: int,
    error: str,
    db_path: Path = DB_PATH,
) -> bool:
    with _get_conn(db_path) as conn:
        conn.execute(
            "UPDATE memoria_acciones_programadas "
            "SET estado = 'fallida', intentos = intentos + 1, ultimo_error = ? WHERE id = ?",
            (error, accion_id),
        )
        return True


# ---------------------------------------------------------------------------
#  Mutes de alertas (silenciar reglas o entidades por tiempo)
# ---------------------------------------------------------------------------

@dataclass
class AlertaMute:
    id: Optional[int] = None
    creada_en: str = ""
    tipo: str = ""
    entidad: str = ""
    hasta: str = ""
    motivo: str = ""


def _ensure_mutes_tabla(db_path: Path) -> None:
    """Crea la tabla de mutes si no existe (idempotente)."""
    with _get_conn(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_mutes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creada_en TEXT NOT NULL,
                tipo TEXT NOT NULL,
                entidad TEXT NOT NULL,
                hasta TEXT NOT NULL,
                motivo TEXT DEFAULT ''
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_alert_mutes_tipo_entidad "
            "ON alert_mutes(tipo, entidad)"
        )


def agregar_mute(
    tipo: str,
    entidad: str,
    hasta_iso: str,
    motivo: str = "",
    db_path: Path = DB_PATH,
) -> int:
    """Silencia alertas de `tipo`+`entidad` hasta `hasta_iso`. Devuelve el id."""
    ahora = _ahora_iso()
    _ensure_mutes_tabla(db_path)
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO alert_mutes (creada_en, tipo, entidad, hasta, motivo)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ahora, tipo, entidad, hasta_iso, motivo),
        )
        return int(cursor.lastrowid)


def listar_mutes(db_path: Path = DB_PATH) -> list[AlertaMute]:
    """Todos los mutes activos (aún no expirados)."""
    _ensure_mutes_tabla(db_path)
    ahora = _ahora_iso()
    with _get_conn(db_path) as conn:
        filas = conn.execute(
            "SELECT * FROM alert_mutes WHERE hasta > ? ORDER BY creada_en DESC",
            (ahora,),
        ).fetchall()
    return [AlertaMute(**dict(f)) for f in filas]


def eliminar_mute(mute_id: int, db_path: Path = DB_PATH) -> bool:
    """Elimina un mute por id."""
    with _get_conn(db_path) as conn:
        cursor = conn.execute("DELETE FROM alert_mutes WHERE id = ?", (mute_id,))
        return cursor.rowcount > 0


def matches_mute(tipo: str, entidad: str, db_path: Path = DB_PATH) -> bool:
    """True si existe un mute activo para tipo+entidad."""
    _ensure_mutes_tabla(db_path)
    ahora = _ahora_iso()
    with _get_conn(db_path) as conn:
        fila = conn.execute(
            "SELECT 1 FROM alert_mutes WHERE tipo = ? AND entidad = ? AND hasta > ? LIMIT 1",
            (tipo, entidad, ahora),
        ).fetchone()
        return fila is not None


# ---------------------------------------------------------------------------
#  Historial de ejecuciones del scheduler
# ---------------------------------------------------------------------------

@dataclass
class HistorialEjecucion:
    id: Optional[int] = None
    ejecutada_en: str = ""
    job: str = ""
    estado: str = ""   # 'ok', 'fallida'
    error: str = ""
    filas_afectadas: int = 0


def _ensure_scheduler_historial_tabla(db_path: Path) -> None:
    """Crea la tabla de historial del scheduler si no existe (idempotente)."""
    with _get_conn(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduler_historial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ejecutada_en TEXT NOT NULL,
                job TEXT NOT NULL,
                estado TEXT NOT NULL,
                error TEXT DEFAULT '',
                filas_afectadas INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_scheduler_historial_job "
            "ON scheduler_historial(job, ejecutada_en DESC)"
        )


def registrar_ejecucion_scheduler(
    job: str,
    estado: str,
    error: str = "",
    filas_afectadas: int = 0,
    db_path: Path = DB_PATH,
) -> int:
    """Registra una ejecución del scheduler (ok o fallida)."""
    ahora = _ahora_iso()
    _ensure_scheduler_historial_tabla(db_path)
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO scheduler_historial
                (ejecutada_en, job, estado, error, filas_afectadas)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ahora, job, estado, error, filas_afectadas),
        )
        return int(cursor.lastrowid)


def obtener_historial_scheduler(
    db_path: Path = DB_PATH,
    limite: int = 50,
) -> list[HistorialEjecucion]:
    """Últimas ejecuciones del scheduler."""
    _ensure_scheduler_historial_tabla(db_path)
    if not Path(db_path).exists():
        return []
    with _get_conn(db_path) as conn:
        filas = conn.execute(
            "SELECT * FROM scheduler_historial ORDER BY ejecutada_en DESC LIMIT ?",
            (limite,),
        ).fetchall()
    return [HistorialEjecucion(**dict(f)) for f in filas]


def obtener_todas_acciones(
    db_path: Path = DB_PATH,
    limite: int = 100,
) -> list[AccionProgramada]:
    """Todas las acciones programadas (no solo pendientes)."""
    if not Path(db_path).exists():
        return []
    with _get_conn(db_path) as conn:
        filas = conn.execute(
            "SELECT * FROM memoria_acciones_programadas ORDER BY ejecutar_en DESC LIMIT ?",
            (limite,),
        ).fetchall()
    return [AccionProgramada(**dict(f)) for f in filas]


def obtener_todas_iniciativas(db_path: Path = DB_PATH) -> list[Iniciativa]:
    """Todas las iniciativas (activas y completadas)."""
    if not Path(db_path).exists():
        return []
    with _get_conn(db_path) as conn:
        filas = conn.execute(
            "SELECT * FROM memoria_iniciativas ORDER BY actualizada_en DESC"
        ).fetchall()
    return [Iniciativa(**dict(f)) for f in filas]


def eliminar_iniciativa(iniciativa_id: int, db_path: Path = DB_PATH) -> bool:
    """Elimina una iniciativa por id."""
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM memoria_iniciativas WHERE id = ?", (iniciativa_id,)
        )
        return cursor.rowcount > 0
