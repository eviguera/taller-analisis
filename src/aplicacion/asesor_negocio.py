"""Caso de uso: Asesor de Negocio con IA (puro, sin streamlit/fastapi)."""
from __future__ import annotations

from typing import Any, Dict

from src.adapters.llm.factory import obtener_adaptador_llm
from src.puertos.agente_ia import RespuestaAsesor
from src.servicios.contexto_datos import construir_contexto_asesor


def asesor_ia_disponible() -> bool:
    """Indica si el proveedor de IA tiene credenciales configuradas."""
    return bool(obtener_adaptador_llm().disponible())


def generar_diagnostico_automatico(cfg: Any, data: Dict[str, Any]) -> RespuestaAsesor:
    """Genera diagnóstico automático grounded con datos del workspace."""
    contexto = construir_contexto_asesor(cfg, data)
    instrucciones = (
        "Genera un DIAGNÓSTICO AUTOMÁTICO para el dueño de la pyme. "
        "Sé directo, práctico y accionable. "
        "Enfócate en 3 hallazgos clave, 3 acciones prioritarias y riesgos si los hay. "
        "Prioriza lo que tenga mayor impacto con menor esfuerzo. "
        "Usa cifras solo si aparecen en el contexto. "
        "Idioma español."
    )
    adaptador = obtener_adaptador_llm()
    resp = adaptador.generar_respuesta(contexto, instrucciones, respuesta_json_esperada=True)
    return resp


def preguntar_al_asesor(cfg: Any, data: Dict[str, Any], pregunta: str) -> RespuestaAsesor:
    """Pregunta al asesor sobre datos del workspace."""
    contexto = construir_contexto_asesor(cfg, data)
    instrucciones = (
        f"Responde a esta pregunta basándote ÚNICAMENTE en el contexto: {pregunta}\n\n"
        "Dame respuesta práctica con acciones si procede. "
        "Si no hay datos suficientes en el contexto para responder con certeza, indícalo."
    )
    adaptador = obtener_adaptador_llm()
    resp = adaptador.generar_respuesta(contexto, instrucciones, respuesta_json_esperada=True)
    return resp


__all__ = [
    "asesor_ia_disponible",
    "generar_diagnostico_automatico",
    "preguntar_al_asesor",
]
