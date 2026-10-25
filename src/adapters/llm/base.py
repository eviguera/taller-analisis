"""Base para adaptadores LLM."""
from __future__ import annotations

from typing import Any, Dict

from src.puertos.agente_ia import RespuestaAsesor


class AdaptadorLLMBase:
    proveedor: str = "base"

    def generar_respuesta(
        self,
        contexto_datos: Dict[str, Any],
        instrucciones: str,
        respuesta_json_esperada: bool = True,
    ) -> RespuestaAsesor:
        raise NotImplementedError
