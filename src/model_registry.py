"""Registry de modelos: persiste los modelos de scikit-learn entre sesiones.

Los modelos se guardan con joblib en ``data/models/`` junto con un JSON de
metadatos (fecha de entrenamiento, metricas y tamano de la muestra). Asi el
dashboard no re-entrena en cada sesion: carga el modelo persistido y solo
re-entrena cuando cambia el volumen de datos o se pide explicitamente.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class ModelRegistry:
    """Guardado/carga de modelos por tipo (churn, ingresos, demanda, ...)."""

    def __init__(self, directorio: Optional[Path] = None):
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
        meta.update({
            "tipo": tipo,
            "fecha_entrenamiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        joblib.dump(modelo, self._ruta_modelo(tipo))
        self._ruta_meta(tipo).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return meta

    def cargar(self, tipo: str) -> tuple[Any, Optional[dict]]:
        """Devuelve ``(modelo, metadatos)`` o ``(None, None)`` si no existe."""
        import joblib

        modelo_path = self._ruta_modelo(tipo)
        meta_path = self._ruta_meta(tipo)
        if not modelo_path.exists():
            return None, None
        try:
            modelo = joblib.load(modelo_path)
        except Exception:  # noqa: BLE001
            return None, None
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
        return modelo, meta

    def borrar(self, tipo: str) -> None:
        """Elimina un modelo guardado (para forzar reentrenamiento)."""
        for r in (self._ruta_modelo(tipo), self._ruta_meta(tipo)):
            if r.exists():
                r.unlink()

    def listar(self) -> list[dict]:
        """Catalogo de modelos persistidos con sus metadatos."""
        modelos = []
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
        _, meta = self.cargar(tipo)
        if not meta:
            return False
        return (meta.get("n_muestras") or 0) >= n_minimo