import pandas as pd
import numpy as np
from .data_loader import merge_datasets


class Analyzer:
    """Analisis exploratorio de los datos del negocio (demo: taller mecanico)."""

    def __init__(self, data):
        self.data = data
        self.df = merge_datasets(data)
        self.df = self.df[self.df["estado"] != "Cancelada"].copy()

    def kpis_globales(self):
        facturas = self.df
        return {
            "total_ingresos": round(facturas["total"].sum(), 2),
            "total_facturas": len(facturas),
            "ticket_promedio": round(facturas["total"].mean(), 2) if len(facturas) else 0,
            "clientes_activos": facturas["cliente_id"].nunique(),
            "vehiculos_atendidos": facturas["vehiculo_id"].nunique(),
            "servicios_unicos": facturas["detalles"].str.split(";").explode().nunique() if "detalles" in facturas else 0,
            "descuentos_total": round(facturas["descuento"].sum(), 2),
            "valor_cliente_promedio": round(facturas.groupby("cliente_id")["total"].sum().mean(), 2),
        }

    def ingresos_por_mes(self):
        df = self.df.copy()
        df["anio_mes"] = df["fecha"].dt.to_period("M")
        series = df.groupby("anio_mes")["total"].sum().reset_index()
        series["anio_mes"] = series["anio_mes"].astype(str)
        series["acumulado"] = series["total"].cumsum()
        return series

    def ingresos_por_marca(self):
        df = self.df.copy()
        agrupado = df.groupby("marca").agg(
            ingresos=("total", "sum"),
            facturas=("id", "count"),
            promedio=("total", "mean"),
        ).sort_values("ingresos", ascending=False).reset_index()
        return agrupado

    def ingresos_por_vehiculo(self, n=50):
        """Ingresos generados por cada vehiculo (total, visitas y ultima visita).

        Devuelve hasta `n` vehiculos ordenados por ingreso descendente.
        """
        df = self.df
        if "vehiculo_id" not in df.columns or "total" not in df.columns:
            return pd.DataFrame()
        agg = df.groupby("vehiculo_id").agg(
            facturas=("id", "count"),
            ingresos=("total", "sum"),
            ultima_visita=("fecha", "max"),
        ).reset_index()
        veh_cols = ["marca", "modelo", "placa", "anio", "color", "kilometraje"]
        presentes = [c for c in veh_cols if c in df.columns]
        if presentes:
            dim = df[["vehiculo_id"] + presentes].drop_duplicates("vehiculo_id", keep="first")
            agg = agg.merge(dim, on="vehiculo_id", how="left")
        agg = agg.sort_values(["ingresos", "facturas"], ascending=False)
        return agg.head(n) if n else agg

    def servicios_mas_solicitados(self):
        if "detalles" not in self.df:
            return pd.DataFrame()
        df = self.df.copy()
        servicios = df["detalles"].str.split(";").explode()
        servicios = servicios[servicios.notna() & (servicios != "")]
        ids = servicios.str.split(":").str[0]
        contador = ids.astype(int).value_counts().reset_index()
        contador.columns = ["servicio_id", "frecuencia"]
        contador = contador.sort_values("frecuencia", ascending=False)
        if "servicios" in self.data:
            mapa_nombres = self.data["servicios"].set_index("id")["nombre"].to_dict()
            contador["servicio"] = contador["servicio_id"].map(mapa_nombres).fillna(contador["servicio_id"])
        contador = contador.head(15)
        return contador[["servicio", "frecuencia"]]

    def clientes_top(self, n=10):
        df = self.df.copy()
        agrupado = df.groupby(["cliente_id", "nombre"]).agg(
            facturas=("id", "count"),
            total_gastado=("total", "sum"),
            ultima_visita=("fecha", "max"),
        ).sort_values("total_gastado", ascending=False).head(n).reset_index()
        return agrupado

    def clientes_rfm(self):
        hoy = self.df["fecha"].max()
        df = self.df.copy()
        rfm = df.groupby(["cliente_id", "nombre"]).agg(
            recencia_dias=("fecha", lambda x: (hoy - x.max()).days),
            frecuencia=("id", "count"),
            monto=("total", "sum"),
        ).reset_index()

        # Cuantiles para calificar
        try:
            rfm["R"] = pd.qcut(rfm["recencia_dias"], 4, labels=[1, 2, 3, 4]).astype(int)
            rfm["F"] = pd.qcut(rfm["frecuencia"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
            rfm["M"] = pd.qcut(rfm["monto"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
        except Exception:
            rfm["R"] = 1
            rfm["F"] = 1
            rfm["M"] = 1

        rfm["rfm_score"] = rfm["R"].astype(int) + rfm["F"].astype(int) + rfm["M"].astype(int)

        def segmentar(row):
            r, f, m = int(row["R"]), int(row["F"]), int(row["M"])
            if r >= 4 and f >= 4:
                return "Campeones"
            if r >= 4 and f >= 3:
                return "Cliente Leal"
            if m >= 4 and f >= 3:
                return "Alto Valor"
            if r <= 2 and f <= 2:
                return "En Riesgo"
            if r <= 2:
                return "Perdido"
            if r >= 3 and f >= 2:
                return "Activo"
            return "Promedio"

        rfm["segmento"] = rfm.apply(segmentar, axis=1)
        return rfm.sort_values("rfm_score", ascending=False)

    def estacionalidad(self):
        """Analiza por mes, trimestre y dia de semana."""
        df = self.df.copy()
        por_mes = df.groupby(df["fecha"].dt.month)["total"].agg(["sum", "count"]).reindex(
            range(1, 13), fill_value=0).reset_index()
        por_mes.columns = ["mes", "ingresos", "facturas"]

        por_mes_dia = df.groupby(df["fecha"].dt.day_name())["total"].sum().reindex(
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        ).fillna(0).reset_index()
        por_mes_dia.columns = ["dia_semana", "ingresos"]

        return {"por_mes": por_mes, "por_dia_semana": por_mes_dia}

    def inventario_data(self):
        inv = self.data["inventario"].copy()
        inv["valor_inventario"] = inv["stock_actual"] * inv["precio_costo"]
        inv["margen"] = inv["precio_venta"] - inv["precio_costo"]
        inv["margen_pct"] = (inv["margen"] / inv["precio_costo"] * 100).round(1)
        inv["estado_stock"] = inv.apply(
            lambda r: "Bajo" if r["stock_actual"] <= r["stock_minimo"] else
                      "Medio" if r["stock_actual"] <= r["stock_minimo"] * 1.5 else "Optimo",
            axis=1
        )
        return inv

    def frecuencia_visitas_clientes(self):
        df = self.df.copy()
        return df.groupby("nombre").agg(
            facturas=("id", "count"),
            promedio_dias_entre_visitas=("fecha", lambda x: x.sort_values().diff().dt.days.mean()),
        ).sort_values("facturas", ascending=False).reset_index()

    def detalle_servicios(self):
        nombres = self.data["servicios"].set_index("id")["nombre"].to_dict()
        rows = []
        for _, factura in self.df.iterrows():
            if not isinstance(factura["detalles"], str):
                continue
            for det in factura["detalles"].split(";"):
                try:
                    sid, cantidad, subtotal = det.split(":")
                    filas = self.data["servicios"]
                    precio_unitario = filas.loc[filas["id"] == int(sid), "precio_base"].values[0] if len(filas.loc[filas["id"] == int(sid)]) else 0
                    rows.append({
                        "factura_id": factura["id"],
                        "fecha": factura["fecha"],
                        "cliente": factura["nombre"],
                        "servicio_id": int(sid),
                        "servicio": nombres.get(int(sid), sid),
                        "cantidad": int(cantidad),
                        "subtotal": float(subtotal),
                    })
                except (ValueError, IndexError):
                    continue
        return pd.DataFrame(rows)

    def correlaciones(self):
        """Correlaciones entre variables relevantes."""
        df = self.df[["total", "descuento", "antiguedad_cliente_dias", "anio"]].copy()
        df = df.astype(float)
        return df.corr().round(3)