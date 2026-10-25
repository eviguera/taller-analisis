"""Adaptador OpenRouter (agnóstico, configurable por os.environ)."""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import requests

from src.puertos.agente_ia import (
    AccionPrioritaria,
    Hallazgo,
    RespuestaAsesor,
    Riesgo,
)


class OpenRouterAdapter:
    proveedor: str = "openrouter"

    def __init__(
        self,
        api_key: str | None = None,
        modelo: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
    ):
        self.api_key = api_key or os.environ.get("GIRO_IA_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or ""
        self.modelo = modelo or os.environ.get("GIRO_IA_MODEL") or "google/gemini-2.5-flash"
        self.base_url = (base_url or os.environ.get("GIRO_IA_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
        self.timeout = timeout or int(os.environ.get("GIRO_IA_TIMEOUT") or "60")
        self.max_tokens = int(os.environ.get("GIRO_IA_MAX_TOKENS") or "1400")

    def disponible(self) -> bool:
        """OpenRouter necesita una clave para poder consultar el modelo."""
        return bool(self.api_key)

    def _construir_prompt(self, contexto_datos: Dict[str, Any], instrucciones: str) -> str:
        sistema = (
            "Eres GIRO Asesor, un asesor de negocio práctico para pymes. "
            "Debes basarte ÚNICAMENTE en el contexto de datos proporcionado. "
            "No inventes cifras. Si falta información, dilo en 'preguntas_para_aclarar'. "
            "Responde SIEMPRE con JSON válido siguiendo el esquema exacto. "
            "Idioma: español."
        )
        esquema = {
            "resumen_ejecutivo": "string",
            "hallazgos": [
                {
                    "titulo": "string",
                    "descripcion": "string",
                    "severidad": "critica|alta|media|baja|ok",
                    "evidencia": ["string"],
                }
            ],
            "acciones": [
                {
                    "titulo": "string",
                    "descripcion": "string",
                    "prioridad": "alta|media|baja",
                    "esfuerzo": "bajo|medio|alto",
                    "impacto": "alto|medio|bajo",
                    "plazo": "inmediato|30_dias|60_dias|90_dias",
                    "categoria": "ventas|clientes|inventario|facturacion|finanzas|general",
                }
            ],
            "riesgos": [
                {
                    "titulo": "string",
                    "descripcion": "string",
                    "probabilidad": "alta|media|baja",
                    "impacto": "alto|medio|bajo",
                    "mitigacion": "string",
                }
            ],
            "preguntas_para_aclarar": ["string"],
            "fuentes_usadas": ["string"],
        }
        prompt = (
            f"{sistema}\n\n"
            f"INSTRUCCIONES:\n{instrucciones}\n\n"
            f"ESQUEMA JSON OBLIGATORIO:\n{json.dumps(esquema, ensure_ascii=False, indent=2)}\n\n"
            f"CONTEXTO DATOS (SOLO AGREGADOS, GROUNDED):\n{json.dumps(contexto_datos, ensure_ascii=False, indent=2)}\n\n"
            "Responde ÚNICAMENTE con el JSON, sin texto extra."
        )
        return prompt

    def _parsear_respuesta(self, texto: str) -> Dict[str, Any]:
        # Intentar extraer JSON si viene con markdown
        texto = texto.strip()
        if texto.startswith("```"):
            # quitar fences
            # simple
            partes = texto.split("```")
            if len(partes) >= 3:
                texto = partes[1]
                if texto.lower().startswith("json"):
                    texto = texto[4:]
        texto = texto.strip()
        try:
            return json.loads(texto)
        except Exception:
            # último intento: buscar primer { y último }
            ini = texto.find("{")
            fin = texto.rfind("}")
            if ini >= 0 and fin > ini:
                return json.loads(texto[ini : fin + 1])
            raise

    def generar_respuesta(
        self,
        contexto_datos: Dict[str, Any],
        instrucciones: str,
        respuesta_json_esperada: bool = True,
    ) -> RespuestaAsesor:
        if not self.api_key:
            raise RuntimeError("Falta GIRO_IA_API_KEY / OPENROUTER_API_KEY para usar OpenRouter")

        prompt = self._construir_prompt(contexto_datos, instrucciones)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.environ.get("GIRO_IA_HTTP_REFERER") or "http://localhost",
            "X-Title": os.environ.get("GIRO_IA_X_TITLE") or "GIRO Asesor",
        }
        body = {
            "model": self.modelo,
            "messages": [
                {"role": "system", "content": "Eres GIRO Asesor. Responde solo JSON válido."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": self.max_tokens,
        }
        resp = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=body, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        contenido = ""
        try:
            contenido = data["choices"][0]["message"]["content"] or ""
        except Exception:
            contenido = ""

        parsed = self._parsear_respuesta(contenido)
        hallazgos = []
        for h in parsed.get("hallazgos") or []:
            if isinstance(h, dict):
                hallazgos.append(
                    Hallazgo(
                        titulo=str(h.get("titulo") or ""),
                        descripcion=str(h.get("descripcion") or ""),
                        severidad=str(h.get("severidad") or "media"),
                        evidencia=[str(x) for x in (h.get("evidencia") or []) if x is not None],
                    )
                )
        acciones = []
        for a in parsed.get("acciones") or []:
            if isinstance(a, dict):
                acciones.append(
                    AccionPrioritaria(
                        titulo=str(a.get("titulo") or ""),
                        descripcion=str(a.get("descripcion") or ""),
                        prioridad=str(a.get("prioridad") or "media"),
                        esfuerzo=str(a.get("esfuerzo") or "medio"),
                        impacto=str(a.get("impacto") or "medio"),
                        plazo=str(a.get("plazo") or "30_dias"),
                        categoria=str(a.get("categoria") or "general"),
                    )
                )
        riesgos = []
        for r in parsed.get("riesgos") or []:
            if isinstance(r, dict):
                riesgos.append(
                    Riesgo(
                        titulo=str(r.get("titulo") or ""),
                        descripcion=str(r.get("descripcion") or ""),
                        probabilidad=str(r.get("probabilidad") or "media"),
                        impacto=str(r.get("impacto") or "medio"),
                        mitigacion=str(r.get("mitigacion") or ""),
                    )
                )
        return RespuestaAsesor(
            resumen_ejecutivo=str(parsed.get("resumen_ejecutivo") or ""),
            hallazgos=hallazgos,
            acciones=acciones,
            riesgos=riesgos,
            preguntas_para_aclarar=[str(x) for x in (parsed.get("preguntas_para_aclarar") or []) if x is not None],
            fuentes_usadas=[str(x) for x in (parsed.get("fuentes_usadas") or []) if x is not None],
            datos_usados={
                "workspace": contexto_datos.get("workspace"),
                "moneda": contexto_datos.get("moneda"),
                "num_alertas": len(contexto_datos.get("alertas") or []),
                "num_top_clientes": len(contexto_datos.get("top_clientes") or []),
            },
            modelo=self.modelo,
            proveedor=self.proveedor,
        )
