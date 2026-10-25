"""Motor narrativo del briefing ejecutivo.

Todas las funciones son puras sobre datos ya cargados (dict de DataFrames +
alertas + KPIs). No hay efectos secundarios en import.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

import pandas as pd

DIA_TRANQUILO = (
    "Todo en orden por ahora: no hay alertas críticas ni cambios significativos "
    "en los ingresos desde tu última visita."
)


def _moneda(valor: float, cfg) -> str:
    """Formatea un monto usando el formato compartido del repo."""
    try:
        from ..formatos import moneda

        return moneda(valor, cfg.moneda if cfg else "MXN")
    except Exception:  # noqa: BLE001 — fallback simple
        return f"{valor:,.0f}"


def _porcentaje(valor: float) -> str:
    return f"{valor * 100:.0f}%"


def resumen_ejecutivo(
    datos: dict,
    kpis: dict,
    alertas: list[dict],
    salud: dict,
    cfg=None,
) -> str:
    """Genera el texto completo del briefing ejecutivo en español.

    Argumentos:
        datos: dict de DataFrames (como devuelve load_all).
        kpis: KPIs globales (Analyzer.kpis_globales).
        alertas: lista de alertas activas (evaluar_alertas o evaluar_alertas_avanzadas).
        salud: métricas de cartera (negocio.salud_cartera).
        cfg: AppConfig opcional para moneda y nombre del negocio.

    Devuelve un texto en Markdown listo para pintar en un panel de Streamlit.
    """
    nombre = getattr(cfg, "negocio_nombre", "tu negocio") if cfg else "tu negocio"
    moneda = getattr(cfg, "moneda", "MXN") if cfg else "MXN"

    partes: list[str] = []
    partes.append(f"# Briefing ejecutivo · {nombre}")
    partes.append(f"_Generado el {datetime.now(UTC).strftime('%d de %B de %Y')}_")
    partes.append("")

    # --- Llamada principal (Top call) ---
    llamada = _llamada_principal(kpis, alertas, salud, moneda)
    if llamada:
        partes.append("## 🎯 Llamada principal")
        partes.append(llamada)
        partes.append("")

    # --- Hoy (forma del día) ---
    hoy = _resumen_hoy(kpis, salud, moneda)
    if hoy:
        partes.append("## 📅 Hoy")
        partes.append(hoy)
        partes.append("")

    # --- Qué cambió ---
    cambio = _lo_que_cambio(kpis, alertas, moneda)
    if cambio:
        partes.append("## 🔄 Qué cambió")
        partes.append(cambio)
        partes.append("")

    # --- Necesita tu atención ---
    atencion = _necesita_atencion(alertas, moneda)
    if atencion:
        partes.append("## ⚠️ Necesita tu atención")
        partes.append(atencion)
        partes.append("")

    # --- En riesgo ---
    riesgo = _en_riesgo(salud, alertas, moneda)
    if riesgo:
        partes.append("## 📉 En riesgo")
        partes.append(riesgo)
        partes.append("")

    # --- Día tranquilo ---
    if not any([llamada, hoy, cambio, atencion, riesgo]):
        partes.append("## ✅ Día tranquilo")
        partes.append(DIA_TRANQUILO)
        partes.append("")

    return "\n".join(partes)


def _llamada_principal(kpis, alertas, salud, moneda) -> Optional[str]:
    """La decisión más importante en la que enfocarse hoy."""
    criticas = [a for a in alertas if a.get("severidad") == "critica"]
    medias = [a for a in alertas if a.get("severidad") == "media"]

    if criticas:
        a = criticas[0]
        return f"**{a['titulo']}.** {a['detalle']}"
    if salud and salud.get("monto_en_riesgo", 0) > 0:
        monto = _moneda(salud["monto_en_riesgo"], type("C", (), {"moneda": moneda})())
        return (
            f"Hay {_moneda(salud['monto_en_riesgo'], type('C', (), {'moneda': moneda})())} "
            f"de cartera en riesgo ({salud.get('pct_cartera_en_riesgo', 0):.0%} del total). "
            f"Prioriza recuperar a {salud.get('clientes_en_riesgo', 0)} cliente(s) antes de que se pierdan."
        )
    if medias:
        a = medias[0]
        return f"**{a['titulo']}.** {a['detalle']}"
    if kpis.get("total_ingresos", 0) > 0:
        return (
            f"Ingresos totales: {_moneda(kpis['total_ingresos'], type('C', (), {'moneda': moneda})())} "
            f"en {kpis.get('total_facturas', 0)} facturas, con {kpis.get('clientes_activos', 0)} cliente(s) activo(s)."
        )
    return None


def _resumen_hoy(kpis, salud, moneda) -> Optional[str]:
    """Forma del día: métricas clave del momento."""
    lineas = []
    if kpis.get("ticket_promedio"):
        lineas.append(
            f"- Ticket promedio: {_moneda(kpis['ticket_promedio'], type('C', (), {'moneda': moneda})())} por factura."
        )
    if kpis.get("clientes_activos"):
        lineas.append(f"- Clientes activos: {kpis['clientes_activos']}.")
    if kpis.get("vehiculos_atendidos"):
        lineas.append(f"- Vehículos atendidos: {kpis['vehiculos_atendidos']}.")
    if salud:
        churn = salud.get("churn_mensual", 0)
        lineas.append(f"- Churn mensual implícito: {churn:.1%}.")
        arpu = salud.get("arpu_mensual", 0)
        if arpu:
            lineas.append(f"- ARPU mensual: {_moneda(arpu, type('C', (), {'moneda': moneda})())}.")
    if not lineas:
        return None
    return "\n".join(lineas)


def _lo_que_cambio(kpis, alertas, moneda) -> Optional[str]:
    """Novedades desde la última visita: alertas nuevas y variaciones."""
    lineas = []
    recientes = [a for a in alertas if a.get("severidad") in ("critica", "media")]
    for a in recientes[:5]:
        lineas.append(f"- {a['titulo']}: {a['detalle']}")
    if kpis.get("descuentos_total", 0) > 0:
        lineas.append(
            f"- Descuentos aplicados: {_moneda(kpis['descuentos_total'], type('C', (), {'moneda': moneda})())}."
        )
    if not lineas:
        return None
    return "\n".join(lineas)


def _necesita_atencion(alertas, moneda) -> Optional[str]:
    """Acciones concretas que el usuario debe tomar."""
    lineas = []
    for a in alertas:
        if a.get("severidad") == "critica":
            lineas.append(f"- {a['titulo']} → {a['detalle']}")
    if not lineas:
        return None
    return "\n".join(lineas)


def _en_riesgo(salud, alertas, moneda) -> Optional[str]:
    """Cartera y métricas que están en peligro."""
    if not salud:
        return None
    lineas = []
    if salud.get("clientes_en_riesgo", 0) > 0:
        lineas.append(
            f"- {salud['clientes_en_riesgo']} cliente(s) en riesgo de abandono "
            f"({salud.get('pct_cartera_en_riesgo', 0):.0%} de la cartera en monto)."
        )
    if salud.get("ltv_gross", 0) > 0:
        lineas.append(
            f"- LTV bruto estimado: {_moneda(salud['ltv_gross'], type('C', (), {'moneda': moneda})())}."
        )
    if not lineas:
        return None
    return "\n".join(lineas)


def generar_briefing(
    datos: dict,
    kpis: dict,
    alertas: list[dict],
    salud: dict,
    cfg=None,
    usar_llm: bool = False,
) -> str:
    """Punto de entrada único del briefing.

    Por defecto usa plantillas determinísticas (cero costo de LLM). Si
    `usar_llm=True` y hay un proveedor configurado, se puede extender para
    generar lenguaje con un modelo externo (opcional, al igual que hace
    OpenExecutive con Claude).
    """
    if usar_llm:
        return _generar_briefing_llm(datos, kpis, alertas, salud, cfg)
    return resumen_ejecutivo(datos, kpis, alertas, salud, cfg)


def _llm_chat(
    sistema: str,
    usuario: str,
    proveedor: str | None = None,
    api_key: str | None = None,
    modelo: str | None = None,
    base_url: str | None = None,
    temperatura: float = 0.3,
    max_tokens: int = 900,
) -> str:
    """Llama a un modelo de lenguaje externo usando solo stdlib (urllib).

    Lee credenciales de variables de entorno si no se pasan como argumento:
      * GIRO_LLM_PROVEEDOR: 'anthropic' | 'openai' | 'openrouter' | 'local'
      * GIRO_LLM_API_KEY: clave del proveedor
      * GIRO_LLM_MODELO: modelo a usar
      * GIRO_LLM_BASE_URL: base URL (para openai/openrouter/local)

    Si no hay proveedor ni clave configurada, devuelve cadena vacía (el
    llamador debe hacer fallback a plantillas determinísticas).
    """
    import json
    import os
    import urllib.error
    import urllib.request

    proveedor = proveedor or os.environ.get("GIRO_LLM_PROVEEDOR", "").strip().lower()
    api_key = api_key or os.environ.get("GIRO_LLM_API_KEY", "").strip()
    modelo = modelo or os.environ.get("GIRO_LLM_MODELO", "").strip()
    base_url = base_url or os.environ.get("GIRO_LLM_BASE_URL", "").strip()

    if not proveedor or not api_key or not modelo:
        return ""

    try:
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
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data.get("content", [{}])[0].get("text", "")

        # Proveedores OpenAI-compatible (openai, openrouter, local, etc.)
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
        headers = {"Content-Type": "application/json"}
        if proveedor == "openrouter":
            headers["HTTP-Referer"] = "https://giro-analytics.local"
            headers["X-Title"] = "GIRO Analytics"
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError, KeyError) as exc:
        # Nunca falle silenciosamente: loguea y deja que el llamador haga fallback.
        import logging

        log = logging.getLogger("taller.briefing")
        log.warning("LLM no disponible (%s); usando plantillas determinísticas", exc)
        return ""


def _generar_briefing_llm(datos, kpis, alertas, salud, cfg) -> str:
    """Genera el briefing con un LLM externo si está configurado.

    Si no hay `GIRO_LLM_API_KEY` / `GIRO_LLM_PROVEEDOR`, cae a plantillas
    determinísticas (cero costo). Nunca hardcodea credenciales.
    """
    nombre = getattr(cfg, "negocio_nombre", "tu negocio") if cfg else "tu negocio"
    moneda = getattr(cfg, "moneda", "MXN") if cfg else "MXN"

    sistema = (
        "Eres un ejecutivo de negocio experto. Resume en español, de forma "
        "concisa y accionable, lo que está pasando en el negocio del usuario. "
        "Usa solo los datos que se te proporcionan; no inventes nombres de "
        "clientes, montos ni fechas. Estructura la respuesta con las secciones: "
        "Llamada principal, Hoy, Qué cambió, Necesita tu atención, En riesgo."
    )

    resumen_texto = resumen_ejecutivo(datos, kpis, alertas, salud, cfg)
    usuario = (
        f"Negocio: {nombre} (moneda: {moneda})\n\n"
        f"Datos actuales del negocio (resumen ejecutivo automático):\n{resumen_texto}\n\n"
        "Redacta un briefing ejecutivo en español, directo y sin florituras."
    )

    texto_llm = _llm_chat(sistema=sistema, usuario=usuario)
    if texto_llm:
        return texto_llm
    # Fallback a plantillas determinísticas si el LLM no responde.
    return resumen_texto


def dia_tranquilo() -> str:
    return DIA_TRANQUILO
