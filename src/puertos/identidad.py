"""Puerto de identidad federada (SSO / OIDC).

El nucleo (`src.core.auth`) necesita saber si la peticion trae una identidad
federada, pero no puede depender de ningun proveedor: `st.user` es de
Streamlit, y la API HTTP y el CLI no lo tienen (ni deben arrastrarlo). Este
puerto declara lo minimo que el nucleo pide: la identidad de la UI, si la hay.

El nucleo no instala nada: guarda el adaptador en su registro
(``src.core.auth.fijar_proveedor_identidad``) y, si nadie registro uno, no
busca identidad federada y se queda con el registro local. Quien implementa
este contrato es el adaptador de entrada correspondiente: en la UI es
``ui.login.IdentidadStreamlit``.

Si el metodo lanza, el nucleo lo trata como "federacion no disponible",
muestra el aviso correspondiente y cae al registro local: un error del IdP no
puede dejar a nadie sin entrar.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class PuertoIdentidad(Protocol):
    """Identidad federada de la peticion en curso."""

    def identidad_ui(self) -> Optional[dict]:
        """``{"email": ..., "nombre": ...}`` o ``None`` si no hay sesion federada.

        ``None`` tambien cubre el caso "no hay proveedor configurado": el
        llamador no debe distinguirlo, solo no continuar por la via OIDC.
        """
        ...


__all__ = ["PuertoIdentidad"]
