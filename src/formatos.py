"""Formato de presentacion de numeros y moneda.

Una sola implementacion de "como se ve un numero" para todo el producto.
Antes habia tres copias que habian ido divergiendo:

* ``ui/components.py`` — ``miles``/``moneda``, sin tolerancia a errores.
* ``src/reporting/formato.py`` — otras ``miles``/``moneda`` con defaults y
  tolerancia distintos: el mismo valor podia renderizarse distinto en el
  dashboard y en el reporte descargado.
* ``main.py`` — su propio ``_formato`` y un ``_moneda`` que importaba
  ``ui.components`` **perezosamente**, lo que metia la UI en el CLI.

Modulo sin dependencias: ni streamlit, ni plotly, ni duckdb. Eso es lo que
permite que lo usen por igual el dashboard, los reportes, la API y la CLI.

Notas de compatibilidad
-----------------------
* ``moneda`` usa ``moneda="CLP"`` por defecto; ``ui/components`` decia
  ``"MXN"``. Ambos simbolo ``$``, asi que **la salida es identica** y
  ninguna llamada existente cambia de render.
* La tolerancia a errores (devolver ``""`` ante un valor no numerico) ya la
  tenian los reportes y ahora la hereda la UI: hoy la UI lanzaba.
"""

from __future__ import annotations

#: Simbolo por moneda. Las no listadas caen a ``$``.
_SIMBOLOS = {"MXN": "$", "USD": "$", "EUR": "€", "CLP": "$", "COP": "$"}

#: Monedas enteras: nunca llevan decimales aunque se pidan.
_MONEDAS_ENTERAS = {"CLP", "MXN", "COP", "CRC"}


def miles(valor, decimales: int = 0) -> str:
    """Numero con punto como separador de miles (es-CL).

    Devuelve ``""`` si el valor no es numerico en vez de lanzar: una celda
    de tabla o una etiqueta de KPI con ``None`` no debe tumbar el render.
    """
    try:
        return f"{float(valor):,.{int(decimales)}f}".replace(",", ".")
    except (TypeError, ValueError):
        return ""


def moneda(valor, moneda: str = "CLP", decimales: int = 0) -> str:
    """Importe con el simbolo de la moneda del workspace.

    Las monedas enteras (CLP, MXN, COP, CRC) se redondean siempre: pedir
    decimales para CLP es un error de quien llama, no algo que haya que
    reflejar en pantalla.
    """
    codigo = (moneda or "CLP").upper()
    if codigo in _MONEDAS_ENTERAS:
        decimales = 0
    return f"{_SIMBOLOS.get(codigo, '$')}{miles(valor, decimales)}"


def formato_moneda(moneda: str = "CLP") -> str:
    """Formato de columna numerica para ``column_config`` con la moneda del cfg.

    Centraliza el simbolo: las tablas no deben hardcodear ``$`` si el
    workspace esta en EUR.
    """
    return f"{_SIMBOLOS.get((moneda or 'CLP').upper(), '$')}#,##0"


def formato_archivo(fmt) -> str:
    """Etiqueta de formato para una celda de tabla (texto plano).

    El texto de una celda de ``st.dataframe`` se muestra literal: ahi no
    entra HTML ni markdown, asi que un chip ``<span>`` se veria como codigo.
    Para badges con color usar ``ui.components.badge`` en el flujo markdown.
    """
    return str(fmt or "?").upper()


__all__ = ["miles", "moneda", "formato_moneda", "formato_archivo"]
