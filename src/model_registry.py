"""Registry de modelos: persiste los modelos de scikit-learn entre sesiones.

Los modelos se guardan con joblib en ``data/models/`` junto con un JSON de
metadatos (fecha de entrenamiento, metricas y tamano de la muestra). Asi el
dashboard no re-entrena en cada sesion: carga el modelo persistido y solo
re-entrena cuando cambia el volumen de datos o se pide explicitamente.
"""

from __future__ import annotations

import hashlib
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

    def _ruta_modelo(self, tipo: str, version: Optional[str] = None) -> Path:
        """Ruta del archivo del modelo. Si se da version, usa tipo_v{version}."""
        if version:
            return self.directorio / f"{tipo}_v{version}.joblib"
        return self.directorio / f"{tipo}.joblib"

    def _ruta_meta(self, tipo: str, version: Optional[str] = None) -> Path:
        """Ruta del archivo de metadatos del modelo."""
        if version:
            return self.directorio / f"{tipo}_v{version}.json"
        return self.directorio / f"{tipo}.json"

    def _siguiente_version(self, tipo: str) -> int:
        """Calcula el siguiente numero de version para un tipo de modelo."""
        existentes = []
        for p in self.directorio.glob(f"{tipo}_v*.joblib"):
            try:
                v = int(p.stem.split("_v")[-1])
                existentes.append(v)
            except (ValueError, IndexError):
                continue
        return max(existentes, default=0) + 1

    def guardar(self, tipo: str, modelo: Any, metadatos: Optional[dict] = None) -> dict:
        """Serializa el modelo y sus metadatos con versionado.

        Guarda como ``tipo_vN.joblib`` donde N es el siguiente numero de
        version, y crea un enlace logico ``tipo.joblib`` y ``tipo.meta.json``
        apuntando a la version mas reciente.
        """
        import joblib

        version = self._siguiente_version(tipo)
        meta = dict(metadatos or {})
        import sklearn
        meta.update({
            "tipo": tipo,
            "version": version,
            "fecha_entrenamiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sklearn_version": sklearn.__version__,
        })
        ruta_modelo = self._ruta_modelo(tipo, version)
        joblib.dump(modelo, ruta_modelo)
        # Hash SHA-256 de integridad (regla 5: no deserializar sin validar origen)
        digest = hashlib.sha256(ruta_modelo.read_bytes()).hexdigest()
        meta["sha256"] = digest
        self._ruta_meta(tipo, version).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        # Actualizar alias "latest" hacia la version mas reciente
        self._ruta_modelo(tipo).write_bytes(ruta_modelo.read_bytes())
        self._ruta_meta(tipo).write_text(
            self._ruta_meta(tipo, version).read_text(encoding="utf-8"), encoding="utf-8")
        meta["version_guardada"] = version
        return meta

    def cargar(self, tipo: str, version: Optional[int] = None
               ) -> tuple[Any, Optional[dict]]:
        """Devuelve ``(modelo, metadatos)`` o ``(None, None)`` si no existe.

        Un ``joblib`` es deserializacion arbitraria (RCE potencial): el archivo
        debe vivir dentro del directorio del registry y tener extension
        ``.joblib`` esperada. Cualquier fallo se registra en vez de tragarse,
        para que un modelo corrupto no parezca un "reentrena solo" fantasma.

        Si se da ``version``, carga esa version especifica; si no, carga la
        version mas reciente (alias ``tipo.joblib``).
        """
        import joblib

        import sklearn

        modelo_path = self._ruta_modelo(tipo, version)
        meta_path = self._ruta_meta(tipo, version)

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

        # Verificar hash SHA-256 de integridad antes de deserializar
        digest_almacenado = (meta or {}).get("sha256")
        if digest_almacenado:
            digest_actual = hashlib.sha256(modelo_path_resuelto.read_bytes()).hexdigest()
            if digest_actual != digest_almacenado:
                log.warning(
                    "Modelo %s hash SHA-256 no coincide (posible manipulacion); "
                    "se reentrenara", tipo,
                )
                return None, None

        try:
            modelo = joblib.load(modelo_path_resuelto)
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo cargar el modelo %s (%s): %s; se reentrenara",
                        tipo, modelo_path.name, type(e).__name__)
            return None, None
        return modelo, meta

    def listar_versiones(self, tipo: str) -> list[dict[str, Any]]:
        """Lista todas las versiones guardadas de un tipo de modelo."""
        versiones: list[dict[str, Any]] = []
        for meta_path in sorted(self.directorio.glob(f"{tipo}_v*.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["archivo"] = self.directorio / f"{meta_path.stem}.joblib"
                meta["existe_modelo"] = Path(str(meta["archivo"])).exists()
                versiones.append(meta)
            except (json.JSONDecodeError, OSError):
                continue
        return sorted(versiones, key=lambda m: m.get("version", 0))

    def detectar_drift(
        self,
        tipo: str,
        datos_actuales: pd.DataFrame,
        columnas_features: list[str],
    ) -> dict[str, Any]:
        """Detecta drift de datos comparando distribuciones actuales vs entrenamiento.

        Compara la media y desviacion estandar de cada característica entre
        los datos de entrenamiento (almacenados en metadatos) y los datos
        actuales. Devuelve un diccionario con el resultado del drift para
        cada caracteristica y una bandera global de drift detectado.

        Requiere que los metadatos del modelo contengan estadisticas
        (media y std) de las características de entrenamiento, guardadas
        durante el entrenamiento.
        """
        import numpy as np
        from scipy import stats

        meta_path = self._ruta_meta(tipo)
        if not meta_path.exists():
            return {
                "drift_detectado": False,
                "error": "No hay metadatos del modelo para comparar",
                "caracteristicas": {},
            }

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            return {
                "drift_detectado": False,
                "error": f"No se pudieron leer metadatos: {e}",
                "caracteristicas": {},
            }

        estadisticas_entrenamiento = meta.get("estadisticas_entrenamiento", {})
        if not estadisticas_entrenamiento:
            return {
                "drift_detectado": False,
                "error": "No hay estadísticas de entrenamiento en metadatos",
                "caracteristicas": {},
            }

        resultados: dict[str, Any] = {
            "drift_detectado": False,
            "umbral_p_valor": 0.05,
            "caracteristicas": {},
        }

        for columna in columnas_features:
            if columna not in datos_actuales.columns:
                continue

            valores_actuales = datos_actuales[columna].dropna().values
            if len(valores_actuales) < 10:
                continue

            stats_entrenamiento = estadisticas_entrenamiento.get(columna, {})
            media_entrenamiento = stats_entrenamiento.get("media")
            std_entrenamiento = stats_entrenamiento.get("std", 1.0)

            if media_entrenamiento is None:
                continue

            media_actual = float(valores_actuales.mean())
            std_actual = float(valores_actuales.std())

            # Prueba t de Welch para comparar medias
            try:
                _, p_valor = stats.ttest_ind_from_stats(
                    media_actual, std_actual, len(valores_actuales),
                    media_entrenamiento, std_entrenamiento,
                    max(1, len(valores_actuales)),
                )
            except Exception:
                p_valor = 1.0

            drift_detectado = p_valor < 0.05

            if drift_detectado:
                resultados["drift_detectado"] = True

            resultados["caracteristicas"][columna] = {
                "media_entrenamiento": media_entrenamiento,
                "media_actual": media_actual,
                "std_entrenamiento": std_entrenamiento,
                "std_actual": std_actual,
                "p_valor": round(float(p_valor), 4),
                "drift_detectado": drift_detectado,
            }

        return resultados

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