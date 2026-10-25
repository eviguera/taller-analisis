"""Alertas avanzadas: triage, deduplicacion y grounding.

Capa sobre `src/alerts.py` que añade:
  * Triage simple: clasifica cada hallazgo del motor de reglas en severidad
    (critica/media/baja) con criterios explicables, no solo el primero que
    llega.
  * Deduplicacion: una misma alerta (mismo tipo + misma entidad afectada) no
    se regenera en cada rerun de la UI; se mantiene una tabla de alertas
    activas por workspace en la base de memoria (SQLite).
  * Grounding: las titulos y detalles solo citan cifras y entidades que
    realmente aparecen en los datos del workspace; nunca se inventan nombres
    de clientes, montos o fechas.

Se integra con el ledger de decisiones (`src/memoria`): cada alerta nueva se
registra como una decisión de dominio "alerta" para que quede rastro de lo
que el sistema surgio y que el usuario hizo con ella.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from .alerts import (
    evaluar_alertas as evaluar_alertas_base,
    resumen_alertas,
    SEVERIDADES,
)
from .memoria.episodico import (
    inicializar_db,
    registrar_decision,
    matches_mute,
    ruta_db_por_workspace,
)

log = logging.getLogger("taller.alertas_avanzadas")

# Umbrales de triage explicables.
CHURN_CRITICA = 0.75
CHURN_MEDIA = 0.60
CAIDA_CRITICA = -0.30   # caída > 30% mes a mes es crítica
CAIDA_MEDIA = -0.15     # caída > 15% mes a mes es media

# Claves de dedup: (tipo_alerta, entidad) -> no repetir mientras esté abierta.
_DEDUP_HORAS = 24

# Severidades válidas para el triaje con LLM.
_SEVERIDADES_VALIDAS = {"critica", "media", "baja"}


def _triaje_con_llm(tipo: str, detalle: str, valores: dict) -> str | None:
    """Clasifica la severidad de una alerta usando un LLM externo si está
    configurado (GIRO_LLM_TRIAJE=1 + GIRO_LLM_API_KEY + GIRO_LLM_MODELO).

    Devuelve None si no hay proveedor configurado o falla la llamada, para
    que el llamador use el triaje basado en reglas como fallback.
    """
    if os.environ.get("GIRO_LLM_TRIAJE", "").strip().lower() not in ("1", "true", "si", "yes", "on"):
        return None
    api_key = os.environ.get("GIRO_LLM_API_KEY", "").strip()
    modelo = os.environ.get("GIRO_LLM_MODELO", "").strip()
    proveedor = os.environ.get("GIRO_LLM_PROVEEDOR", "openai").strip().lower()
    base_url = os.environ.get("GIRO_LLM_BASE_URL", "").strip()
    if not api_key or not modelo:
        return None

    sistema = (
        "Eres un analista de negocio. Clasifica la severidad de una alerta de "
        "negocio en exactamente una de estas tres categorías: 'critica', "
        "'media' o 'baja'. Responde SOLO con la palabra de la categoría, "
        "sin explicaciones. Considera el tipo de alerta, el detalle y los "
        "valores numéricos proporcionados."
    )
    usuario = (
        f"Tipo de alerta: {tipo}\n"
        f"Detalle: {detalle}\n"
        f"Valores: {json.dumps(valores, ensure_ascii=False)}\n"
        f"Responde solo con: critica / media / baja"
    )

    try:
        texto = _llm_chat_alertas(sistema, usuario, proveedor, api_key, modelo, base_url)
        texto_limpio = texto.strip().lower()
        for s in _SEVERIDADES_VALIDAS:
            if s in texto_limpio:
                return s
        return None
    except Exception:  # noqa: BLE001 — fallback a reglas
        return None


def _llm_chat_alertas(
    sistema: str,
    usuario: str,
    proveedor: str,
    api_key: str,
    modelo: str,
    base_url: str = "",
    temperatura: float = 0.1,
    max_tokens: int = 20,
) -> str:
    """Llama a un LLM para el triaje de alertas (solo stdlib urllib)."""
    if proveedor == "anthropic":
        url = (base_url or "https://api.anthropic.com/v1/messages").rstrip("/")
        body = {
            "model": modelo,
            "max_tokens": max_tokens,
            "temperature": temperatura,
            "system": sistema,
            "messages": [{"role": "user", "content": usuario}],
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("content", [{}])[0].get("text", "")

    url = (base_url or "https://api.openai.com/v1/chat/completions").rstrip("/")
    body = {
        "model": modelo,
        "temperature": temperatura,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": sistema},
            {"role": "user", "content": usuario},
        ],
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    if proveedor == "openrouter":
        headers["HTTP-Referer"] = "https://giro-analytics.local"
        headers["X-Title"] = "GIRO Analytics"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


def _ahora_iso() -> str:
    return datetime.now(UTC).isoformat()


def _ventana_hace_horas(horas: int) -> str:
    return (datetime.now(UTC) - timedelta(hours=horas)).isoformat()


def _existe_alerta_reciente(
    tipo: str,
    entidad: str,
    db_path: Path,
    horas: int = _DEDUP_HORAS,
) -> bool:
    """True si ya hay una decisión de alerta del mismo tipo y entidad en las
    últimas `horas` horas (dedup por ventana)."""
    if not db_path.exists():
        return False
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        fila = conn.execute(
            """
            SELECT id FROM memoria_decisiones
            WHERE dominio = 'alerta'
              AND substr(resumen, 1, 120) = ?
              AND timestamp > ?
            LIMIT 1
            """,
            (f"[{tipo}] {entidad}", _ventana_hace_horas(horas)),
        ).fetchone()
        return fila is not None
    finally:
        conn.close()


def _clasificar_severidad(tipo: str, detalle: str, valores: dict) -> str:
    """Triage: LLM opcional primero, reglas explicables como fallback."""
    severidad_llm = _triaje_con_llm(tipo, detalle, valores)
    if severidad_llm is not None:
        return severidad_llm

    # Reglas explicables (siempre disponibles, sin costo de LLM).
    if tipo == "churn":
        prob = valores.get("prob_churn", 0.0)
        if prob >= CHURN_CRITICA:
            return "critica"
        if prob >= CHURN_MEDIA:
            return "media"
        return "baja"
    if tipo == "caida_ingresos":
        var = valores.get("variacion", 0.0)
        if var <= CAIDA_CRITICA:
            return "critica"
        if var <= CAIDA_MEDIA:
            return "media"
        return "baja"
    if tipo == "stock_bajo":
        # severidad ya viene del motor base; respetarla
        return valores.get("severidad", "media")
    if tipo == "facturas_pendientes":
        return "media"
    return "baja"


def _grounding_titulo(tipo: str, entidad: str, detalle: str) -> str:
    """Construye un título que solo cite lo que hay en los datos."""
    plantillas = {
        "stock_bajo": f"Stock bajo: {entidad}",
        "churn": f"Cliente en riesgo de churn: {entidad}",
        "caida_ingresos": "Caida de ingresos mes a mes",
        "facturas_pendientes": "Facturas pendientes vencidas",
    }
    return plantillas.get(tipo, f"Alerta: {tipo}")


def evaluar_alertas_avanzadas(
    cfg,
    data: dict,
    db_path: Optional[Path] = None,
    analyzer=None,
    predictor=None,
) -> list[dict]:
    """Evalua alertas con triage, deduplicacion y grounding.

    Devuelve la lista de alertas activas (nuevas + ya conocidas). Cada alerta
    lleva un campo ``dedup_key`` y ``severidad`` calculada por triage.

    Si `db_path` es None se usa la base de memoria del workspace activo
    (según `cfg.directorio_datos`).
    """
    if db_path is None:
        db_path = ruta_db_por_workspace(cfg.directorio_datos)

    # Asegurar que el ledger de memoria exista (idempotente).
    try:
        inicializar_db(db_path)
    except Exception as exc:  # noqa: BLE001 — no bloquee las alertas por la memoria
        log.warning("No se pudo inicializar el ledger de memoria: %s", exc)

    # Ejecutar el motor de reglas base (ya existe y está testeado).
    alertas_base = evaluar_alertas_base(cfg, data, analyzer=analyzer, predictor=predictor)

    alertas_finales: list[dict] = []
    for a in alertas_base:
        tipo = a.get("tipo", "desconocida")
        entidad = a.get("categoria", tipo)
        # El detalle del motor base ya viene con cifras reales; las usamos tal
        # cual (grounding: no inventamos nada).
        detalle = a.get("detalle", "")
        severidad = _clasificar_severidad(tipo, detalle, a)

        dedup_key = f"{tipo}:{entidad}"

        # Mute: si hay un mute activo para este tipo+entidad, silenciamos.
        if matches_mute(tipo, entidad, db_path):
            continue

        # Dedup: si ya existe una alerta reciente del mismo tipo+entidad, no
        # dupliquemos (a menos que la severidad haya escalado a critica).
        reciente = _existe_alerta_reciente(tipo, entidad, db_path)
        if reciente and severidad != "critica":
            continue

        alerta = {
            "tipo": tipo,
            "severidad": severidad,
            "titulo": _grounding_titulo(tipo, entidad, detalle),
            "detalle": detalle,
            "categoria": a.get("categoria", tipo),
            "valor": a.get("valor", ""),
            "dedup_key": dedup_key,
            "origen": "motor_reglas",
            "generada_en": _ahora_iso(),
        }
        alertas_finales.append(alerta)

        # Registrar como decisión de dominio "alerta" en el ledger.
        try:
            registrar_decision(
                dominio="alerta",
                resumen=f"[{tipo}] {entidad}: {detalle[:120]}",
                justificacion=f"Severidad {severidad} por {tipo}.",
                etiquetas=f"alerta:{tipo},severidad:{severidad}",
                sesion_id="sistema",
                db_path=db_path,
            )
        except Exception as exc:  # noqa: BLE001 — no falle el flujo de alertas por memoria
            log.warning("No se pudo registrar la alerta en el ledger: %s", exc)

    # Ordenar por severidad (critica primero).
    alertas_finales.sort(key=lambda a: SEVERIDADES.get(a["severidad"], 3))
    return alertas_finales


def resumen_alertas_avanzadas(alertas: list[dict]) -> dict:
    """Conteo por severidad y tipo, igual que resumen_alertas pero con dedup_key."""
    res = {
        "total": len(alertas),
        "critica": sum(1 for a in alertas if a["severidad"] == "critica"),
        "media": sum(1 for a in alertas if a["severidad"] == "media"),
        "baja": sum(1 for a in alertas if a["severidad"] == "baja"),
        "por_tipo": {},
        "por_severidad": {"critica": 0, "media": 0, "baja": 0},
    }
    for a in alertas:
        res["por_tipo"][a["tipo"]] = res["por_tipo"].get(a["tipo"], 0) + 1
        res["por_severidad"][a["severidad"]] = res["por_severidad"].get(a["severidad"], 0) + 1
    return res
