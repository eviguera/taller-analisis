"""Formato de numeros, fechas y graficos para los reportes (es-CL)."""

import base64
import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MESES_ES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

MESES_ES_CORTO = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                  "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

DIAS_SEMANA = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miercoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sabado",
    "Sunday": "Domingo",
}


def miles(valor, decimales=0):
    """Formatea un numero con punto como separador de miles (es-CL)."""
    try:
        return f"{float(valor):,.{decimales}f}".replace(",", ".")
    except (TypeError, ValueError):
        return ""


def moneda(valor, moneda="CLP", decimales=0):
    """Formatea un valor de forma monetaria segun la moneda del workspace."""
    simbolo = {"MXN": "$", "USD": "$", "EUR": "€", "CLP": "$"}.get(moneda or "CLP", "$")
    if moneda and moneda.upper() in ("CLP", "MXN", "COP", "CRC"):
        decimales = 0
    return f"{simbolo}{miles(valor, decimales)}"


def pct(valor, decimales=0):
    try:
        return f"{float(valor) * 100:{'.0f' if decimales == 0 else '.' + str(decimales)}f}%"
    except (TypeError, ValueError):
        return ""


def fecha_es(fecha=None, con_hora=False):
    fecha = fecha or datetime.now()
    base = f"{fecha.day} de {MESES_ES[fecha.month - 1]} de {fecha.year}"
    return base if not con_hora else f"{base} a las {fecha.strftime('%H:%M')}"


def periodo_es(anio_mes: str) -> str:
    """Convierte '2024-07' en 'Jul 2024'."""
    try:
        anio, mes = anio_mes.split("-")
        return f"{MESES_ES_CORTO[int(mes) - 1]} {anio}"
    except (ValueError, IndexError):
        return anio_mes


def fig_a_base64(fig, dpi=110, ancho=None):
    """Convierte una figura matplotlib a data URI PNG para incrustar en HTML."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return f"data:image/png;base64,{encoded}"