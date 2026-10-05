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

from .core.config import umbral_churn as umbral_churn_cfg
from .core.hechos import construir_factura_detalle
from .predictions import Predictor

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

    # Vectorizar: cross-join entre vehiculos e intervalos
    vehiculos = vehiculos.copy()
    vehiculos["_km"] = vehiculos["kilometraje"].fillna(0).astype(float)
    vehiculos["_edad"] = vehiculos["anio"].apply(lambda a: _edad_vehiculo_anios(a, hoy))
    vehiculos["_ultima"] = vehiculos["id"].map(ultima_visita)
    vehiculos["_meses_ultima"] = vehiculos["_ultima"].apply(lambda f: _meses_desde(f, hoy) if pd.notna(f) else 999)

    # Cliente por vehiculo
    if "cliente_id" in vehiculos.columns and "clientes" in data:
        cli = data["clientes"]
        cli_map = cli.set_index("id")["nombre"].to_dict()
        vehiculos["_cliente"] = vehiculos["cliente_id"].map(cli_map).fillna("")
    else:
        vehiculos["_cliente"] = ""

    # Cross-join con intervalos
    intervalos_df = pd.DataFrame({"servicio": list(intervalos.keys()), "intervalo": list(intervalos.values())})
    cross = vehiculos.merge(intervalos_df, how="cross")

    # Calcular meses_desde_serv vectorizado
    if not hechos.empty:
        hechos_serv = hechos.copy()
        hechos_serv["_servicio_lower"] = hechos_serv["servicio"].astype(str).str.lower()
        # Para cada servicio en intervalos, buscar coincidencias
        meses_desde_list = []
        for servicio in intervalos.keys():
            mask = hechos_serv["_servicio_lower"].str.contains(servicio, na=False)
            if mask.any():
                filas_s = hechos_serv[mask]
                max_por_vehiculo = filas_s.groupby("vehiculo_id")["fecha"].max()
                meses_desde_list.append(max_por_vehiculo.rename(servicio))
        if meses_desde_list:
            meses_desde_df = pd.concat(meses_desde_list, axis=1)
            meses_desde_df = meses_desde_df.reset_index().rename(columns={"index": "vehiculo_id"})
            cross = cross.merge(meses_desde_df, left_on="id", right_on="vehiculo_id", how="left")
            for servicio in intervalos.keys():
                if servicio in cross.columns:
                    cross[f"_meses_{servicio}"] = cross[servicio].apply(lambda f: _meses_desde(f, hoy) if pd.notna(f) else 999)
                else:
                    cross[f"_meses_{servicio}"] = 999
        else:
            for servicio in intervalos.keys():
                cross[f"_meses_{servicio}"] = 999
    else:
        for servicio in intervalos.keys():
            cross[f"_meses_{servicio}"] = 999

    # Calcular candidatos vectorizados usando melt para evitar apply(axis=1)
    meses_cols = [f"_meses_{s}" for s in intervalos.keys()]
    cross_melted = cross.melt(
        id_vars=["id", "intervalo", "servicio", "_km", "_edad", "_meses_ultima", "_cliente", "marca", "modelo", "anio", "placa"],
        value_vars=meses_cols,
        var_name="_servicio_var",
        value_name="_meses_desde_serv"
    )
    cross_melted["_servicio_cross"] = cross_melted["_servicio_var"].str.replace("_meses_", "", regex=False)
    cross_melted = cross_melted[cross_melted["_servicio_cross"] == cross_melted["servicio"]].copy()
    cross_melted["_pendiente"] = cross_melted["intervalo"] - cross_melted["_meses_desde_serv"]

    # Filtrar candidatos
    vencido_mask = cross_melted["_meses_desde_serv"] >= cross_melted["intervalo"]
    proximo_mask = (cross_melted["_meses_desde_serv"] < cross_melted["intervalo"]) & (cross_melted["_pendiente"] >= 0) & (cross_melted["_pendiente"] <= 2)
    cross_melted = cross_melted[vencido_mask | proximo_mask].copy()

    # Calcular urgencia
    cross_melted["_urgencia"] = np.where(
        cross_melted["_meses_desde_serv"] >= cross_melted["intervalo"],
        np.minimum(cross_melted["_pendiente"], 0) / cross_melted["intervalo"],
        cross_melted["_pendiente"] / cross_melted["intervalo"]
    )
    cross_melted["_nota"] = np.where(cross_melted["_meses_desde_serv"] >= cross_melted["intervalo"], "vencido", "proximo")
    cross_melted["_servicio_title"] = cross_melted["servicio"].str.title()

    # Ordenar por urgencia y tomar top N por vehiculo
    cross_melted = cross_melted.sort_values("_urgencia")
    top = cross_melted.groupby("id").head(pendientes_considerar)

    # Construir resultado
    if not top.empty:
        primero = top.groupby("id").first().reset_index()
        df = pd.DataFrame({
            "vehiculo_id": primero["id"],
            "cliente": primero["_cliente"].replace("", "—"),
            "marca": primero.get("marca", ""),
            "modelo": primero.get("modelo", ""),
            "anio": primero.get("anio", ""),
            "placa": primero.get("placa", ""),
            "kilometraje": primero["_km"],
            "edad_anios": primero["_edad"].round(1),
            "dias_sin_visita": (primero["_meses_ultima"].clip(lower=0) * 30).astype(int),
            "servicio_sugerido": primero["_servicio_title"],
            "nota": primero["_nota"],
            "meses_estimados": primero["_meses_desde_serv"].round(1),
            "intervalo_meses": primero["intervalo"],
        })
        # Calcular prioridad vectorizada
        df["_vencido_leve"] = (df["nota"] == "vencido") & (df["meses_estimados"] < df["intervalo_meses"] * 1.5)
        df["_vencido_muy"] = (df["nota"] == "vencido") & (df["meses_estimados"] >= df["intervalo_meses"] * 1.5)
        df["_km_alto"] = df["kilometraje"] >= 80000
        df["_edad_alta"] = df["edad_anios"] >= 10
        df["_km_muy_alto"] = df["kilometraje"] >= 150000
        df["_edad_muy_alta"] = df["edad_anios"] >= 15
        df["prioridad"] = 3 + df["_vencido_leve"].astype(int) + df["_vencido_muy"].astype(int) * 2 + df["_km_alto"].astype(int) + df["_edad_alta"].astype(int) + df["_km_muy_alto"].astype(int) + df["_edad_muy_alta"].astype(int)
        df["prioridad"] = df["prioridad"].clip(upper=5)
        df = df.drop(columns=["_vencido_leve", "_vencido_muy", "_km_alto", "_edad_alta", "_km_muy_alto", "_edad_muy_alta"])
        df = df.sort_values("prioridad", ascending=False)
    else:
        df = pd.DataFrame()
    return df


def next_best_action(data, cfg, n=25, predictor=None) -> pd.DataFrame:
    """Siguiente mejor accion por cliente (reactivar, recordar, upsell, fidelidad).

    Cruza el churn (ejecutado desde el registry si esta fresco) con la
    segmentacion RFM y el mantenimiento predictivo por vehiculo.

    ``predictor`` opcional: reutiliza el que cachea ``obtener_estado()`` en
    vez de instanciar otro y reentrenar el churn en cada rerun.
    """
    predictor_contexto = predictor if predictor is not None else Predictor(data, cfg=cfg)
    churn = predictor_contexto.predecir_churn()
    rfm = churn["resultados"].copy() if not churn["resultados"].empty else pd.DataFrame()
    if rfm.empty:
        return pd.DataFrame()

    progs = proximo_servicio(data, cfg)
    servicio_por_cliente = {}
    if not progs.empty:
        top = progs.drop_duplicates("cliente", keep="first") if "cliente" in progs else progs
        servicio_por_cliente = dict(zip(top["cliente"], top["servicio_sugerido"]))

    umbral_churn = umbral_churn_cfg(cfg.alertas)
    hoy = pd.Timestamp.today()

    # Vectorizar next_best_action
    rfm = rfm.copy()
    rfm["_nombre"] = rfm["nombre"].astype(str)
    rfm["_prob"] = rfm["prob_churn"].fillna(0).astype(float)
    rfm["_monto"] = rfm["monto"].fillna(0).astype(float)
    rfm["_recencia"] = rfm["recencia"].fillna(0).astype(float)

    # Servicio por cliente (vectorizado con map)
    rfm["_servicio"] = rfm["cliente_id"].map(servicio_por_cliente).fillna("")
    mask_serv = rfm["_servicio"] == ""
    rfm.loc[mask_serv, "_servicio"] = rfm.loc[mask_serv, "_nombre"].map(servicio_por_cliente).fillna("")
    mask_serv = rfm["_servicio"] == ""
    rfm.loc[mask_serv, "_servicio"] = rfm.loc[mask_serv, "_nombre"].astype(str).map(servicio_por_cliente).fillna("")

    # Determinar acción y canal (vectorizado con np.where)
    monto_p80 = float(rfm["_monto"].quantile(0.8)) if len(rfm) else 0.0
    rfm["_accion"] = np.where(
        rfm["_prob"] >= umbral_churn,
        "Reactivar",
        np.where(
            rfm["_servicio"] != "",
            "Recordatorio preventivo",
            np.where(
                rfm["_monto"] >= monto_p80,
                "Fidelidad",
                "Upsell / servicio complementario"
            )
        )
    )
    rfm["_canal"] = np.where(
        rfm["_prob"] >= umbral_churn,
        "WhatsApp",
        np.where(
            rfm["_servicio"] != "",
            "Email",
            np.where(
                rfm["_monto"] >= monto_p80,
                "Email",
                "WhatsApp"
            )
        )
    )

    # Mensajes fila por fila (cada cliente necesita su propio formato)
    def _formatear_mensaje(row):
        if row["_accion"] == "Reactivar":
            return MENSAJES["Reactivar"].format(nombre=row["_nombre"])
        elif row["_accion"] == "Recordatorio preventivo":
            return MENSAJES["Recordatorio preventivo"].format(
                nombre=row["_nombre"], vehiculo=row["_servicio"])
        elif row["_accion"] == "Fidelidad":
            return MENSAJES["Fidelidad"].format(nombre=row["_nombre"])
        else:
            return MENSAJES["Upsell / servicio complementario"].format(
                nombre=row["_nombre"],
                servicio=row["_servicio"] or "una revision de mantenimiento")

    rfm["_mensaje"] = rfm.apply(_formatear_mensaje, axis=1)

    # Prioridad vectorizada
    rfm["_valor_pct"] = rfm["_monto"].apply(lambda m: _percentil(rfm["_monto"], m))
    rfm["_prioridad"] = (
        _ponderar(rfm["_prob"], 0.55) +
        _ponderar(rfm["_valor_pct"], 0.30) +
        _ponderar((rfm["_recencia"] / 180).clip(upper=1.0), 0.15)
    )

    df = pd.DataFrame({
        "cliente_id": rfm["cliente_id"],
        "nombre": rfm["_nombre"],
        "accion": rfm["_accion"],
        "canal": rfm["_canal"],
        "mensaje": rfm["_mensaje"],
        "prioridad": rfm["_prioridad"].round(3),
        "prob_churn": rfm["_prob"].round(3),
        "monto": rfm["_monto"].round(2),
        "recencia_dias": rfm["_recencia"].astype(int),
        "servicio_sugerido": rfm["_servicio"],
    })
    if not df.empty:
        df = df.sort_values("prioridad", ascending=False).head(n)
    return df


def _percentil(series, valor) -> float:
    try:
        return float((series <= valor).mean())
    except Exception:  # noqa: BLE001
        return 0.0


def _ponderar(valor, peso: float):
    """Aporta ``valor * peso`` al score de prioridad. Acepta escalar o Serie."""
    return valor * float(peso)