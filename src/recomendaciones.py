"""Giro Recomienda: motor de siguiente mejor accion y mantenimiento predictivo.

Convierte la analitica (RFM, churn, hechos de servicios) en acciones concretas
por cliente y por vehiculo:

  * ``proximo_servicio``  -> que servicio necesita cada vehiculo y en que mes,
                             usando el intervalo tipico de mantenimiento.
  * ``next_best_action``  -> para cada cliente, la accion de mayor impacto
                             (reactivar, recordar mantenimiento, upsell, fidelidad)
                             con prioridad, canal y mensaje.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .core.hechos import construir_factura_detalle
from .predictions import Predictor

CANALES = {"WhatsApp", "Email", "Llamada"}

MENSAJES = {
    "Reactivar": "Hola {nombre}, queremos verte de nuevo: 15% de descuento en tu proxima visita.",
    "Recordatorio preventivo": "Hola {nombre}, tu {vehiculo} tiene programado su mantenimiento este mes.",
    "Upsell / servicio complementario": "Hola {nombre}, te recomendamos sumar {servicio} a tu proxima visita.",
    "Fidelidad": "Hola {nombre}, gracias por confiar en nosotros. Consulta tu beneficio exclusivo.",
    "Monitoreo": "Sin accion inmediata: manten en observacion a {nombre}.",
}


def _intervalos_meses(cfg) -> dict:
    mant = (cfg.mantenimiento or {}) or {}
    base = dict(mant.get("intervalos_meses", {}) or {})
    # Normaliza claves a minusculas para comparaciones robustas
    return {str(k).lower(): float(v) for k, v in base.items()}


def _edad_vehiculo_anios(anio, hoy):
    try:
        return max(0, hoy.year - int(anio))
    except (TypeError, ValueError):
        return 0.0


def _meses_desde(fecha, referencia):
    if pd.isna(fecha) or pd.isna(referencia):
        return 999
    return (referencia - fecha).days / 30.0


def proximo_servicio(data, cfg) -> pd.DataFrame:
    """Predice el proximo servicio preventivo de cada vehiculo.

    Combina el intervalo de mantenimiento configurado (``mantenimiento.
    intervalos_meses``) con el ultimo servicio similar realizado y la
    antiguedad/kilometraje del vehiculo.
    """
    vehiculos = data.get("vehiculos", pd.DataFrame()).copy()
    facturas = data.get("facturas", pd.DataFrame())
    if vehiculos.empty or facturas.empty:
        return pd.DataFrame()

    hechos = construir_factura_detalle(facturas, data.get("servicios"))
    hoy = pd.Timestamp.today()

    intervalos = _intervalos_meses(cfg)
    pendientes_considerar = int((cfg.mantenimiento or {}).get("pendientes_considerar", 3))

    # Ultima visita por vehiculo
    ultima_visita = hechos.groupby("vehiculo_id")["fecha"].max().to_dict() if not hechos.empty else {}

    filas = []
    for _, v in vehiculos.iterrows():
        vid = v.get("id")
        km = float(v.get("kilometraje", 0) or 0)
        edad = _edad_vehiculo_anios(v.get("anio"), hoy)
        ultima = ultima_visita.get(vid)
        meses_ultima = _meses_desde(ultima, hoy) if ultima is not None else 999
        cliente = None
        if "cliente_id" in v.index and "clientes" in data:
            cli = data["clientes"]
            m = cli[cli["id"] == v["cliente_id"]]
            if not m.empty:
                cliente = str(m.iloc[0].get("nombre", ""))

        candidatos = []
        for servicio, intervalo in intervalos.items():
            meses_desde_serv = 999
            if not hechos.empty:
                filas_s = hechos[
                    (hechos["vehiculo_id"] == vid)
                    & (hechos["servicio"].astype(str).str.lower().str.contains(
                        servicio, na=False))]
                if not filas_s.empty:
                    meses_desde_serv = _meses_desde(filas_s["fecha"].max(), hoy)

            pendiente = (intervalo - meses_desde_serv)
            if meses_desde_serv >= intervalo:
                candidatos.append({
                    "servicio": servicio.title(),
                    "nota": "vencido",
                    "urgencia": min(pendiente, 0) / intervalo,  # negativo: mas vencido
                    "meses_desde": meses_desde_serv,
                    "intervalo": intervalo,
                })
            elif meses_desde_serv < intervalo and 0 <= pendiente <= 2:
                candidatos.append({
                    "servicio": servicio.title(),
                    "nota": "proximo",
                    "urgencia": pendiente / intervalo,
                    "meses_desde": meses_desde_serv,
                    "intervalo": intervalo,
                })

        candidatos.sort(key=lambda c: c["urgencia"])
        top = candidatos[:pendientes_considerar]
        if top:
            primero = top[0]
            filas.append({
                "vehiculo_id": vid,
                "cliente": cliente or "—",
                "marca": v.get("marca", ""),
                "modelo": v.get("modelo", ""),
                "anio": v.get("anio", ""),
                "placa": v.get("placa", ""),
                "kilometraje": km,
                "edad_anios": round(edad, 1),
                "dias_sin_visita": int(max(0, meses_ultima * 30)),
                "servicio_sugerido": primero["servicio"],
                "nota": primero["nota"],
                "meses_estimados": round(primero["meses_desde"], 1),
                "intervalo_meses": primero["intervalo"],
                "prioridad": _prioridad_servicio(primero, km, edad),
            })

    df = pd.DataFrame(filas)
    if not df.empty:
        df = df.sort_values("prioridad", ascending=False)
    return df


def _prioridad_servicio(candidato, km, edad) -> int:
    """Prioridad 1..5: 5 = maxima urgencia."""
    p = 3
    if candidato["nota"] == "vencido" and candidato["meses_desde"] >= candidato["intervalo"] * 1.5:
        p += 2
    elif candidato["nota"] == "vencido":
        p += 1
    if km >= 80000 or edad >= 10:
        p += 1
    if km >= 150000 or edad >= 15:
        p += 1
    return int(min(5, p))


def next_best_action(data, cfg, n=25) -> pd.DataFrame:
    """Siguiente mejor accion por cliente (reactivar, recordar, upsell, fidelidad).

    Cruza el churn (ejecutado desde el registry si esta fresco) con la
    segmentacion RFM y el mantenimiento predictivo por vehiculo.
    """
    predictor_contexto = Predictor(data, cfg=cfg)
    churn = predictor_contexto.predecir_churn()
    rfm = churn["resultados"].copy() if not churn["resultados"].empty else pd.DataFrame()
    if rfm.empty:
        return pd.DataFrame()

    progs = proximo_servicio(data, cfg)
    servicio_por_cliente = {}
    if not progs.empty:
        top = progs.drop_duplicates("cliente", keep="first") if "cliente" in progs else progs
        servicio_por_cliente = dict(zip(top["cliente"], top["servicio_sugerido"]))

    umbral_churn = float((cfg.alertas or {}).get("churn_riesgo_umbral", 0.60))
    hoy = pd.Timestamp.today()

    filas = []
    for _, r in rfm.iterrows():
        nombre = str(r.get("nombre", ""))
        prob = float(r.get("prob_churn", 0) or 0)
        monto = float(r.get("monto", 0) or 0)
        recencia = float(r.get("recencia", 0) or 0)

        servicio = servicio_por_cliente.get(r.get("cliente_id"), "") or \
            servicio_por_cliente.get(nombre, "") or servicio_por_cliente.get(str(r["nombre"]), "")

        if prob >= umbral_churn:
            accion, canal, mensaje = "Reactivar", "WhatsApp", MENSAJES["Reactivar"].format(nombre=nombre)
        elif servicio:
            accion, canal = "Recordatorio preventivo", "Email"
            mensaje = MENSAJES["Recordatorio preventivo"].format(
                nombre=nombre, vehiculo=servicio)
        elif len(rfm) and monto >= float(rfm["monto"].quantile(0.8)):
            accion, canal = "Fidelidad", "Email"
            mensaje = MENSAJES["Fidelidad"].format(nombre=nombre)
        else:
            accion, canal = "Upsell / servicio complementario", "WhatsApp"
            mensaje = MENSAJES["Upsell / servicio complementario"].format(
                nombre=nombre, servicio=servicio or "una revision de mantenimiento")

        # Score de prioridad: riesgo + valor + inactividad
        valor_pct = _percentil(rfm["monto"], monto)
        prioridad = _ponderar(prob, 0.55) + _ponderar(valor_pct, 0.30) + _ponderar(min(recencia / 180, 1.0), 0.15)

        filas.append({
            "cliente_id": r.get("cliente_id"),
            "nombre": nombre,
            "accion": accion,
            "canal": canal,
            "mensaje": mensaje,
            "prioridad": round(prioridad, 3),
            "prob_churn": round(prob, 3),
            "monto": round(monto, 2),
            "recencia_dias": int(recencia),
            "servicio_sugerido": servicio or "",
        })

    df = pd.DataFrame(filas)
    if not df.empty:
        df = df.sort_values("prioridad", ascending=False).head(n)
    return df


def _percentil(series, valor) -> float:
    try:
        return float((series <= valor).mean())
    except Exception:  # noqa: BLE001
        return 0.0


def _ponderar(valor: float, peso: float) -> float:
    """Aporta ``valor * peso`` al score de prioridad de una accion."""
    return float(valor) * float(peso)