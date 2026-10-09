"""Nucleo del sistema: configuracion, catalogo de datos y pipeline ETL."""

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Probabilidad de churn a partir de la cual se alerta. Es el valor por
# defecto de la config ``alertas.churn_riesgo_umbral`` y lo comparten
# alertas, recomendaciones y los reportes: tenerlo aqui evita que cada
# llamador ponga su propio 0.60 y se desincronicen.
UMBRAL_CHURN_DEFECTO = 0.60

#: Ventana de analisis anual que comparten informe y simulador: cuantos meses
#: de historial se miran atras y cuantos se proyectan hacia delante. Evita que
#: el literal 12 se dispersara por tres ficheros (review #2, F1.2).
VENTANA_MESES = 12


def umbral_churn(alertas_cfg) -> float:
    """Umbral de churn efectivo: config del tenant o el defecto."""
    valor = (alertas_cfg or {}).get("churn_riesgo_umbral")
    # La cadena vacia llega desde un config.yaml escrito a mano y cuenta
    # como "sin fijar": float("") reventaria al generar el reporte.
    if valor is None or valor == "":
        return UMBRAL_CHURN_DEFECTO
    return float(valor)


@dataclass
class DatasetConfig:
    """Definicion de un dataset en la configuracion."""
    nombre: str
    archivo: Optional[str] = None
    formato: str = "auto"          # auto | csv | excel | sav | zsav | por
    hoja: Optional[int] = None     # para excel
    mapeo: Dict[str, str] = field(default_factory=dict)  # columna_origen -> columna_canonica
    descripcion: str = ""
    fuentes_alternativas: List[str] = field(default_factory=list)  # otros archivos/variantes


@dataclass
class AppConfig:
    """Configuracion global del sistema."""
    clave: str = "principal"         # workspace/tenant (multiempresa)
    negocio_nombre: str = "Mi Negocio"
    sector: str = ""                 # vertical de ejemplo (taller mecanico, retail, ...)
    slogan: str = "Gira tus datos en resultados"
    moneda: str = "MXN"
    directorio_datos: Path = Path("data")
    db_path: Path = Path("data/almacen.duckdb")
    cache_dir: Path = Path("data/cache")
    usar_cache: bool = True
    datasets: Dict[str, DatasetConfig] = field(default_factory=dict)
    # --- configuracion de negocio avanzada (Idea 1/2/3) ---
    inventario: Dict = field(default_factory=dict)   # horizonte, lead time, mapeo servicio->categoria
    mantenimiento: Dict = field(default_factory=dict)  # intervalos de servicio preventivo (meses)
    alertas: Dict = field(default_factory=dict)      # reglas y canales de notificacion
    # --- identidad/marca (startup: tema por workspace) ---
    tema: Dict = field(default_factory=dict)         # colores y texto de marca
    # --- white-label (Fase 3: reventa): titulo de ventana y pie de pagina ---
    whitelabel: Dict = field(default_factory=dict)   # titulo, footer, mostrar_footer
    # --- defaults del simulador por vertical (Fase 2: what-if por sector) ---
    simulador: Dict = field(default_factory=dict)    # margen, gastos, crecimiento del sector
    # --- conectores a origenes externos (Fase 2: ERP/SQL/archivos remotos) ---
    conectores: List[Dict] = field(default_factory=list)  # motor, fuente, consulta, dataset, forzar
    # --- reportes ejecutivos (producto reventa): white-label y tipos por cliente ---
    reportes: Dict = field(default_factory=dict)  # tipos, ocasion, periodos_meses, branding
    # --- submarca/plataforma (inversion/pitch): planes, COGS y costo fijo ---
    suscripcion: Dict = field(default_factory=dict)  # planes, costo_tenant, gasto_fijo

    # Compat: campo historico `taller_nombre` (se mantiene sincronizado).
    @property
    def taller_nombre(self) -> str:
        return self.negocio_nombre

    @taller_nombre.setter
    def taller_nombre(self, valor: str):
        self.negocio_nombre = valor