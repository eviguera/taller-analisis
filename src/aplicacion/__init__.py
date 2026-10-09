"""Casos de uso de la aplicacion.

Capa de aplicacion del hexagono: orquesta el dominio y los puertos sin
saber de que adaptador habla. Los adaptadores de entrada (Streamlit en
`ui/`, la API, el CLI) llaman aqui; los de salida (`src/storage`,
`src/loaders`, `src/model_registry`) son los que el nucleo invoca a traves
de `src/puertos`.

Regla: **aqui no se importa `streamlit`**. Si aparece, el caso de uso se ha
quedado atado a un adaptador concreto y deja de poder servir a otro.
"""

from .almacen import (
    VISTAS_PARA_EXPORTAR,
    abrir_almacen,
    consulta_sql,
    estructura,
    exportar_analitica_pspp,
    firma_datos,
    firma_fuentes,
    resumen_calidad,
    sincronizar_almacen,
    validar_sql_solo_lectura,
    vista,
)

__all__ = [
    "VISTAS_PARA_EXPORTAR",
    "abrir_almacen",
    "consulta_sql",
    "estructura",
    "exportar_analitica_pspp",
    "firma_datos",
    "firma_fuentes",
    "resumen_calidad",
    "sincronizar_almacen",
    "validar_sql_solo_lectura",
    "vista",
]
