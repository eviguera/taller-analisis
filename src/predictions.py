import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, root_mean_squared_error, accuracy_score, f1_score
from sklearn.preprocessing import LabelEncoder
from .data_loader import enriquecer_facturas
from .core.config_manager import cargar_config
from .core.hechos import construir_factura_detalle, demanda_producto_categoria
from .model_registry import ModelRegistry


class Predictor:
    """Modelos de prediccion (ingresos, demanda, churn e inventario).

    Los modelos pesados (churn, ingresos) se persisten en un registry
    (data/models/) para no re-entrenarlos en cada sesion.
    """

    def __init__(self, data, cfg=None):
        self.data = data
        self.cfg = cfg if cfg is not None else cargar_config()
        self.df = enriquecer_facturas(data)
        self.df = self.df[self.df["estado"] != "Cancelada"].copy()

    def _dir_modelos(self) -> str:
        """Directorio de modelos del workspace actual (junto a la base DuckDB)."""
        base = getattr(self.cfg, "db_path", Path("data/almacen.duckdb"))
        return str(Path(base).parent / "models")

    def _hechos(self):
        """Cachea la tabla de hechos factura_detalle una vez por Predictor."""
        if getattr(self, "_hechos_df", None) is None:
            self._hechos_df = construir_factura_detalle(
                self.data.get("facturas", pd.DataFrame()),
                self.data.get("servicios", pd.DataFrame()),
            )
        return self._hechos_df

    def _registro(self) -> ModelRegistry:
        return ModelRegistry(self._dir_modelos())

    def registro_modelos(self) -> list:
        """Catalogo de modelos persistidos (para el panel de modelos)."""
        return self._registro().listar()

    def reentrenar(self, tipo: str):
        """Elimina un modelo persistido para forzar reentrenamiento."""
        self._registro().borrar(tipo)

    def feature_engineering(self, grupo):
        grupo = grupo.copy()
        if "fecha" in grupo.columns:
            grupo["mes"] = grupo["fecha"].dt.month
            grupo["anio"] = grupo["fecha"].dt.year
            grupo["trimestre"] = grupo["fecha"].dt.quarter
            grupo["dia_semana"] = grupo["fecha"].dt.dayofweek
        return grupo

    def predecir_ingresos(self, meses_futuros=6, usar_registro=True):
        """Prediccion de ingresos mensuales usando regresion con lags."""
        df = self.df.copy()
        serie = df.groupby(df["fecha"].dt.to_period("M"))["total"].sum().reset_index()
        serie["anio_mes"] = serie["fecha"].astype(str)
        serie["periodo"] = np.arange(len(serie))
        serie["ingresos"] = serie["total"].astype(float)

        # Crear lags (1, 2, 3 meses atras)
        for lag in [1, 2, 3]:
            serie[f"lag_{lag}"] = serie["ingresos"].shift(lag)

        # Features de tiempo
        serie["mes"] = serie["fecha"].dt.month
        serie["anio"] = serie["fecha"].dt.year

        # Dataset con lags validos
        modelo_df = serie.dropna().copy()
        features = ["mes", "anio", "lag_1", "lag_2", "lag_3"]
        X = modelo_df[features].values
        y = modelo_df["ingresos"].values

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

        def _evaluar(m):
            eva = {}
            if len(X_test) > 0:
                y_pred = m.predict(X_test)
                eva = {
                    "mae": round(mean_absolute_error(y_test, y_pred), 2),
                    "rmse": round(root_mean_squared_error(y_test, y_pred), 2),
                    "mape": round(float(np.mean(np.abs((y_test - y_pred) / y_test)) * 100), 2) if (np.abs(y_test).sum() > 0) else 0,
                }
            return eva

        n_muestras = len(modelo_df)

        # Linea base naive: predecir el promedio historico
        naive_pred = float(modelo_df["ingresos"].mean())
        naive_mae = float(np.mean(np.abs(modelo_df["ingresos"] - naive_pred)))

        registro = None
        if usar_registro:
            reg = self._registro()
            previo, meta = reg.cargar("ingresos")
            if meta and meta.get("n_muestras") == n_muestras and previo is not None:
                modelo = previo
                evaluacion = dict(meta.get("evaluacion", {}))
                evaluacion["fuente"] = "registro"
                registro = meta
            else:
                modelo = GradientBoostingRegressor(n_estimators=200, random_state=42, max_depth=3, learning_rate=0.1)
                modelo.fit(X_train, y_train)
                evaluacion = _evaluar(modelo)
                registro = reg.guardar("ingresos", modelo, {
                    "n_muestras": n_muestras, "evaluacion": evaluacion, "features": features,
                })
        else:
            modelo = GradientBoostingRegressor(n_estimators=200, random_state=42, max_depth=3, learning_rate=0.1)
            modelo.fit(X_train, y_train)
            evaluacion = _evaluar(modelo)

        # Generar predicciones futuras paso a paso (avanzando un mes real por iteracion)
        predicciones = []
        ultimo_mes = int(serie["mes"].iloc[-1])
        ultimo_anio = int(serie["anio"].iloc[-1])
        ultimo_lag = {
            "lag_1": float(modelo_df["lag_1"].iloc[-1]),
            "lag_2": float(modelo_df["lag_2"].iloc[-1]),
            "lag_3": float(modelo_df["lag_3"].iloc[-1]),
        }
        for i in range(1, meses_futuros + 1):
            mes_prox = ultimo_mes + i
            anio_prox = ultimo_anio
            while mes_prox > 12:
                anio_prox += 1
                mes_prox -= 12
            fila = [mes_prox, anio_prox, ultimo_lag["lag_1"], ultimo_lag["lag_2"], ultimo_lag["lag_3"]]
            pred = float(max(0, modelo.predict([fila])[0]))
            predicciones.append({
                "fecha": f"{anio_prox}-{mes_prox:02d}",
                "ingresos_predichos": round(pred, 2),
            })
            ultimo_lag["lag_3"] = ultimo_lag["lag_2"]
            ultimo_lag["lag_2"] = ultimo_lag["lag_1"]
            ultimo_lag["lag_1"] = pred

        # Intervalo de confianza simple: +/- 1 desviacion estandar de los residuos
        residuos = y_train - modelo.predict(X_train)
        std_residuo = float(np.std(residuos)) if len(residuos) > 1 else 0.0

        # Anadir intervalos a las predicciones
        for p in predicciones:
            p["ic_inferior"] = round(max(0, p["ingresos_predichos"] - 1.96 * std_residuo), 2)
            p["ic_superior"] = round(p["ingresos_predichos"] + 1.96 * std_residuo, 2)

        return {
            "modelo": "Gradient Boosting",
            "evaluacion": {**evaluacion, "naive_mae": round(naive_mae, 2)},
            "predicciones": pd.DataFrame(predicciones),
            "historial": serie[["anio_mes", "ingresos"]],
            "registro": registro,
        }

    def predecir_demanda(self, horizonte_meses=6):
        """Prediccion de demanda de servicios."""
        df = self.df.copy()
        detalles = df["detalles"].str.split(";").explode()
        detalles = detalles[detalles.notna() & (detalles != "")]
        if detalles.empty:
            return {"modelo": "N/A", "predicciones": pd.DataFrame()}

        # Contar frecuencia por servicio y mes
        rows = []
        for idx, det in detalles.items():
            try:
                partes = det.split(":")
                sid = int(partes[0])
                cantidad = int(partes[1]) if len(partes) > 1 else 1
                rows.append({"fecha": df.loc[idx, "fecha"], "servicio_id": sid, "cantidad": cantidad})
            except (ValueError, KeyError, IndexError):
                continue

        det_df = pd.DataFrame(rows)
        if det_df.empty:
            return {"modelo": "N/A", "predicciones": pd.DataFrame()}

        nombres = self.data["servicios"].set_index("id")["nombre"].to_dict()
        det_df["servicio"] = det_df["servicio_id"].map(nombres)

        # Serie mensual por servicio
        det_df["anio_mes"] = det_df["fecha"].dt.to_period("M").astype(str)
        serie = det_df.groupby(["servicio", "anio_mes"])["cantidad"].sum().reset_index(name="demanda")

        # Para cada servicio top 8, hacer regresion simple
        top_servicios = det_df["servicio"].value_counts().head(8).index
        predicciones = []
        info = []

        for serv in top_servicios:
            sdf = serie[serie["servicio"] == serv].copy()
            sdf["periodo"] = np.arange(len(sdf))
            if len(sdf) < 5:
                continue
            X = sdf[["periodo"]].values
            y = sdf["demanda"].values
            modelo = LinearRegression()
            modelo.fit(X, y)
            tendencia = modelo.coef_[0]

            ultimo_periodo = sdf["periodo"].iloc[-1]
            ultimo_mes = sdf["anio_mes"].iloc[-1]
            ultimo_anio, ultimo_m_term = ultimo_mes.split("-")
            for i in range(1, horizonte_meses + 1):
                pred_periodo = ultimo_periodo + i
                pred_demanda = modelo.predict([[pred_periodo]])[0]
                anio, mes = int(ultimo_anio), int(ultimo_m_term) + i
                while mes > 12:
                    anio += 1
                    mes -= 12
                predicciones.append({
                    "servicio": serv,
                    "fecha": f"{anio}-{mes:02d}",
                    "demanda_predicha": round(max(0, pred_demanda), 1),
                })
            info.append({"servicio": serv, "tendencia": round(tendencia, 2)})

        return {
            "modelo": "Regresion Lineal",
            "predicciones": pd.DataFrame(predicciones),
            "tendencias": pd.DataFrame(info),
        }

    def predecir_churn(self, usar_registro=True):
        """Prediccion de churn de clientes usando RFM + Random Forest."""
        df = self.df.copy()
        hoy = df["fecha"].max()

        rfm = df.groupby(["cliente_id", "nombre"]).agg(
            recencia=("fecha", lambda x: (hoy - x.max()).days),
            frecuencia=("id", "count"),
            monto=("total", "sum"),
            primer_visita=("fecha", "min"),
            ultima_visita=("fecha", "max"),
        ).reset_index()

        # Definir churn: cliente que no ha visitado en >90 dias (churn potencial)
        rfm["churn"] = (rfm["recencia"] > 90).astype(int)

        # Otras features
        rfm["usuario_activo_dias"] = (hoy - rfm["primer_visita"]).dt.days
        rfm["promedio_gasto"] = rfm["monto"] / rfm["frecuencia"].clip(lower=1)

        features = ["frecuencia", "monto", "usuario_activo_dias", "promedio_gasto"]
        X = rfm[features].values
        y = rfm["churn"].values

        if len(np.unique(y)) < 2:
            evaluacion = {"nota": "Datos insuficientes para clasificador"}
            valor_rating = int(np.unique(y)[0])
            rfm["prob_churn"] = valor_rating
            return {"modelo": "Basado en reglas", "evaluacion": evaluacion,
                    "resultados": rfm, "registro": None}

        # Validacion temporal: shuffle=False. sklearn no permite stratify con
        # shuffle=False, asi que se omite (la clase mayoritaria domina igual).
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, random_state=42, shuffle=False)

        def _aplicar(m):
            return m.predict_proba(X)[:, 1]

        def _metrica(m):
            y_pred = m.predict(X_test)
            importancias = sorted(zip(features, m.feature_importances_), key=lambda x: -x[1])
            return {
                "accuracy": round(accuracy_score(y_test, y_pred), 3),
                "f1": round(f1_score(y_test, y_pred), 3),
                "num_churn_detectado": int(y.sum()),
                "tasa_churn": round(y.mean() * 100, 1),
                "features_importantes": {f: round(v, 3) for f, v in importancias},
            }

        n_muestras = len(X)
        registro = None
        if usar_registro:
            reg = self._registro()
            previo, meta = reg.cargar("churn")
            if previo is not None and meta and meta.get("n_muestras") == n_muestras:
                modelo = previo
                evaluacion = dict(meta.get("evaluacion", {}))
                evaluacion["fuente"] = "registro"
                registro = meta
            else:
                modelo = RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced")
                modelo.fit(X_train, y_train)
                evaluacion = _metrica(modelo)
                registro = reg.guardar("churn", modelo, {
                    "n_muestras": n_muestras, "evaluacion": evaluacion, "features": features,
                })
        else:
            modelo = RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced")
            modelo.fit(X_train, y_train)
            evaluacion = _metrica(modelo)

        rfm["prob_churn"] = _aplicar(modelo)

        return {
            "modelo": "Random Forest",
            "evaluacion": evaluacion,
            "resultados": rfm.sort_values("prob_churn", ascending=False),
            "registro": registro,
        }

    def predecir_inventario(self):
        """Reposicion con demanda real derivada de los servicios vendidos.

        Idea 1: la demanda ya no es una regla inventada. Se estima a partir de
        la tabla de hechos (servicios vendidos por mes) mapeada a la categoria
        de producto mediante ``inventario.mapeo_servicio_categoria``, y se
        distribuye entre los productos de la categoria ponderando por su stock
        minimo. Con eso se calculan rotacion, cobertura y cantidad a pedir.
        """
        inv = self.data.get("inventario", pd.DataFrame()).copy()
        if inv.empty:
            # Mismo esquema que devuelve la rama con datos: la pagina de
            # Predicciones selecciona 10 de estas columnas y con un frame de
            # dos columnas crasheaba (KeyError) en cualquier workspace sin
            # inventario.
            return pd.DataFrame(columns=[
                "id", "producto", "categoria", "stock_actual", "stock_minimo",
                "demanda_mensual", "tasa_rotacion_mensual", "stock_objetivo",
                "meses_cobertura", "cantidad_recomendada", "recomendacion",
                "valor_stock", "margen_unitario", "fecha_recomendada",
            ])

        hechos = self._hechos()
        inv_cfg = (self.cfg.inventario or {}) or {}
        horizonte = int(inv_cfg.get("horizonte_meses", 3))
        lead_time = float(inv_cfg.get("lead_time_meses", 1.5))
        factor_seguridad = float(inv_cfg.get("factor_seguridad", 1.2))
        mapeo = inv_cfg.get("mapeo_servicio_categoria", {}) or {}

        demanda_cat = demanda_producto_categoria(
            hechos, mapeo, horizonte_meses=horizonte)

        # Demanda por producto: repartir la demanda de la categoria ponderando
        # por stock minimo (los productos con mayor stock minimo rotan mas).
        cat_demanda = {}
        peso_por_producto = {}
        if not demanda_cat.empty:
            cat_demanda = demanda_cat.set_index("categoria")["demanda_mensual"].astype(float).to_dict()
            for cat, _demanda in cat_demanda.items():
                grupo = inv[inv.get("categoria") == cat]
                if grupo.empty:
                    continue
                pesos = (grupo["stock_minimo"].fillna(0) + 1)
                total = float(pesos.sum()) or 1.0
                for pid, w in zip(grupo["id"], pesos / total):
                    peso_por_producto[str(pid)] = float(w)

        hoy = pd.Timestamp.today()

        inv["_stock"] = inv["stock_actual"].fillna(0).astype(float)
        inv["_stock_min"] = inv["stock_minimo"].fillna(0).astype(float)
        inv["_venta"] = inv["precio_venta"].fillna(0).astype(float)
        inv["_costo"] = inv["precio_costo"].fillna(0).astype(float)
        inv["_categoria"] = inv["categoria"].fillna("").astype(str)
        inv["_id"] = inv["id"].astype(str)

        # Demanda mensual estimada de ESTE producto
        inv["_demanda_mes"] = 0.0
        for cat, demanda in cat_demanda.items():
            mask = inv["_categoria"] == cat
            inv.loc[mask, "_demanda_mes"] = demanda * inv.loc[mask, "_id"].map(peso_por_producto).fillna(0.0)

        inv["_stock_objetivo"] = inv["_stock_min"] + inv["_demanda_mes"].clip(lower=0) * lead_time * factor_seguridad
        inv["_meses_cobertura"] = np.where(
            inv["_demanda_mes"] > 0,
            inv["_stock"] / inv["_demanda_mes"],
            np.where(inv["_stock"] > 0, 999, 0)
        )
        inv["_falta_stock"] = inv["_stock"] < inv["_stock_objetivo"]
        inv["_recomendacion"] = np.where(
            inv["_stock"] <= inv["_stock_min"],
            "Reabastecer",
            np.where(inv["_falta_stock"], "Vigilar", "Suficiente")
        )
        inv["_cantidad_recomendada"] = (inv["_stock_objetivo"] - inv["_stock"]).clip(lower=0).apply(np.ceil).astype(int)

        pred = pd.DataFrame({
            "id": inv["_id"],
            "producto": inv["producto"],
            "categoria": inv["_categoria"],
            "stock_actual": inv["_stock"],
            "stock_minimo": inv["_stock_min"],
            "demanda_mensual": inv["_demanda_mes"].round(2),
            "tasa_rotacion_mensual": inv["_demanda_mes"].round(2),
            "stock_objetivo": inv["_stock_objetivo"].round(1),
            "meses_cobertura": inv["_meses_cobertura"].clip(upper=999).round(1),
            "cantidad_recomendada": inv["_cantidad_recomendada"],
            "recomendacion": inv["_recomendacion"],
            "valor_stock": (inv["_stock"] * inv["_costo"]).round(2),
            "margen_unitario": (inv["_venta"] - inv["_costo"]).round(2),
        })
        pred["fecha_recomendada"] = hoy.strftime("%Y-%m-%d")
        orden = {"Reabastecer": 0, "Vigilar": 1, "Suficiente": 2}
        return pred.sort_values(
            "recomendacion", key=lambda s: s.map(orden))

    def proxima_factura_demanda(self):
        """Recomendaciones de servicios para proxima visita sugerida."""
        df = self.df.copy()
        hoy = df["fecha"].max()

        # Recencia por cliente y ultimo servicio
        recencia = df.groupby(["cliente_id", "nombre"], as_index=False).agg(
            ultima_visita=("fecha", "max"),
            dias_sin_visita=("fecha", lambda x: (hoy - x.max()).days),
        ).sort_values("dias_sin_visita", ascending=False)

        top15 = recencia.head(15).copy()
        top15["sugerencia"] = np.where(
            top15["dias_sin_visita"] > 120,
            "Contacto de reactivacion: ofrecer descuento",
            "Recordatorio amable de mantenimiento"
        )
        return top15[["nombre", "dias_sin_visita", "sugerencia"]].rename(
            columns={"nombre": "cliente"}
        ).reset_index(drop=True)