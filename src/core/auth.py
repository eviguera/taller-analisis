"""Autenticacion y autorizacion de GIRO (multiempresa).

GIRO se vende como producto white-label instalado en cada pyme, a veces en
redes sin salida a internet, asi que la identidad se resuelve contra un
registro local de usuarios con contraseñas con hash scrypt. No es un
"formulario de contraseña" comparada contra un string: hay usuarios
identificados, roles, y la sesion viaja en una cookie firmada con HMAC-SHA256
que el cliente no puede falsificar.

Capas, de la mas fuerte a la mas debil:

1. ``GIRO_AUTH=0`` desactiva la autenticacion por completo. Pensado solo para
   desarrollo local; solo tiene efecto si la app escucha en loopback.
2. Identidad real con ``st.user`` cuando hay un proveedor OIDC configurado
   (``st.secrets["auth"]``). Es la via recomendada en despliegues gestionados.
3. Registro local de usuarios con cookie firmada, para instalaciones on-prem
   sin proveedor de identidad.

Permisos
--------
- ``admin``: ve todos los workspaces, crea empresas, usa la consola SQL y
  publica el almacen en un SQL externo.
- ``cliente``: queda atado a los workspaces de su lista. No puede cambiar de
  empresa, crear empresas ni tocar la consola SQL.

El alcance se impone en el servidor (``workspace_permitido``), no ocultando
widgets: aunque alguien manipule el estado de sesion, la peticion se resuelve
contra el workspace permitido.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

log = logging.getLogger("taller.auth")

from ..workspaces import CLAVE_PRINCIPAL, PATRON_CLAVE, listar_workspaces, validar_clave

# ---------------------------------------------------------------------------
#  Constantes
# ---------------------------------------------------------------------------

# scrypt: N=2**15, r=8, p=1 -> ~64 MB y ~80 ms por verificacion.
# maxmem es obligatorio y va al doble del minimo teorico (128*N*r): OpenSSL
# reserva el bloque de mas, asi que con el valor exacto lanza
# "memory limit exceeded". Medido en Python 3.14, ver _self_test().
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SCRYPT_MAXMEM = 256 * _SCRYPT_N * _SCRYPT_R
_LONGPREFIJO = "scrypt$"

ROL_ADMIN = "admin"
ROL_CLIENTE = "cliente"
ROLES_VALIDOS = (ROL_ADMIN, ROL_CLIENTE)

# Permisos que no dependen del alcance de workspace.
PERMISO_CONSOLA_SQL = "consola_sql"
PERMISO_GESTIONAR_EMPRESAS = "gestionar_empresas"
PERMISO_CONECTORES = "conectores"
PERMISO_PUBLICAR_WAREHOUSE = "publicar_warehouse"
PERMISO_VER_TODAS_EMPRESAS = "ver_todas_empresas"

# Un ``cliente`` no hereda nada por defecto: los permisos de arriba se
# conceden por usuario en ``config/usuarios.yaml``::

#     - username: carmen
#       permisos: [publicar_warehouse, ver_todas_empresas]
#
# ``admin`` y el modo desarrollo los tienen todos sin figurar. Fuera de esta
# lista lo que se pida se descarga al leer el registro (una errata no puede
# dejar a nadie sin entrar ni abrir una puerta inesperada).
PERMISOS_VALIDOS = frozenset({
    PERMISO_CONSOLA_SQL, PERMISO_GESTIONAR_EMPRESAS, PERMISO_CONECTORES,
    PERMISO_PUBLICAR_WAREHOUSE, PERMISO_VER_TODAS_EMPRESAS,
})

_PERMISOS_CLIENTE = frozenset()

NOMBRE_COOKIE = "giro_sesion"
_EDICION_SESION_HORAS = 12
_MAX_INTENTOS = 5
_BLOQUEO_MINUTOS = 5
# Antiguedad maxima de una credencial para que el hash siga siendo aceptado.
_EDICION_CREDENCIAL_DIAS = 90

_RAIZ = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
#  Hash de contraseñas (scrypt, solo libreria estandar)
# ---------------------------------------------------------------------------

def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def hashear(password: str) -> str:
    """Devuelve ``scrypt$n$r$p$salt$hash`` para storing en texto plano."""
    if not password:
        raise ValueError("La contraseña no puede estar vacia")
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, maxmem=_SCRYPT_MAXMEM,
                        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN)
    return f"{_LONGPREFIJO}{_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64e(salt)}${_b64e(dk)}"


def verificar_hash(password: str, hash_guardado: str) -> bool:
    """Compara en tiempo constante. Falso si el hash esta mal formado."""
    if not password or not hash_guardado or not hash_guardado.startswith(_LONGPREFIJO):
        return False
    try:
        n, r, p, sal, esperado = hash_guardado[len(_LONGPREFIJO):].split("$")
        esperado_bytes = _b64d(esperado)
        dk = hashlib.scrypt(password.encode("utf-8"), salt=_b64d(sal),
                            maxmem=_SCRYPT_MAXMEM, n=int(n), r=int(r), p=int(p),
                            dklen=len(esperado_bytes))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk, esperado_bytes)


# ---------------------------------------------------------------------------
#  Firma de la cookie de sesion
# ---------------------------------------------------------------------------

def _clave_firma() -> bytes:
    """Secreto de firma: ``GIRO_AUTH_SECRET`` o, si falta, uno persistido local.

    El archivo alterno vive fuera de ``workspaces/`` y con permisos 0600, y se
    crea una sola vez. Sin el secreto, cada reinicio invalidaria las sesiones.
    """
    secreto = os.environ.get("GIRO_AUTH_SECRET", "").strip()
    if secreto:
        return secreto.encode("utf-8")
    ruta = _RAIZ / "data" / ".giro_auth_secret"
    if ruta.exists():
        return ruta.read_bytes().strip()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    valor = base64.urlsafe_b64encode(secrets.token_bytes(32))
    try:
        ruta.write_bytes(valor)
        ruta.chmod(0o600)
    except OSError:
        # Sistema de archivos de solo lectura: la sesion durara lo que el proceso.
        pass
    return valor


def firmar(datos: dict) -> str:
    """Serializa ``datos`` y lo firma: ``payload_b64.firma_b64``."""
    crudo = json.dumps(datos, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload = _b64e(crudo)
    firma = hmac.new(_clave_firma(), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{firma}"


def verificar(token: Optional[str]) -> Optional[dict]:
    """Valida firma y vigencia. Devuelve los datos o ``None``."""
    if not token or "." not in token:
        return None
    payload, _, firma = token.rpartition(".")
    esperada = hmac.new(_clave_firma(), payload.encode("ascii"),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(esperada, firma):
        return None
    try:
        datos = json.loads(_b64d(payload))
    except (ValueError, TypeError):
        return None
    if not isinstance(datos, dict):
        return None
    if float(datos.get("exp", 0)) < time.time():
        return None
    return datos


# ---------------------------------------------------------------------------
#  Modelo
# ---------------------------------------------------------------------------

@dataclass
class Usuario:
    """Usuario del registro local."""

    username: str
    nombre: str
    hash: str
    rol: str = ROL_CLIENTE
    # Workspaces a los que tiene acceso. Vacio = todos (solo admin).
    workspaces: List[str] = field(default_factory=list)
    # Permisos puntuales concedidos a esta cuenta (ver PERMISOS_VALIDOS).
    permisos: List[str] = field(default_factory=list)
    activo: bool = True
    email: str = ""

    def __post_init__(self) -> None:
        self.username = (self.username or "").strip()
        self.nombre = (self.nombre or self.username).strip()
        if self.rol not in ROLES_VALIDOS:
            raise ValueError(f"Rol desconocido: {self.rol!r}. Usa {ROLES_VALIDOS}.")
        self.workspaces = sorted({validar_clave(w) for w in (self.workspaces or [])})
        pedidos = [str(p).strip() for p in (self.permisos or [])]
        ignorados = sorted({p for p in pedidos if p and p not in PERMISOS_VALIDOS})
        if ignorados:
            log.warning("Permisos desconocidos en %s (ignorados): %s",
                        self.username, ", ".join(ignorados))
        self.permisos = sorted({p for p in pedidos if p in PERMISOS_VALIDOS})

    @property
    def es_admin(self) -> bool:
        return self.rol == ROL_ADMIN and self.activo

    def workspaces_permitidos(self) -> List[str]:
        """Claves visibles para este usuario ("" = todas)."""
        return [] if self.es_admin else list(self.workspaces)

    def es_dict_sensible(self) -> dict:
        return {"username": self.username, "nombre": self.nombre, "rol": self.rol,
                "workspaces": self.workspaces, "permisos": self.permisos,
                "activo": self.activo}


@dataclass
class Sesion:
    """Identidad de la peticion en curso."""

    usuario: Optional[Usuario] = None
    # Consultor de la landing publica: sin sesion, solo lectura y sin config.
    visitante: bool = False
    # True cuando la autenticacion esta desactivada (solo loopback).
    modo_abierto: bool = False
    # Credenciales que la UI debe poder modificar (alta de usuarios).
    gestion_usuarios: bool = False

    @property
    def hay_sesion(self) -> bool:
        return self.usuario is not None

    @property
    def es_admin(self) -> bool:
        return self.modo_abierto or (self.usuario is not None and self.usuario.es_admin)

    @property
    def etiqueta(self) -> str:
        if self.modo_abierto:
            return "desarrollo"
        if self.usuario:
            return self.usuario.nombre or self.usuario.username
        if self.visitante:
            return "visitante"
        return "—"

    @property
    def acceso_total(self) -> bool:
        """La sesion no esta acotada a una lista de empresas.

        ``admin`` y el modo desarrollo, o quien tenga concedido el permiso
        explicito ``ver_todas_empresas``. Para todos los demas la lista manda,
        y si esta vacia no hay acceso a ninguna empresa.
        """
        return self.es_admin or self.puede(PERMISO_VER_TODAS_EMPRESAS)

    def puede(self, permiso: str) -> bool:
        if self.modo_abierto or self.es_admin:
            return True
        if not self.hay_sesion:
            return False
        # Concesiones puntuales de la cuenta (usuarios.yaml -> permisos).
        return permiso in _PERMISOS_CLIENTE or permiso in (self.usuario.permisos or ())

    def workspaces_permitidos(self) -> List[str]:
        """Claves asignadas a la sesion.

        Ojo con la lista vacia: NO significa "todas". Solo ``acceso_total``
        significa "todas". Un ``cliente`` al que no se le ha asignado ninguna
        empresa no ve ninguna, que es el unico comportamiento seguro.
        """
        if self.acceso_total or self.usuario is None:
            return []
        return self.usuario.workspaces_permitidos()

    def visibles(self, todos: List[str]) -> List[str]:
        """Filtra la lista de workspaces a los que el usuario tiene acceso."""
        if self.acceso_total:
            return list(todos)
        permitidos = self.workspaces_permitidos()
        return [c for c in todos if c in permitidos]


# ---------------------------------------------------------------------------
#  Registro de usuarios
# ---------------------------------------------------------------------------

def ruta_registro() -> Path:
    """Ubicacion del registro, sobreescribible con ``GIRO_AUTH_USERS``."""
    return Path(os.environ.get("GIRO_AUTH_USERS") or (_RAIZ / "config" / "usuarios.yaml"))


def cargar_registro() -> Dict[str, Usuario]:
    """Lee el registro de usuarios. Archivo ausente = sin usuarios."""
    ruta = ruta_registro()
    if not ruta.exists():
        return {}
    try:
        raw = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    usuarios: Dict[str, Usuario] = {}
    for entrada in raw.get("usuarios") or []:
        if not isinstance(entrada, dict):
            continue
        username = (entrada.get("username") or "").strip()
        hash_guardado = str(entrada.get("hash") or "")
        if not username or not hash_guardado:
            continue
        try:
            usuarios[username] = Usuario(
                username=username,
                nombre=entrada.get("nombre") or username,
                hash=hash_guardado,
                rol=entrada.get("rol") or ROL_CLIENTE,
                workspaces=list(entrada.get("workspaces") or []),
                permisos=list(entrada.get("permisos") or []),
                activo=bool(entrada.get("activo", True)),
                email=entrada.get("email") or "",
            )
        except ValueError:
            # Entrada con rol o workspaces invalidos: se ignora en vez de tumbar
            # el arranque de la app.
            continue
    return usuarios


def guardar_registro(usuarios: Dict[str, Usuario]) -> None:
    """Vuelca el registro a disco con permisos 0600."""
    ruta = ruta_registro()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    contenido = {
        "usuarios": [
            {
                "username": u.username,
                "nombre": u.nombre,
                "email": u.email,
                "rol": u.rol,
                "workspaces": u.workspaces,
                "permisos": u.permisos,
                "activo": u.activo,
                "hash": u.hash,
            }
            for u in sorted(usuarios.values(), key=lambda x: x.username)
        ]
    }
    ruta.write_text(yaml.safe_dump(contenido, allow_unicode=True, sort_keys=False,
                                   default_flow_style=False), encoding="utf-8")
    try:
        ruta.chmod(0o600)
    except OSError as e:
        # El registro de usuarios debe quedar legible solo por su duenio:
        # si el chmod falla, que se vea en el log, no en silencio.
        log.warning("No se pudo restringir permisos de %s: %s", ruta, e)


def buscar_usuario(username: str) -> Optional[Usuario]:
    return cargar_registro().get((username or "").strip())


def crear_usuario(username: str, password: str, nombre: str = "",
                  rol: str = ROL_CLIENTE, workspaces: Optional[List[str]] = None,
                  email: str = "", activo: bool = True) -> Usuario:
    """Crea o reemplaza un usuario y persiste el registro."""
    if rol not in ROLES_VALIDOS:
        raise ValueError(f"Rol desconocido: {rol!r}. Usa {ROLES_VALIDOS}.")
    if len(password) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres.")
    usuarios = cargar_registro()
    clave = (username or "").strip()
    if not clave:
        raise ValueError("El nombre de usuario no puede estar vacio")
    usuario = Usuario(
        username=clave, nombre=nombre or clave, hash=hashear(password),
        rol=rol, workspaces=workspaces or [], activo=activo, email=email)
    usuarios[clave] = usuario
    guardar_registro(usuarios)
    return usuario


def actualizar_password(username: str, password: str) -> bool:
    if len(password) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres.")
    usuarios = cargar_registro()
    usuario = usuarios.get((username or "").strip())
    if usuario is None:
        return False
    usuario.hash = hashear(password)
    guardar_registro(usuarios)
    return True


def _hash_obsoleto(hash_guardado: str) -> bool:
    """True si el hash ya no usa los parametros de scrypt actuales.

    Detecta el caso "el coste subio y el hash viejo quedo barato de romper".
    """
    if not hash_guardado.startswith(_LONGPREFIJO):
        return True
    partes = hash_guardado[len(_LONGPREFIJO):].split("$")
    if len(partes) != 5:
        return True
    try:
        return (int(partes[0]), int(partes[1]), int(partes[2])) != (_SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    except ValueError:
        return True


def autenticar(username: str, password: str) -> Tuple[Optional[Usuario], Optional[str]]:
    """Verifica credenciales. Devuelve (usuario, error).

    Mismo mensaje para usuario inexistente y contraseña incorrecta, para no
    revelar que cuentas existen.
    """
    usuario = buscar_usuario(username)
    if usuario is None or not usuario.activo:
        # Se verifica un hash ficticio para que el tiempo de respuesta no
        # distinga "no existe" de "existe pero mala contraseña".
        verificar_hash(password or "", hashear(secrets.token_urlsafe(16)))
        return None, "Usuario o contraseña incorrectos."
    if not verificar_hash(password, usuario.hash):
        return None, "Usuario o contraseña incorrectos."
    if _hash_obsoleto(usuario.hash):
        # Hay que mutar el registro releido, no el objeto de esta llamada:
        # guardar_registro(cargar_registro()) rele el disco y volveria a
        # volcar el hash viejo, dejando la migracion sin efecto.
        registro = cargar_registro()
        if usuario.username in registro:
            registro[usuario.username].hash = hashear(password)
            try:
                guardar_registro(registro)
            except OSError as e:
                # El hash viejo quedara sin migrar en disco: no es fatal para la
                # sesion actual, pero hay que dejar constancia.
                log.warning("No se pudo persistir la migracion del hash de %s: %s",
                            usuario.username, e)
    return usuario, None


def hash_a_envejecer(hashes: List[str], dias: int = _EDICION_CREDENCIAL_DIAS) -> List[str]:
    """Hashes que conviene re-hashear. No puede fechado un hash, asi que la
    señal es la version del formato (parametros de scrypt)."""
    return [h for h in hashes if h and _hash_obsoleto(h)]


# ---------------------------------------------------------------------------
#  Control de intentos (en memoria: se reinicia con el proceso)
# ---------------------------------------------------------------------------

_intentos: Dict[str, List[float]] = {}


def _bloqueado_hasta(clave: str) -> Optional[float]:
    intentos = [t for t in _intentos.get(clave, []) if t > time.time() - _BLOQUEO_MINUTOS * 60]
    _intentos[clave] = intentos
    if len(intentos) >= _MAX_INTENTOS:
        return min(intentos) + _BLOQUEO_MINUTOS * 60
    return None


def registrar_intento(username: str) -> None:
    _intentos.setdefault((username or "").strip(), []).append(time.time())


def limpiar_intentos(username: str) -> None:
    _intentos.pop((username or "").strip(), None)


# ---------------------------------------------------------------------------
#  Politicas de exposicion
# ---------------------------------------------------------------------------

def _escucha_solo_loopback() -> bool:
    """True solo si el servidor esta realmente limitado a loopback.

    La direccion efectiva puede venir de tres sitios (flag
    ``--server.address``, ``[server] address`` en config.toml o la variable de
    entorno); mirar solo ``STREAMLIT_SERVER_ADDRESS`` dejaba ``GIRO_AUTH=0``
    desactivando la autenticacion aunque la app escuchara en 0.0.0.0. Ante la
    duda (config ilegible), se responde False: la autenticacion sigue puesta.
    """
    address = os.environ.get("STREAMLIT_SERVER_ADDRESS", "").strip()
    if not address:
        # Flag CLI (--server.address 0.0.0.0, el caso de entrypoint.sh):
        # se lee de argv porque st.config no siempre lo refleja en runtime.
        argv = sys.argv[1:]
        for i, arg in enumerate(argv):
            if arg == "--server.address" and i + 1 < len(argv):
                address = argv[i + 1].strip()
                break
            if arg.startswith("--server.address="):
                address = arg.split("=", 1)[1].strip()
                break
    if not address:
        try:
            import streamlit as st
            address = str(st.config.get_option("server.address") or "").strip()
        except Exception:  # noqa: BLE001  # sin runtime de Streamlit: duda = expuesta
            return False
    if not address:
        return True  # Streamlit solo escucha en loopback si no se define ADDRESS.
    if address in ("127.0.0.1", "localhost", "::1"):
        return True
    # 0.0.0.0 o una IP concreta: la app esta expuesta a la red.
    return False


def _flag(nombre: str, defecto: str = "0") -> bool:
    return os.environ.get(nombre, defecto).strip().lower() in ("1", "true", "si", "yes")


#: Streamlit no expone una API para escribir cookies, asi que la sesion vive en
#: ``st.session_state`` y se pierde al recargar el navegador (forzar F5). Es el
#: default por ser el mas seguro. Con ``GIRO_AUTH_PERSISTIR_URL=1`` el token se
#: ademas refleja en la query string para sobrevivir a la recarga, a cambio de
#: que queda en el historial del navegador y en las cabeceras ``Referer``.
PERSISTIR_URL = _flag("GIRO_AUTH_PERSISTIR_URL")
PARAM_URL = "giro_sesion"


def auth_activada() -> bool:
    """False solo si GIRO_AUTH=0 y la app no esta expuesta a la red."""
    flag = os.environ.get("GIRO_AUTH", "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return not _escucha_solo_loopback()
    return True


def bootstrap_permitido() -> bool:
    """Si la UI puede ofrecer crear el primer administrador.

    Solo en loopback, o si el operador lo fuerza con GIRO_AUTH_BOOTSTRAP=1
    (por ejemplo, el contenedor recien levantado al que se entra por tunel).
    """
    if _flag("GIRO_AUTH_BOOTSTRAP"):
        return True
    return _escucha_solo_loopback()


def _usuario_demo() -> Optional[Usuario]:
    """Usuario de solo lectura del modo kiosco, si se configuro uno."""
    username = os.environ.get("GIRO_DEMO_USER", "").strip()
    if not username:
        return None
    usuario = buscar_usuario(username)
    if usuario is None or not usuario.activo:
        return None
    return Usuario(username=usuario.username, nombre=usuario.nombre,
                   hash="", rol=ROL_CLIENTE, workspaces=list(usuario.workspaces),
                   # El kiosco es de solo lectura por diseno: el rol ya se
                   # rebaja a cliente y las concesiones puntuales no se
                   # heredan, ni aunque el operador apunte a una cuenta admin.
                   permisos=[])


def tiene_consola_oidc() -> bool:
    """True si hay un proveedor OIDC configurado en st.secrets."""
    try:
        import streamlit as st
        return bool(dict(st.secrets.get("auth") or {}))
    except Exception:  # noqa: BLE001  # st.secrets lanza si no hay secrets.toml
        return False


def inicio_de_sesion(token: Optional[str], modo_kiosco: bool = False) -> Sesion:
    """Construye la sesion de la peticion a partir de la cookie firmada."""
    if not auth_activada():
        return Sesion(modo_abierto=True)

    # 1) Identidad federada: gana sobre el registro local si esta configurada.
    #    st.user.is_logged_in solo existe cuando hay un proveedor OIDC en
    #    secrets; leerlo sin esa seccion lanza AttributeError en cada rerun,
    #    lo que colaba un warning de "identidad federada" por peticion.
    try:
        import streamlit as st
        if tiene_consola_oidc() and st.user.is_logged_in:
            claims = {"email": st.user.email or "", "nombre": st.user.name or ""}
            return _sesion_por_claims(claims)
    except Exception as e:  # noqa: BLE001
        # Si la federacion falla, se cae al registro local: un fallo silencioso
        # aqui dejaria al usuario sin saber por que su SSO no entra.
        log.warning("Identidad federada no disponible (%s); se usa el registro local",
                    type(e).__name__)

    # 2) Kiosco: visitante de solo lectura, nunca con permisos de escritura.
    if modo_kiosco:
        demo = _usuario_demo()
        if demo is not None:
            return Sesion(usuario=demo, visitante=True)
        return Sesion(visitante=True)

    # 3) Registro local.
    datos = verificar(token)
    if datos and datos.get("u"):
        usuario = buscar_usuario(str(datos["u"]))
        if usuario is not None and usuario.activo:
            # El alcance se relee del registro: revocar un workspace surte
            # efecto en la sesion siguiente, sin esperar a que caduque el token.
            return Sesion(usuario=usuario)
    return Sesion()


def _rol_por_claims(email: str) -> Optional[str]:
    """Rol segun ``GIRO_AUTH_ROLES``, un JSON ``{"<email|@dominio|*>": "admin"}``."""
    try:
        mapeo = json.loads(os.environ.get("GIRO_AUTH_ROLES", "{}") or "{}")
    except ValueError:
        return None
    if not isinstance(mapeo, dict):
        return None
    for patron, rol in mapeo.items():
        patron = str(patron).lower()
        if patron == "*" or patron == email or \
                (patron.startswith("@") and email.endswith(patron)):
            return str(rol)
    return None


def _sesion_por_claims(claims: dict) -> Sesion:
    """Resuelve un usuario OIDC contra el mapeo de roles y el registro local.

    Ser admin exige match explicito en ``GIRO_AUTH_ROLES``: la pertenencia al
    grupo del proveedor no concede administracion por si sola.

    El alcance de empresas NUNCA se deduce del simple hecho de tener el correo
    verificado, porque en multiempresa eso entregaria el portfolio completo a
    cualquiera que sesaque una cuenta en el IdP. Se hereda del registro local:
    un admin asigna con ``main.py usuarios acceso <email> --workspace <clave>``.
    Sin asignacion previa el usuario entra como cliente acotado al workspace
    publico de demostracion y no ve datos de ningun cliente.
    """
    email = (claims.get("email") or "").strip().lower()
    nombre = (claims.get("nombre") or "").strip()
    ident = email or "oidc"
    rol = _rol_por_claims(email)
    if rol == ROL_ADMIN:
        return Sesion(usuario=Usuario(username=ident, nombre=nombre or ident,
                                      hash="", rol=ROL_ADMIN))
    # Hereda el alcance del registro local si el correo ya esta dado de alta.
    registrado = buscar_usuario(ident)
    if registrado is not None and registrado.activo:
        return Sesion(usuario=Usuario(
            username=ident, nombre=nombre or registrado.nombre or ident,
            hash="", rol=ROL_CLIENTE, workspaces=registrado.workspaces,
            permisos=registrado.permisos))
    return Sesion(usuario=Usuario(username=ident, nombre=nombre or ident,
                                  hash="", rol=ROL_CLIENTE, workspaces=[]))


def emitir_cookie(usuario: Usuario) -> str:
    """Token de sesion para un usuario recien autenticado."""
    return firmar({"u": usuario.username, "rol": usuario.rol,
                   "iat": int(time.time()),
                   "exp": int(time.time()) + _EDICION_SESION_HORAS * 3600})


# ---------------------------------------------------------------------------
#  Alcance de workspace (imposicion en servidor, no ocultamiento en la UI)
# ---------------------------------------------------------------------------

def workspace_permitido(sesion: Sesion, solicitado: str) -> str:
    """Resuelve el workspace efectivo de la peticion.

    A un ``cliente`` se le fuerza a uno de sus workspaces aunque el estado de
    sesion diga otro: es el control que impide el salto entre empresas. Si no
    tiene ninguno asignado, cae al workspace publico de demostracion; nunca
    a una empresa real.
    """
    pedido = validar_clave(solicitado) if solicitado else ""
    if sesion.acceso_total:
        return pedido or CLAVE_PRINCIPAL
    permitidos = sesion.workspaces_permitidos()
    if pedido and pedido in permitidos:
        return pedido
    return permitidos[0] if permitidos else CLAVE_PRINCIPAL


def workspaces_visibles(sesion: Sesion) -> List[str]:
    """Catalogo que la sesion puede ver.

    ``principal`` se une siempre porque no es un tenant: es el workspace por
    defecto que resuelve contra ``data/`` y ``config/config.yaml`` de la raiz,
    es decir el dataset de demostracion. El modo kiosco ya lo sirve sin
    autenticacion, asi que agregarlo aqui no expone nada nuevo, y sirve para
    que cualquiera vea el producto con datos de ejemplo.

    Invariante: ``data/`` de la raiz es publico por diseno. Los datos de un
    cliente van SIEMPRE en ``workspaces/<clave>/data/``.
    """
    return sorted(set(sesion.visibles(listar_workspaces())) | {CLAVE_PRINCIPAL})


__all__ = [
    "ROL_ADMIN", "ROL_CLIENTE", "PERMISO_CONSOLA_SQL", "PERMISO_GESTIONAR_EMPRESAS",
    "PERMISO_CONECTORES", "PERMISO_PUBLICAR_WAREHOUSE", "PERMISO_VER_TODAS_EMPRESAS",
    "PERMISOS_VALIDOS",
    "NOMBRE_COOKIE", "PATRON_CLAVE", "PERSISTIR_URL", "PARAM_URL",
    "Usuario", "Sesion", "autenticar", "auth_activada", "inicio_de_sesion",
    "emitir_cookie", "workspace_permitido", "workspaces_visibles",
    "crear_usuario", "actualizar_password", "cargar_registro", "guardar_registro",
    "ruta_registro", "buscar_usuario", "tiene_consola_oidc", "hash_a_envejecer",
    "verificar_hash", "hashear", "firmar", "verificar",
]
