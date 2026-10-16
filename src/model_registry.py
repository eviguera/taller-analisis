"""Registry de modelos: persiste los modelos de scikit-learn entre sesiones.

Los modelos se guardan con joblib en ``data/models/`` junto con un JSON de
metadatos (fecha de entrenamiento, metricas y tamano de la muestra). Asi el
dashboard no re-entrena en cada sesion: carga el modelo persistido y solo
re-entrena cuando cambia el volumen de datos o se pide explicitamente.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .puertos import PuertoRegistroModelos

log = logging.getLogger("taller.registry")


class ModelRegistry(PuertoRegistroModelos):
    """Guardado/carga de modelos por tipo (churn, ingresos, demanda, ...)."""

    def __init__(self, directorio: Optional[Path] = None) -> None:
        self.directorio = Path(directorio) if directorio else Path("data/models")
        self.directorio.mkdir(parents=True, exist_ok=True)

    def _ruta_modelo(self, tipo: str) -> Path:
        return self.directorio / f"{tipo}.joblib"

    def _ruta_meta(self, tipo: str) -> Path:
        return self.directorio / f"{tipo}.json"

    def guardar(self, tipo: str, modelo: Any, metadatos: Optional[dict] = None) -> dict:
        """Serializa el modelo y sus metadatos."""
        import joblib

        meta = dict(metadatos or {})
        import sklearn
        meta.update({
            "tipo": tipo,
            "fecha_entrenamiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sklearn_version": sklearn.__version__,
        })
        joblib.dump(modelo, self._ruta_modelo(tipo))
        self._ruta_meta(tipo).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return meta

    def cargar(self, tipo: str) -> tuple[Any, Optional[dict]]:
        """Devuelve ``(modelo, metadatos)`` o ``(None, None)`` si no existe.

        Un ``joblib`` es deserializacion arbitraria (RCE potencial): el archivo
        debe vivir dentro del directorio del registry y tener extension
        ``.joblib`` esperada. Cualquier fallo se registra en vez de tragarse,
        para que un modelo corrupto no parezca un "reentrena solo" fantasma.
        """
        import joblib

        import sklearn

        modelo_path = self._ruta_modelo(tipo)
        meta_path = self._ruta_meta(tipo)

        if not modelo_path.exists():
            return None, None

        # Validacion de origen (regla 5 de AGENTS.md):
        # 1. El path resuelto debe estar dentro del directorio del registry.
        # 2. La extension debe ser exactamente .joblib (evita archivos
        #    forjados con otro nombre dentro del directorio).
        modelo_path_resuelto = modelo_path.resolve()
        if self.directorio.resolve() not in modelo_path_resuelto.parents:
            log.warning("Modelo %s fuera del registry; se ignora", modelo_path_resuelto)
            return None, None
        if modelo_path_resuelto.suffix != ".joblib":
            log.warning("Modelo %s con extension no valida; se ignora",
                        modelo_path_resuelto)
            return None, None

        meta: Optional[dict] = None
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Metadatos ilegibles para %s: %s", tipo, e)

        version_sklearn = (meta or {}).get("sklearn_version")
        if version_sklearn:
            if str(version_sklearn) != sklearn.__version__:
                # sklearn no garantiza compatibilidad entre versiones al
                # deserializar; se descarta y se reentrena.
                log.warning("Modelo %s entrenado con sklearn %s (actual %s); "
                            "se reentrenara", tipo, version_sklearn, sklearn.__version__)
                return None, None

        try:
            modelo = joblib.load(modelo_path_resuelto)
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo cargar el modelo %s (%s): %s; se reentrenara",
                        tipo, modelo_path.name, type(e).__name__)
            return None, None
        return modelo, meta

    def borrar(self, tipo: str) -> None:
        """Elimina un modelo guardado (para forzar reentrenamiento)."""
        for r in (self._ruta_modelo(tipo), self._ruta_meta(tipo)):
            if r.exists():
                r.unlink()

    def listar(self) -> list[dict[str, Any]]:
        """Catalogo de modelos persistidos con sus metadatos."""
        modelos: list[dict[str, Any]] = []
        for meta_path in sorted(self.directorio.glob("*.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            meta["archivo"] = self.directorio / f"{meta_path.stem}.joblib"
            meta["existe_modelo"] = Path(str(meta["archivo"])).exists()
            modelos.append(meta)
        return modelos

    def es_fresco(self, tipo: str, n_minimo: int = 0) -> bool:
        """True si el modelo existe y fue entrenado con al menos `n_minimo` muestras."""
        # Lee solo el JSON: no deserializa el modelo completo solo para esto.
        meta_path = self._ruta_meta(tipo)
        if not meta_path.exists() or not self._ruta_modelo(tipo).exists():
            return False
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        return (meta.get("n_muestras") or 0) >= n_minimo