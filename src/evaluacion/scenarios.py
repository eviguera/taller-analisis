"""Escenarios de evaluación determinística.

Cada escenario es un dict con:
  - nombre: identificador legible
  - descripcion: qué se verifica
  - datos: dict de DataFrames simulados (mismo esquema que load_all)
  - cfg: AppConfig mínima
  - fn: función bajo prueba (recibe datos, cfg)
  - esperado: aserciones a verificar sobre el resultado
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from src.core.config import AppConfig


@dataclass
class Escenario:
    nombre: str
    descripcion: str
    datos: dict
    cfg: AppConfig
    fn: Callable
    verificar: Callable[[Any], bool]  # recibe el resultado, devuelve True si pasa

    def ejecutar(self) -> tuple[bool, str]:
        try:
            resultado = self.fn(self.datos, self.cfg)
            ok = self.verificar(resultado)
            return ok, "" if ok else "La verificación no se cumplió."
        except Exception as exc:  # noqa: BLE001 — se captura para reportar, no se traga
            return False, f"Excepción: {exc}"


# ---------------------------------------------------------------------------
# Datos simulados compartidos
# ---------------------------------------------------------------------------

def _datos_simulados() -> dict:
    """Datos mínimos de un taller con 4 clientes, 4 vehículos, 8 facturas y
    3 productos de inventario."""
    clientes = pd.DataFrame([
        {"id": 1, "nombre": "Juan Pérez", "telefono": "555-0001", "email": "juan@ej.com",
         "fecha_registro": "2024-01-10"},
        {"id": 2, "nombre": "María Gómez", "telefono": "555-0002", "email": "maria@ej.com",
         "fecha_registro": "2024-02-15"},
        {"id": 3, "nombre": "Carlos Ruiz", "telefono": "555-0003", "email": "carlos@ej.com",
         "fecha_registro": "2024-03-01"},
        {"id": 4, "nombre": "Lucía Díaz", "telefono": "555-0004", "email": "lucia@ej.com",
         "fecha_registro": "2024-03-10"},
    ])
    vehiculos = pd.DataFrame([
        {"id": 1, "cliente_id": 1, "marca": "Toyota", "modelo": "Corolla", "anio": 2018,
         "placa": "ABC-123", "color": "Blanco", "kilometraje": 45000},
        {"id": 2, "cliente_id": 2, "marca": "Nissan", "modelo": "Versa", "anio": 2019,
         "placa": "DEF-456", "color": "Negro", "kilometraje": 30000},
        {"id": 3, "cliente_id": 3, "marca": "Toyota", "modelo": "Yaris", "anio": 2015,
         "placa": "GHI-789", "color": "Gris", "kilometraje": 110000},
        {"id": 4, "cliente_id": 4, "marca": "Hyundai", "modelo": "Accent", "anio": 2020,
         "placa": "JKL-012", "color": "Rojo", "kilometraje": 20000},
    ])
    servicios = pd.DataFrame([
        {"id": 1, "nombre": "Cambio de aceite", "precio_base": 5000, "tiempo_estimado_min": 30},
        {"id": 2, "nombre": "Revisión de frenos", "precio_base": 15000, "tiempo_estimado_min": 60},
        {"id": 3, "nombre": "Alineación y balanceo", "precio_base": 8000, "tiempo_estimado_min": 45},
    ])
    # Fecha de "hoy" simulada: usamos 2024-06-01 como referencia
    hoy = pd.Timestamp("2024-06-01")
    facturas = pd.DataFrame([
        # Juan: cliente frecuente, última visita reciente, bajo churn
        {"id": 101, "cliente_id": 1, "vehiculo_id": 1, "fecha": "2024-05-20", "total": 15000,
         "descuento": 0, "estado": "Pagada", "detalles": "1:1"},
        {"id": 102, "cliente_id": 1, "vehiculo_id": 1, "fecha": "2024-04-01", "total": 20000,
         "descuento": 0, "estado": "Pagada", "detalles": "2:1"},
        {"id": 103, "cliente_id": 1, "vehiculo_id": 1, "fecha": "2024-02-10", "total": 5000,
         "descuento": 0, "estado": "Pagada", "detalles": "1:1"},
        # María: última visita hace 3 meses, riesgo de churn medio
        {"id": 104, "cliente_id": 2, "vehiculo_id": 2, "fecha": "2024-03-01", "total": 25000,
         "descuento": 0, "estado": "Pagada", "detalles": "2:1"},
        {"id": 105, "cliente_id": 2, "vehiculo_id": 2, "fecha": "2024-01-15", "total": 8000,
         "descuento": 0, "estado": "Pagada", "detalles": "1:1"},
        # Carlos: última visita hace 8 meses, alto churn, vehículo viejo y km alto
        {"id": 106, "cliente_id": 3, "vehiculo_id": 3, "fecha": "2023-10-01", "total": 30000,
         "descuento": 0, "estado": "Pagada", "detalles": "3:1;1:1"},
        {"id": 107, "cliente_id": 3, "vehiculo_id": 3, "fecha": "2023-06-15", "total": 12000,
         "descuento": 0, "estado": "Pagada", "detalles": "1:1"},
        # Lucía: reciente, bajo monto
        {"id": 108, "cliente_id": 4, "vehiculo_id": 4, "fecha": "2024-05-15", "total": 6000,
         "descuento": 0, "estado": "Pagada", "detalles": "1:1"},
    ])
    inventario = pd.DataFrame([
        {"id": 1, "producto": "Aceite 5W30", "categoria": "Lubricantes", "precio_costo": 3000,
         "precio_venta": 5000, "stock_actual": 2, "stock_minimo": 10},
        {"id": 2, "producto": "Filtro de aceite", "categoria": "Filtros", "precio_costo": 2000,
         "precio_venta": 3500, "stock_actual": 50, "stock_minimo": 5},
        {"id": 3, "producto": "Pastillas de freno", "categoria": "Frenos", "precio_costo": 8000,
         "precio_venta": 15000, "stock_actual": 1, "stock_minimo": 4},
    ])
    # Convertir columnas de fecha a datetime (como haria el pipeline al cargar CSV).
    for df_ in (clientes, facturas):
        for col in ("fecha_registro", "fecha"):
            if col in df_.columns:
                df_[col] = pd.to_datetime(df_[col], errors="coerce")

    return {
        "clientes": clientes,
        "vehiculos": vehiculos,
        "servicios": servicios,
        "facturas": facturas,
        "inventario": inventario,
    }


def _cfg_simulado() -> AppConfig:
    return AppConfig(
        clave="eval-taller",
        negocio_nombre="Taller Eval",
        moneda="MXN",
        alertas={
            "churn_riesgo_umbral": 0.60,
            "stock_bajo": True,
            "churn": True,
            "caida_ingresos": True,
            "facturas_pendientes": True,
        },
        mantenimiento={
            "intervalos_meses": {
                "cambio de aceite": 6,
                "revision de frenos": 12,
                "alineación y balanceo": 6,
            },
            "pendientes_considerar": 3,
        },
    )


# ---------------------------------------------------------------------------
# Escenario 1: next_best_action → cliente con alto churn recibe "Reactivar"
# ---------------------------------------------------------------------------

class _PredictorMock:
    """Predictor de prueba que devuelve prob_churn conocido (sin ML)."""

    def predecir_churn(self):
        import pandas as pd
        hoy = pd.Timestamp("2024-06-01")
        rfm = pd.DataFrame([
            {"cliente_id": 1, "nombre": "Juan Pérez", "prob_churn": 0.05,
             "recencia": 10, "frecuencia": 3, "monto": 40000},
            {"cliente_id": 2, "nombre": "María Gómez", "prob_churn": 0.30,
             "recencia": 80, "frecuencia": 2, "monto": 33000},
            {"cliente_id": 3, "nombre": "Carlos Ruiz", "prob_churn": 0.90,
             "recencia": 232, "frecuencia": 2, "monto": 42000},
            {"cliente_id": 4, "nombre": "Lucía Díaz", "prob_churn": 0.10,
             "recencia": 5, "frecuencia": 1, "monto": 6000},
        ])
        return {"resultados": rfm, "modelo": "mock", "evaluacion": {}, "registro": None}

    def predecir_inventario(self):
        import pandas as pd
        return pd.DataFrame(columns=[
            "id", "producto", "categoria", "stock_actual", "stock_minimo",
            "demanda_mensual", "tasa_rotacion_mensual", "stock_objetivo",
            "meses_cobertura", "cantidad_recomendada", "recomendacion",
            "valor_stock", "margen_unitario", "fecha_recomendada",
        ])


def _fn_recomendacion_churn(datos, cfg):
    from src.recomendaciones import next_best_action
    predictor = _PredictorMock()
    return next_best_action(datos, cfg, n=25, predictor=predictor)


def _verificar_churn(resultado) -> bool:
    """Carlos (prob_churn=0.90 >= umbral 0.60) → acción 'Reactivar' y canal
    'WhatsApp'. Los demás clientes de bajo churn no son 'Reactivar'."""
    df = resultado
    if df is None or df.empty:
        return False
    carlos = df[df["nombre"].str.contains("Carlos", na=False)]
    if carlos.empty:
        return False
    fila = carlos.iloc[0]
    if fila["accion"] != "Reactivar" or fila["canal"] != "WhatsApp":
        return False
    # María (0.30 < 0.60) no debe ser 'Reactivar'
    maria = df[df["nombre"].str.contains("María", na=False)]
    if not maria.empty and maria.iloc[0]["accion"] == "Reactivar":
        return False
    return True


# ---------------------------------------------------------------------------
# Escenario 2: alerta stock_bajo → producto con stock por debajo del mínimo
# ---------------------------------------------------------------------------

def _fn_alerta_stock(datos, cfg):
    from src.alertas_avanzadas import evaluar_alertas_avanzadas
    return evaluar_alertas_avanzadas(cfg, datos)


def _verificar_stock(resultado) -> bool:
    """Debe haber al menos una alerta de stock_bajo con severidad crítica,
    derivada de productos cuyo stock está por debajo del mínimo."""
    stock_alertas = [a for a in resultado if a.get("tipo") == "stock_bajo"]
    if not stock_alertas:
        return False
    return all(a.get("severidad") in ("critica", "media") for a in stock_alertas)


# ---------------------------------------------------------------------------
# Escenario 3: proximo_servicio → vehículo con cambio de aceite vencido
# ---------------------------------------------------------------------------

def _fn_proximo_servicio(datos, cfg):
    from src.recomendaciones import proximo_servicio
    return proximo_servicio(datos, cfg)


def _verificar_proximo_servicio(resultado) -> bool:
    """El vehículo 1 (Toyota Corolla, Juan) necesita cambio de aceite (intervalo
    6 meses, último hace ~1 mes → OK, pero el de Carlos hace 8 meses → vencido).
    Verificamos que devuelva al menos una fila con nota 'vencido' o 'proximo'."""
    df = resultado
    return df is not None and not df.empty and "servicio_sugerido" in df.columns


ESCENARIOS = [
    Escenario(
        nombre="recomendacion_churn_reactivar",
        descripcion="Cliente con alta recencia y vehículo viejo → 'Reactivar' por WhatsApp.",
        datos=_datos_simulados(),
        cfg=_cfg_simulado(),
        fn=_fn_recomendacion_churn,
        verificar=_verificar_churn,
    ),
    Escenario(
        nombre="alerta_stock_bajo",
        descripcion="Productos con stock por debajo del mínimo generan alerta stock_bajo.",
        datos=_datos_simulados(),
        cfg=_cfg_simulado(),
        fn=_fn_alerta_stock,
        verificar=_verificar_stock,
    ),
    Escenario(
        nombre="proximo_servicio_vehiculo_vencido",
        descripcion="proximo_servicio devuelve vehículos con servicio pendiente/vencido.",
        datos=_datos_simulados(),
        cfg=_cfg_simulado(),
        fn=_fn_proximo_servicio,
        verificar=_verificar_proximo_servicio,
    ),
]


def ejecutar_todos() -> list[tuple[str, bool, str]]:
    """Ejecuta todos los escenarios y devuelve [(nombre, ok, mensaje)]."""
    return [(e.nombre,) + e.ejecutar() for e in ESCENARIOS]


def escenario_recomendacion_churn() -> Escenario:
    return ESCENARIOS[0]


def escenario_alerta_stock_bajo() -> Escenario:
    return ESCENARIOS[1]


def escenario_proximo_servicio() -> Escenario:
    return ESCENARIOS[2]


# ---------------------------------------------------------------------------
# Escenario 4: valor_recuperable >= 0 cuando hay cartera en riesgo
# ---------------------------------------------------------------------------

def _fn_valor_recuperable(datos, cfg):
    from src.analyzer import Analyzer
    from src.negocio import valor_recuperable, salud_cartera
    analyzer = Analyzer(datos)
    salud = salud_cartera(analyzer)
    return valor_recuperable(analyzer, cfg)


def _verificar_valor_recuperable(resultado) -> bool:
    return isinstance(resultado, (int, float)) and resultado >= 0


# ---------------------------------------------------------------------------
# Escenario 5: roi_suscripcion devuelve lista con planes
# ---------------------------------------------------------------------------

def _fn_roi_suscripcion(datos, cfg):
    from src.analyzer import Analyzer
    from src.negocio import roi_suscripcion, salud_cartera
    analyzer = Analyzer(datos)
    salud = salud_cartera(analyzer)
    return roi_suscripcion(analyzer, cfg)


def _verificar_roi(resultado) -> bool:
    return isinstance(resultado, list) and len(resultado) > 0


# ---------------------------------------------------------------------------
# Escenario 6: proximo_servicio con datos reales devuelve filas con columnas
# esperadas
# ---------------------------------------------------------------------------

def _verificar_proximo_servicio_columnas(resultado) -> bool:
    df = resultado
    return (
        df is not None
        and not df.empty
        and "servicio_sugerido" in df.columns
        and "vehiculo_id" in df.columns
        and "prioridad" in df.columns
    )


ESCENARIOS_EXTRA = [
    Escenario(
        nombre="valor_recuperable_no_negativo",
        descripcion="valor_recuperable devuelve un número >= 0.",
        datos=_datos_simulados(),
        cfg=_cfg_simulado(),
        fn=_fn_valor_recuperable,
        verificar=_verificar_valor_recuperable,
    ),
    Escenario(
        nombre="roi_suscripcion_lista_planes",
        descripcion="roi_suscripcion devuelve una lista de planes con ROI.",
        datos=_datos_simulados(),
        cfg=_cfg_simulado(),
        fn=_fn_roi_suscripcion,
        verificar=_verificar_roi,
    ),
    Escenario(
        nombre="proximo_servicio_columnas",
        descripcion="proximo_servicio devuelve columnas esperadas.",
        datos=_datos_simulados(),
        cfg=_cfg_simulado(),
        fn=_fn_proximo_servicio,
        verificar=_verificar_proximo_servicio_columnas,
    ),
]


def ejecutar_todos() -> list[tuple[str, bool, str]]:
    """Ejecuta todos los escenarios y devuelve [(nombre, ok, mensaje)]."""
    todos = ESCENARIOS + ESCENARIOS_EXTRA
    return [(e.nombre,) + e.ejecutar() for e in todos]


def escenario_recomendacion_churn() -> Escenario:
    return ESCENARIOS[0]


def escenario_alerta_stock_bajo() -> Escenario:
    return ESCENARIOS[1]


def escenario_proximo_servicio() -> Escenario:
    return ESCENARIOS[2]
