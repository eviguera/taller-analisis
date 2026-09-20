"""Motor de alertas: reglas configurables evaluadas sobre los datos.

Reglas (config ``alertas``):
  * stock_bajo            -> productos con stock por debajo del minimo.
  * churn_riesgo_umbral   -> clientes con probabilidad de churn >= umbral.
  * caida_ingresos_mom    -> variacion de ingresos mensual bajo el umbral.
  * facturas_pendientes_dias -> facturas Pendientes con mas de X dias.

Incluye generacion de reporte HTML y envio por SMTP (opcional, el password se
lee de una variable de entorno para no guardar secretos).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .analyzer import Analyzer
from .core.config import AppConfig
from .predictions import Predictor

SEVERIDADES = {"critica": 0, "media": 1, "baja": 2}


def _cfg(rules_cfg):
    return (rules_cfg or {}) or {}


def evaluar_alertas(cfg: AppConfig, data: dict) -> List[dict]:
    """Evalua todas las reglas configuradas y devuelve lista de alertas."""
    ac = _cfg(cfg.alertas)
    reglas_activas = {
        "stock_bajo": bool(ac.get("stock_bajo", True)),
        "churn": bool(ac.get("churn", True)),
        "caida_ingresos": bool(ac.get("caida_ingresos", True)),
        "facturas_pendientes": bool(ac.get("facturas_pendientes", True)),
    }

    alertas: List[dict] = []
    analyzer = Analyzer(data)
    predictor = Predictor(data, cfg=cfg)

    # ---- Regla: stock bajo ----
    if reglas_activas["stock_bajo"]:
        inv = predictor.predecir_inventario()
        if not inv.empty:
            criticos = inv[inv["recomendacion"] == "Reabastecer"]
            max_n = int(ac.get("max_stock_alertas", 10))
            for r in criticos.head(max_n).itertuples():
                cant = getattr(r, "cantidad_recomendada", 0)
                alertas.append({
                    "tipo": "stock_bajo",
                    "severidad": "critica" if (r.stock_actual <= r.stock_minimo) else "media",
                    "titulo": f"{r.producto} requiere reabastecimiento",
                    "detalle": (
                        f"Categoria {r.categoria} · stock {r.stock_actual:.0f} vs minimo "
                        f"{r.stock_minimo:.0f} · demanda {r.demanda_mensual:.1f}/mes "
                        f"· pedir ≈ {cant:.0f} uni."),
                    "categoria": r.categoria,
                    "valor": f"x{cant:.0f}",
                })

    # ---- Regla: riesgo de churn ----
    if reglas_activas["churn"]:
        umbral = float(ac.get("churn_riesgo_umbral", 0.60))
        churn = predictor.predecir_churn()
        if not churn["resultados"].empty and "prob_churn" in churn["resultados"]:
            en_riesgo = churn["resultados"][churn["resultados"]["prob_churn"] >= umbral]
            for r in en_riesgo.head(8).itertuples():
                alertas.append({
                    "tipo": "churn",
                    "severidad": "critica" if r.prob_churn >= 0.75 else "media",
                    "titulo": f"{r.nombre} en riesgo de abandono ({r.prob_churn:.0%})",
                    "detalle": (f"Recencia {r.recencia:.0f} dias · {r.frecuencia:.0f} facturas · "
                                f"monto {r.monto:,.0f}. Accion: {'Reactivar' if r.prob_churn >= umbral else 'Contacto'}"),
                    "categoria": "churn",
                    "valor": f"P={r.prob_churn:.0%}",
                })

    # ---- Regla: caida de ingresos mes a mes ----
    if reglas_activas["caida_ingresos"]:
        umbral_mom = float(ac.get("caida_ingresos_mom", -0.20))
        serie = analyzer.ingresos_por_mes()
        if len(serie) >= 2:
            ult = float(serie.iloc[-1]["total"])
            prev = float(serie.iloc[-2]["total"])
            if prev > 0 and (ult - prev) / prev < umbral_mom:
                var = (ult - prev) / prev
                alertas.append({
                    "tipo": "caida_ingresos",
                    "severidad": "critica",
                    "titulo": "Caida de ingresos mes a mes",
                    "detalle": (f"{serie.iloc[-1]['anio_mes']}: {ult:,.0f} vs "
                                f"{serie.iloc[-2]['anio_mes']}: {prev:,.0f} ({var:.0%})."),
                    "categoria": "ingresos",
                    "valor": f"{var:.0%}",
                })

    # ---- Regla: facturas pendientes ----
    if reglas_activas["facturas_pendientes"]:
        facturas = data.get("facturas", pd.DataFrame())
        dias = int(ac.get("facturas_pendientes_dias", 60))
        max_n = int(ac.get("max_facturas_pendientes", 20))
        if not facturas.empty and "estado" in facturas.columns and "fecha" in facturas.columns:
            pendientes = facturas[facturas["estado"] == "Pendiente"].copy()
            pendientes["fecha"] = pd.to_datetime(pendientes["fecha"], errors="coerce")
            pendientes["dias"] = (pd.Timestamp.today() - pendientes["fecha"]).dt.days
            vencidas = pendientes[pendientes["dias"] > dias]
            if not vencidas.empty:
                monto_pendiente = float(pendientes["total"].sum()) if "total" in pendientes else 0.0
                alertas.append({
                    "tipo": "facturas_pendientes",
                    "severidad": "media",
                    "titulo": f"{len(vencidas)} facturas pendientes con +{dias} dias",
                    "detalle": f"Monto total pendiente: {monto_pendiente:,.0f}.",
                    "categoria": "cobranza",
                    "valor": f"{len(vencidas)}",
                })

    alertas.sort(key=lambda a: SEVERIDADES.get(a["severidad"], 3))
    return alertas


def resumen_alertas(alertas: List[dict]) -> dict:
    """Conteo por severidad y tipo."""
    res = {
        "total": len(alertas),
        "critica": sum(1 for a in alertas if a["severidad"] == "critica"),
        "media": sum(1 for a in alertas if a["severidad"] == "media"),
        "baja": sum(1 for a in alertas if a["severidad"] == "baja"),
        "por_tipo": {},
    }
    for a in alertas:
        res["por_tipo"][a["tipo"]] = res["por_tipo"].get(a["tipo"], 0) + 1
    return res


def generar_reporte_alertas(cfg: AppConfig, data: dict, alertas: Optional[List[dict]] = None,
                            directorio: Optional[Path] = None) -> Path:
    """Genera un HTML con las alertas evaluadas y lo guarda en reports/."""
    alertas = alertas if alertas is not None else evaluar_alertas(cfg, data)
    res = resumen_alertas(alertas)
    dir_out = Path(directorio) if directorio else Path("reports")
    dir_out.mkdir(parents=True, exist_ok=True)
    fecha = datetime.now()
    ruta = dir_out / f"alertas-{fecha.strftime('%Y%m%d-%H%M%S')}.html"

    tarjetas = ""
    colores = {"critica": "#dc2626", "media": "#d97706", "baja": "#2563eb"}
    for a in alertas:
        color = colores.get(a["severidad"], "#64748b")
        tarjetas += f"""
        <div style="border-left:6px solid {color};background:#fff;border-radius:8px;
                    padding:14px 18px;margin:10px 0;box-shadow:0 1px 4px rgba(0,0,0,.08)">
          <div style="font-weight:700;color:#1e293b;">{a['titulo']}</div>
          <div style="color:#64748b;font-size:13px;margin-top:4px;">{a['detalle']}</div>
          <div style="margin-top:6px;">
            <span style="background:#e2e8f0;padding:2px 8px;border-radius:10px;font-size:11px;color:#475569;">
              {a['tipo']} · {a['severidad']}</span>
          </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>Alertas GIRO - {fecha.strftime('%d/%m/%Y %H:%M')}</title>
<style>
 body {{ font-family:'Helvetica Neue',Arial,sans-serif; background:#f1f5f9; margin:0; }}
 .header {{ background:linear-gradient(135deg,#1e3a8a,#2563eb); color:#fff; padding:28px 32px; }}
 .container {{ max-width:900px; margin:0 auto; padding:20px; }}
 .kpi {{ display:inline-block; background:#fff; border-radius:10px; padding:16px 22px; margin:8px;
         text-align:center; box-shadow:0 2px 6px rgba(0,0,0,.06); }}
 .kpi b {{ font-size:22px; display:block; }}
</style></head><body>
<div class="header"><h1>Alertas · {cfg.negocio_nombre}</h1>
<p>Generadas el {fecha.strftime('%d de %B de %Y a las %H:%M')}</p></div>
<div class="container">
  <div>
    <div class="kpi"><b>{res['total']}</b>Total</div>
    <div class="kpi" style="border-top:4px solid #dc2626"><b>{res['critica']}</b>Criticas</div>
    <div class="kpi" style="border-top:4px solid #d97706"><b>{res['media']}</b>Medias</div>
    <div class="kpi" style="border-top:4px solid #2563eb"><b>{res['baja']}</b>Bajas</div>
  </div>
  <h2 style="margin-top:24px;">Detalle</h2>
  {tarjetas or '<p style="color:#64748b;">Sin alertas activas.</p>'}
</div></body></html>"""

    ruta.write_text(html, encoding="utf-8")
    return ruta


def enviar_email(cfg: AppConfig, asunto: str, cuerpo: str) -> bool:
    """Envia el reporte por SMTP si esta configurado. Devuelve True si se envio."""
    import os
    import smtplib
    from email.mime.text import MIMEText

    ac = _cfg(cfg.alertas)
    smtp = dict(ac.get("smtp") or {})
    if not smtp.get("habilitado"):
        return False
    host = smtp.get("host", "")
    remitente = smtp.get("remitente", "")
    destino = smtp.get("destinatario", "")
    if not (host and remitente and destino):
        return False
    password = os.environ.get(smtp.get("password_env", "GIRO_SMTP_PASS"), "")

    msg = MIMEText(cuerpo, "html", "utf-8")
    msg["Subject"] = asunto
    msg["From"] = remitente
    msg["To"] = destino
    try:
        with smtplib.SMTP(host, int(smtp.get("puerto", 587)), timeout=15) as server:
            server.starttls()
            if password:
                server.login(remitente, password)
            server.send_message(msg)
        return True
    except Exception:  # noqa: BLE001
        return False