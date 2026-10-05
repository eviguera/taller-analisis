import pandas as pd
import numpy as np
from .data_loader import enriquecer_facturas


class Analyzer:
    """Analisis exploratorio de los datos del negocio (demo: taller mecanico)."""

    def __init__(self, data):
        self.data = data
        self.df = enriquecer_facturas(data)
        self.df = self.df[self.df["estado"] != "Cancelada"].copy()

    def kpis_globales(self):
        facturas = self.df
        return {
            "total_ingresos": round(facturas["total"].sum(), 2),
            "total_facturas": len(facturas),
            "ticket_promedio": round(facturas["total"].mean(), 2) if len(facturas) else 0,
            "clientes_activos": facturas["cliente_id"].nunique(),
            "vehiculos_atendidos": facturas["vehiculo_id"].nunique(),
            "servicios_unicos": (
                facturas["detalles"].str.split(";").explode().str.split(":").str[0].nunique()
                if "detalles" in facturas else 0
            ),
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
        # sin copy: groupby no muta el frame y el copy de 1M filas cuesta
        df = self.df
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
        df = self.df
        servicios = df["detalles"].str.split(";").explode()
        servicios = servicios[servicios.notna() & (servicios != "")]
        base = servicios.str.split(":").str[0]
        # Ruta rapida: astype directo (como siempre). Si hay un id que no
        # es entero, en vez de tumbar el panel se cae al coercer con
        # to_numeric y se descartan los que no se pudieron convertir.
        try:
            ids = base.astype("int64")
        except (TypeError, ValueError):
            ids = pd.to_numeric(base, errors="coerce").dropna().astype("int64")
        # value_counts ya devuelve ordenado por frecuencia descendente.
        contador = ids.value_counts().reset_index()
        contador.columns = ["servicio_id", "frecuencia"]
        if "servicios" in self.data:
            mapa_nombres = self.data["servicios"].set_index("id")["nombre"].to_dict()
            contador["servicio"] = contador["servicio_id"].map(mapa_nombres).fillna(contador["servicio_id"])
        contador = contador.head(15)
        return contador[["servicio", "frecuencia"]]

    def clientes_top(self, n=10):
        # sin copy: groupby.agg no muta self.df
        agrupado = self.df.groupby(["cliente_id", "nombre"]).agg(
            facturas=("id", "count"),
            total_gastado=("total", "sum"),
            ultima_visita=("fecha", "max"),
        ).sort_values("total_gastado", ascending=False).head(n).reset_index()
        return agrupado

    def clientes_rfm(self):
        hoy = self.df["fecha"].max()
        # Sin lambdas en el agg: el max por grupo en Python escala mal con
        # datasets grandes; con named agg va al motor. pop() entrega la
        # columna y la quita, para no cambiar el esquema que devuelvo.
        rfm = self.df.groupby(["cliente_id", "nombre"]).agg(
            ultima_visita=("fecha", "max"),
            frecuencia=("id", "count"),
            monto=("total", "sum"),
        ).reset_index()
        rfm["recencia_dias"] = (hoy - rfm.pop("ultima_visita")).dt.days
        # mismo esquema y mismo orden de columnas que la version con lambda
        rfm = rfm[["cliente_id", "nombre", "recencia_dias", "frecuencia", "monto"]]

        # Cuantiles para calificar. La recencia va al reves de F y M: pocos
        # dias sin comprar es lo bueno, asi que el cuantil mas bajo de
        # recencia_dias recibe la mejor calificacion (4). El rank garantiza
        # cuantiles distintos aunque haya empates.
        try:
            rfm["R"] = pd.qcut(rfm["recencia_dias"].rank(method="first"), 4,
                               labels=[4, 3, 2, 1], duplicates="drop").astype(int)
            rfm["F"] = pd.qcut(rfm["frecuencia"].rank(method="first"), 4,
                               labels=[1, 2, 3, 4], duplicates="drop").astype(int)
            rfm["M"] = pd.qcut(rfm["monto"].rank(method="first"), 4,
                               labels=[1, 2, 3, 4], duplicates="drop").astype(int)
        except Exception as e:
            import logging
            logging.getLogger("taller.analyzer").warning("Error en RFM: %s", e)
            # Sin cuantiles no hay senal: se marca como no calificado en vez
            # de inventar un 3 constante que pareceria "promedio real".
            rfm["R"] = 0
            rfm["F"] = 0
            rfm["M"] = 0

        rfm["rfm_score"] = rfm["R"].astype(int) + rfm["F"].astype(int) + rfm["M"].astype(int)

        # np.select con las mismas condiciones y en el mismo orden que la
        # cadena de if: vectorizado, sin recorrer fila a fila en Python.
        r = rfm["R"].astype(int)
        f = rfm["F"].astype(int)
        m = rfm["M"].astype(int)
        rfm["segmento"] = np.select(
            [
                (r >= 4) & (f >= 4),
                (r >= 4) & (f >= 3),
                (m >= 4) & (f >= 3),
                (r <= 2) & (f <= 2),
                r <= 2,
                (r >= 3) & (f >= 2),
            ],
            ["Campeones", "Cliente Leal", "Alto Valor", "En Riesgo", "Perdido", "Activo"],
            default="Promedio",
        )
        return rfm.sort_values("rfm_score", ascending=False)

    def estacionalidad(self):
        """Analiza por mes, trimestre y dia de semana."""
        df = self.df
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
        # np.select en vez de apply(axis=1): una condicion por fila en
        # Python no escala con el inventario de un cliente grande.
        inv["estado_stock"] = np.select(
            [inv["stock_actual"] <= inv["stock_minimo"],
             inv["stock_actual"] <= inv["stock_minimo"] * 1.5],
            ["Bajo", "Medio"],
            default="Optimo",
        )
        return inv

    def frecuencia_visitas_clientes(self):
        # diff() por grupo en el motor, no un sort_values() por lambda:
        # el promedio de dias entre visitas es igual, pero sin recorrer
        # cada cliente en Python.
        orden = self.df[["nombre", "fecha", "id"]].sort_values(["nombre", "fecha"])
        orden = orden.assign(dias=orden.groupby("nombre")["fecha"].diff().dt.days)
        return orden.groupby("nombre").agg(
            facturas=("id", "count"),
            promedio_dias_entre_visitas=("dias", "mean"),
        ).sort_values("facturas", ascending=False).reset_index()

    def detalle_servicios(self):
        nombres = self.data["servicios"].set_index("id")["nombre"].to_dict()
        # Un solo copy y sin apply(isinstance): .str.split deja NaN en lo que
        # no es texto y la mascara de ":" de mas abajo ya lo descarta, asi
        # que el filtro fila a fila en Python sobraba.
        df = self.df.copy()
        if df.empty:
            return pd.DataFrame()
        df["detalle_list"] = df["detalles"].str.split(";")
        df = df.explode("detalle_list")
        df = df[df["detalle_list"].str.contains(":", na=False)].copy()
        if df.empty:
            return pd.DataFrame()
        split = df["detalle_list"].str.split(":", expand=True)
        df["servicio_id"] = pd.to_numeric(split[0], errors="coerce")
        df["cantidad"] = pd.to_numeric(split[1], errors="coerce")
        df["subtotal"] = pd.to_numeric(split[2], errors="coerce")
        df = df.dropna(subset=["servicio_id", "cantidad", "subtotal"])
        df["servicio_id"] = df["servicio_id"].astype(int)
        df["servicio"] = df["servicio_id"].map(nombres).fillna(df["servicio_id"].astype(str))
        precios = self.data["servicios"].set_index("id")["precio_base"].to_dict()
        df["precio_unitario"] = df["servicio_id"].map(precios).fillna(0)
        return df[["id", "fecha", "nombre", "servicio_id", "servicio", "precio_unitario", "cantidad", "subtotal"]].rename(
            columns={"id": "factura_id", "nombre": "cliente"}
        ).reset_index(drop=True)

    def correlaciones(self):
        """Correlaciones entre variables relevantes."""
        # astype(float) ya devuelve un frame nuevo: el copy sobraba.
        df = self.df[["total", "descuento", "antiguedad_cliente_dias", "anio"]].astype(float)
        return df.corr().round(3)