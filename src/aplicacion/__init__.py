"""Casos de uso de la aplicacion.

Capa de aplicacion del hexagono: orquesta el dominio y los puertos sin
saber de que adaptador habla. Los adaptadores de entrada (Streamlit en
`ui/`, la API, la CLI) llaman aqui; los de salida (`src/storage`,
`src/loaders`, `src/model_registry`) son los que el nucleo invoca a traves
de `src/puertos`.

Regla: **aqui no se importa `streamlit`**. Si aparece, el caso de uso se ha
quedado atado a un adaptador concreto y deja de poder servir a otro.
"""

from .almacen import (
    EJEMPLOS_SQL,
    VISTAS_PARA_EXPORTAR,
    abrir_almacen,
    consulta_sql,
    estructura,
    exportar_analitica_pspp,
    firma_datos,
    firma_fuentes,
    resumen_calidad,
    resumen_reglas,
    sincronizar_almacen,
    validar_sql_solo_lectura,
    vista,
)
from .carga import (
    CUOTA_WORKSPACE_BYTES,
    FORMATOS_PSPP,
    LIMITE_SUBIDA_BYTES,
    derivados_almacen,
    directorio_datos_permitido,
    ejecutar_etl,
    exportar_datasets_sav,
    filas_conectores,
    filas_detectadas,
    guardar_subidas,
    leer_archivos_pspp,
    mismo_contenido,
)
from .conectores import (
    conectores_desde_snapshot,
    crear_snapshot_erp,
    escribir_conectores,
    parsear_conectores,
    sincronizar_conectores,
)
from .warehouse import (
    ESQUEMAS_WAREHOUSE,
    publicar_warehouse,
    ver_warehouse,
)

__all__ = [
    "EJEMPLOS_SQL",
    "VISTAS_PARA_EXPORTAR",
    "abrir_almacen",
    "consulta_sql",
    "estructura",
    "exportar_analitica_pspp",
    "firma_datos",
    "firma_fuentes",
    "resumen_calidad",
    "resumen_reglas",
    "sincronizar_almacen",
    "validar_sql_solo_lectura",
    "vista",
    "CUOTA_WORKSPACE_BYTES",
    "FORMATOS_PSPP",
    "LIMITE_SUBIDA_BYTES",
    "derivados_almacen",
    "directorio_datos_permitido",
    "ejecutar_etl",
    "exportar_datasets_sav",
    "filas_conectores",
    "filas_detectadas",
    "guardar_subidas",
    "leer_archivos_pspp",
    "mismo_contenido",
    "conectores_desde_snapshot",
    "crear_snapshot_erp",
    "escribir_conectores",
    "parsear_conectores",
    "sincronizar_conectores",
    "ESQUEMAS_WAREHOUSE",
    "publicar_warehouse",
    "ver_warehouse",
]
