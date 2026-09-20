import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, root_mean_squared_error, accuracy_score, f1_score
from sklearn.preprocessing import LabelEncoder
from .data_loader import merge_datasets
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
        self.df = merge_datasets(data)
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

        return {
            "modelo": "Gradient Boosting",
            "evaluacion": evaluacion,
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
                sid = int(det.split(":")[0])
                rows.append({"fecha": df.loc[idx, "fecha"], "servicio_id": sid})
            except (ValueError, KeyError):
                continue

        det_df = pd.DataFrame(rows)
        if det_df.empty:
            return {"modelo": "N/A", "predicciones": pd.DataFrame()}

        nombres = self.data["servicios"].set_index("id")["nombre"].to_dict()
        det_df["servicio"] = det_df["servicio_id"].map(nombres)

        # Serie mensual por servicio
        det_df["anio_mes"] = det_df["fecha"].dt.to_period("M").astype(str)
        serie = det_df.groupby(["servicio", "anio_mes"]).size().reset_index(name="demanda")

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

        features = ["recencia", "frecuencia", "monto", "usuario_activo_dias", "promedio_gasto"]
        X = rfm[features].values
        y = rfm["churn"].values

        if len(np.unique(y)) < 2:
            evaluacion = {"nota": "Datos insuficientes para clasificador"}
            valor_rating = int(np.unique(y)[0])
            rfm["prob_churn"] = valor_rating
            return {"modelo": "Basado en reglas", "evaluacion": evaluacion,
                    "resultados": rfm, "registro": None}

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, random_state=42,
            stratify=y if len(np.unique(y)) > 1 else None)

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
            return pd.DataFrame(columns=["producto", "recomendacion"])

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
            cat_demanda = {
                r["categoria"]: float(r["demanda_mensual"])
                for _, r in demanda_cat.iterrows()}
            for cat, _demanda in cat_demanda.items():
                grupo = inv[inv.get("categoria") == cat]
                if grupo.empty:
                    continue
                pesos = (grupo["stock_minimo"].fillna(0) + 1)
                total = float(pesos.sum()) or 1.0
                for pid, w in zip(grupo["id"], pesos / total):
                    peso_por_producto[str(pid)] = float(w)

        hoy = pd.Timestamp.today()
        resultados = []

        for _, row in inv.iterrows():
            producto_id = str(row["id"])
            stock = float(row.get("stock_actual", 0) or 0)
            stock_min = float(row.get("stock_minimo", 0) or 0)
            venta = row.get("precio_venta", 0) or 0
            costo = row.get("precio_costo", 0) or 0
            categoria = str(row.get("categoria", "") or "")

            # Demanda mensual estimada de ESTE producto
            demanda_mes = 0.0
            if categoria in cat_demanda:
                demanda_mes = cat_demanda[categoria] * peso_por_producto.get(producto_id, 0.0)

            stock_objetivo = stock_min + max(0.0, demanda_mes) * lead_time * factor_seguridad
            meses_cobertura = (stock / demanda_mes) if demanda_mes > 0 else (999 if stock > 0 else 0)
            falta_stock = stock < stock_objetivo
            recomendacion = (
                "Reabastecer" if stock <= stock_min else
                ("Vigilar" if falta_stock else "Suficiente")
            )
            cantidad_recomendada = max(0, int(np.ceil(stock_objetivo - stock)))

            resultados.append({
                "id": producto_id,
                "producto": row["producto"],
                "categoria": str(categoria),
                "stock_actual": stock,
                "stock_minimo": stock_min,
                "demanda_mensual": round(demanda_mes, 2),
                "tasa_rotacion_mensual": round(demanda_mes, 2),
                "stock_objetivo": round(stock_objetivo, 1),
                "meses_cobertura": round(min(meses_cobertura, 999), 1),
                "cantidad_recomendada": cantidad_recomendada,
                "recomendacion": recomendacion,
                "valor_stock": round(stock * costo, 2),
                "margen_unitario": round(venta - costo, 2),
            })

        pred = pd.DataFrame(resultados)
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

        sugerencias = []
        for _, row in recencia.head(15).iterrows():
            if row["dias_sin_visita"] > 120:
                sugerencias.append({
                    "cliente": row["nombre"],
                    "dias_sin_visita": int(row["dias_sin_visita"]),
                    "sugerencia": "Contacto de reactivacion: ofrecer descuento",
                })
            else:
                sugerencias.append({
                    "cliente": row["nombre"],
                    "dias_sin_visita": int(row["dias_sin_visita"]),
                    "sugerencia": "Recordatorio amable de mantenimiento",
                })

        return pd.DataFrame(sugerencias)