"""Pantalla de acceso: login, primer arranque y modo kiosco.

Es la unica pieza de la interfaz que se renderiza sin sesion. Tres caminos:

1. **OIDC** — si hay proveedor configurado en ``st.secrets["auth"]``, se delega
   en ``st.login()``, que gestiona la cookie firmada por su cuenta. Es la via
   recomendada en despliegues gestionados.
2. **Primer arranque** — si el registro esta vacio, se ofrece crear el admin.
   Bloqueado salvo que la app escuche solo en loopback o que el operador lo
   habilite con ``GIRO_AUTH_BOOTSTRAP=1``.
3. **Registro local** — usuario y contrasena contra ``config/usuarios.yaml``.

Kiosco (``?kiosco=1``) no pide credenciales: es la vista de demo sin
configuracion y sin permisos de escritura.
"""

from __future__ import annotations

import time

import streamlit as st

from src.core import auth
from ui import context

_ICONO = ":material/lock:"


def _titulo() -> None:
    # Sin hex fijo: el color hereda el del tema y la opacidad lo suaviza,
    # asi el subtitulo contrasta igual en claro y en oscuro.
    st.markdown(
        f"<div style='text-align:center;padding:1.5rem 0 .5rem'>"
        f"<div style='font-size:2.6rem'>{_ICONO}</div>"
        f"<h2 style='margin:.4rem 0 0'>Acceso a GIRO</h2>"
        f"<p style='color:inherit;opacity:.7;margin:.2rem 0 0'>"
        f"Inteligencia de negocio para tu empresa</p></div>",
        unsafe_allow_html=True,
    )


def _form_bootstrap() -> None:
    """Crea el primer usuario administrador."""
    st.warning(
        "No hay usuarios registrados. Crea el administrador para entrar.",
        icon=":material/person_add:",
    )
    with st.form("form_bootstrap", border=False):
        usuario = st.text_input("Usuario", placeholder="admin", autocomplete="username")
        nombre = st.text_input("Nombre a mostrar", placeholder="Nombre Apellido")
        clave1 = st.text_input("Contrasena", type="password", autocomplete="new-password")
        clave2 = st.text_input("Repetir contrasena", type="password",
                               autocomplete="new-password")
        if st.form_submit_button("Crear administrador", type="primary",
                                 icon=":material/admin_panel_settings:"):
            if not usuario.strip():
                st.error("Indica un nombre de usuario.")
            elif len(clave1) < 10:
                st.error("La contrasena debe tener al menos 10 caracteres.")
            elif clave1 != clave2:
                st.error("Las contrasenas no coinciden.")
            else:
                try:
                    nuevo = auth.crear_usuario(
                        usuario.strip(), clave1, nombre=nombre.strip() or usuario.strip(),
                        rol=auth.ROL_ADMIN)
                except ValueError as e:
                    st.error(str(e))
                else:
                    context.iniciar_sesion(nuevo)
                    st.rerun()


def _form_login() -> None:
    """Login contra el registro local."""
    with st.form("form_login", border=False):
        usuario = st.text_input("Usuario", placeholder="tu usuario",
                                autocomplete="username")
        clave = st.text_input("Contrasena", type="password",
                              autocomplete="current-password")
        if st.form_submit_button("Entrar", type="primary", icon=":material/login:"):
            usuario = usuario.strip()
            bloqueo = auth._bloqueado_hasta(usuario) if usuario else None
            if bloqueo:
                faltan = max(1, int(bloqueo - time.time()) // 60 + 1)
                st.error(f"Demasiados intentos fallidos. Prueba en {faltan} min.")
            elif not usuario or not clave:
                st.error("Completa usuario y contrasena.")
            else:
                usuario_ok, error = auth.autenticar(usuario, clave)
                if usuario_ok is None:
                    auth.registrar_intento(usuario)
                    st.session_state["auth_intento_usuario"] = usuario
                    st.error(error)
                else:
                    auth.limpiar_intentos(usuario)
                    context.iniciar_sesion(usuario_ok)
                    st.rerun()


def _boton_oidc() -> None:
    """Login delegando en el proveedor OIDC de st.secrets."""
    st.divider()
    st.caption("O continua con tu cuenta corporativa")
    if st.button("Entrar con SSO", type="primary", icon=":material/business:",
                 width="stretch"):
        st.login()
        st.rerun()


def pantalla_login() -> None:
    """Punto de entrada: deja la sesion lista o detiene el script."""
    _titulo()

    if not auth.cargar_registro():
        if auth.bootstrap_permitido():
            _form_bootstrap()
        else:
            st.error(
                "No hay usuarios registrados y la app esta expuesta a la red, "
                "asi que el alta automatica esta deshabilitada.",
                icon=":material/gpp_bad:",
            )
            st.code("python main.py usuarios crear <usuario> --admin", language="bash")
            st.caption("Despues, recarga esta pagina para entrar.")
        return

    _form_login()
    if auth.tiene_consola_oidc():
        _boton_oidc()

    with st.expander("Problemas para entrar?", icon=":material/help:"):
        st.markdown(
            "- **Contrasena olvidada**: un administrador puede resetearla con "
            "`python main.py usuarios password <usuario>`.\n"
            "- **Sin acceso a una empresa**: debe aparecer en tu lista de "
            "empresas permitidas; pidelo al administrador.\n"
            "- **Instalacion nueva**: crea el primer administrador con "
            "`python main.py usuarios crear <usuario> --admin`."
        )


def aviso_kiosco() -> None:
    """Banner de solo lectura del modo presentacion.

    Se muestra siempre que hay kiosco activo, sea quien sea la sesion. Antes
    se pedia ``visitante and not hay_sesion`` y el aviso desaparecia justo
    cuando entraba un usuario: con el demo ``GIRO_DEMO_USER``, con SSO o con
    la auth apagada el banner no salia nunca.
    """
    s = context.sesion()
    if s.es_admin:
        st.info(
            "**Modo presentacion** · viendo GIRO como lo veria un cliente: "
            "sin panel de administracion y sin escritura. Sal del modo para "
            "volver a tu sesion completa.",
            icon=":material/present_to_all:",
        )
    else:
        st.info(
            "**Modo presentacion** · vista de solo lectura. Los indicadores son "
            "de datos de ejemplo y no se puede modificar nada.",
            icon=":material/present_to_all:",
        )
