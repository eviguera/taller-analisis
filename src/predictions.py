import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, root_mean_squared_error, accuracy_score, f1_score
from sklearn.preprocessing import LabelEncoder
from .data_loader import merge_datasets


class Predictor:
    """Modelos de prediccion para el taller mecanico."""

    def __init__(self, data):
        self.data = data
        self.df = merge_datasets(data)
        self.df = self.df[self.df["estado"] != "Cancelada"].copy()

    def feature_engineering(self, grupo):
        grupo = grupo.copy()
        if "fecha" in grupo.columns:
            grupo["mes"] = grupo["fecha"].dt.month
            grupo["anio"] = grupo["fecha"].dt.year
            grupo["trimestre"] = grupo["fecha"].dt.quarter
            grupo["dia_semana"] = grupo["fecha"].dt.dayofweek
        return grupo

    def predecir_ingresos(self, meses_futuros=6):
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

        modelo = GradientBoostingRegressor(n_estimators=200, random_state=42, max_depth=3, learning_rate=0.1)
        modelo.fit(X_train, y_train)

        evaluacion = {}
        if len(X_test) > 0:
            y_pred = modelo.predict(X_test)
            evaluacion = {
                "mae": round(mean_absolute_error(y_test, y_pred), 2),
                "rmse": round(root_mean_squared_error(y_test, y_pred), 2),
                "mape": round(float(np.mean(np.abs((y_test - y_pred) / y_test)) * 100), 2) if (np.abs(y_test).sum() > 0) else 0,
            }

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

    def predecir_churn(self):
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
            return {"modelo": "Basado en reglas", "evaluacion": evaluacion, "resultados": rfm}

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y if len(np.unique(y)) > 1 else None)

        modelo = RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced")
        modelo.fit(X_train, y_train)

        y_pred = modelo.predict(X_test)
        y_proba = modelo.predict_proba(X)

        evaluacion = {
            "accuracy": round(accuracy_score(y_test, y_pred), 3),
            "f1": round(f1_score(y_test, y_pred), 3),
            "num_churn_detectado": int(y.sum()),
            "tasa_churn": round(y.mean() * 100, 1),
        }

        rfm["prob_churn"] = y_proba[:, 1]

        importancias = sorted(zip(features, modelo.feature_importances_), key=lambda x: -x[1])
        evaluacion["features_importantes"] = {f: round(v, 3) for f, v in importancias}

        return {
            "modelo": "Random Forest",
            "evaluacion": evaluacion,
            "resultados": rfm.sort_values("prob_churn", ascending=False),
        }

    def predecir_inventario(self):
        """Prediccion de rotacion y reaprovisionamiento de inventario."""
        inv = self.data["inventario"].copy()

        # Demanda estimada por producto en base a facturas
        facturas = self.df.copy()
        resultados = []
        for _, row in inv.iterrows():
            producto_id = row["id"]
            stock = row["stock_actual"]
            stock_min = row["stock_minimo"]
            venta = row["precio_venta"]
            costo = row["precio_costo"]

            # Buscar si el producto aparece en detalles de facturas
            demanda = 0
            for det in facturas["detalles"].dropna():
                # Los detalles son IDs de servicios, no de productos;
                # estimamos demanda via una regla proporcional al stock/min_stock
                pass

            # Regla simple: estimacion basada en rotacion implicita
            falta_datos = stock <= 0
            tasa_rotacion = np.clip((stock_min + 2) / max(stock, 1), 0.1, 3.0)
            demanda_estimada_mes = tasa_rotacion if stock > 0 else 0

            meses_cobertura = stock / demanda_estimada_mes if demanda_estimada_mes > 0 else 0
            dias_problema = (stock - stock_min) / demanda_estimada_mes if demanda_estimada_mes > 0 else 999

            recomendacion = "Reabastecer" if stock <= stock_min else (
                "Vigilar" if stock <= stock_min * 1.5 else "Suficiente"
            )

            resultados.append({
                "id": producto_id,
                "producto": row["producto"],
                "categoria": row["categoria"],
                "stock_actual": stock,
                "stock_minimo": stock_min,
                "tasa_rotacion_mensual": round(demanda_estimada_mes, 2),
                "meses_cobertura": round(meses_cobertura, 1),
                "recomendacion": recomendacion,
                "valor_stock": round(stock * costo, 2),
                "margen_unitario": round(row["precio_venta"] - row["precio_costo"], 2),
            })

        pred = pd.DataFrame(resultados)
        pred["fecha_recomendada"] = pd.Timestamp.today().strftime("%Y-%m-%d")
        return pred.sort_values("recomendacion", key=lambda s: s.map({"Reabastecer": 0, "Vigilar": 1, "Suficiente": 2}))

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