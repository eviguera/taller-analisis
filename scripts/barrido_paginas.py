"""Barrera de las paginas del dashboard con AppTest.

Versionada por la spec de cierre del review (issue #2): es el criterio de
"13 casos en verde" (el shell del dashboard + las 12 paginas registradas en
``PAGINAS``) y se ejecuta al cierre de cada fase.

No es un unittest (fuera del patron ``test*.py``): se queda fuera de la suite
para no alargarla, pero vive en el repo y cualquiera puede lanzarla.

Uso:
    .venv/bin/python scripts/barrido_paginas.py              # todas
    .venv/bin/python scripts/barrido_paginas.py datos alertas
    .venv/bin/python scripts/barrido_paginas.py --kiosco     # ?kiosco=1

Sale con 1 si alguna pagina lanza excepcion.
"""

import glob
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

# El token de URL solo se atiende si el interruptor esta puesto, y auth lo lee
# al importarse: hay que fijarlo antes de importar nada.
os.environ.setdefault("GIRO_AUTH_PERSISTIR_URL", "1")

import streamlit.testing.v1 as at  # noqa: E402

from src.core import auth  # noqa: E402

TIEMPO = 120


def paginas_disponibles():
    """Modulos de ``ui/pages`` con ``principal()``, sin los helpers privados."""
    encontradas = []
    for ruta in sorted(glob.glob(os.path.join(REPO, "ui", "pages", "*.py"))):
        clave = os.path.basename(ruta)[:-3]
        if clave.startswith("_") or clave == "__init__":
            continue
        encontradas.append(clave)
    return encontradas


def _script_de(clave):
    return (
        "import sys\n"
        f"sys.path.insert(0, {REPO!r})\n"
        f"from ui.pages import {clave}\n"
        f"{clave}.principal()\n"
    )


def _barrer_dashboard(token, kiosco=False):
    """El shell (ui/app.py): sidebar, marca, wizard y navegacion."""
    prueba = at.AppTest.from_file(str(os.path.join(REPO, "dashboard.py")),
                                  default_timeout=TIEMPO)
    prueba.query_params[auth.PARAM_URL] = token
    if kiosco:
        prueba.query_params["kiosco"] = "1"
    try:
        prueba.run()
        return _excepciones(prueba)
    except Exception as e:  # noqa: BLE001 — el barrido reporta, no decide
        return [f"{type(e).__name__}: {e}"]


def _excepciones(prueba):
    return [f"{type(e.value).__name__}: {e.value}" for e in prueba.exception]


def barrer(claves, kiosco=False):
    token = auth.emitir_cookie(auth.cargar_registro()["ana"])
    # El shell primero: es la cara que el usuario ve y por donde entra la
    # navegacion (13 casos en total, 12 paginas + dashboard).
    resultado = [("dashboard", _barrer_dashboard(token, kiosco))]
    for clave in claves:
        with tempfile.NamedTemporaryFile(
            "w", suffix=f"_{clave}.py", dir=tempfile.gettempdir(), delete=False
        ) as fichero:
            fichero.write(_script_de(clave))
            ruta = fichero.name
        try:
            prueba = at.AppTest.from_file(ruta, default_timeout=TIEMPO)
            prueba.query_params[auth.PARAM_URL] = token
            if kiosco:
                prueba.query_params["kiosco"] = "1"
            prueba.run()
            fallos = _excepciones(prueba)
        except Exception as e:  # noqa: BLE001 — el barrido reporta, no decide
            fallos = [f"{type(e).__name__}: {e}"]
        finally:
            try:
                os.unlink(ruta)
            except OSError:
                pass
        resultado.append((clave, fallos))
    return resultado


def main(argv):
    kiosco = "--kiosco" in argv
    pedidas = [a for a in argv if not a.startswith("-")]
    claves = pedidas or paginas_disponibles()
    if not claves:
        print("sin paginas que barrer")
        return 1

    print(f"Barrido: {len(claves)} pagina(s) + dashboard"
          f"{' (kiosco)' if kiosco else ''}...")
    resultado = barrer(claves, kiosco=kiosco)
    rotos = 0
    for clave, fallos in resultado:
        if fallos:
            rotos += 1
            print(f"  FAIL {clave}: {'; '.join(fallos)}")
        else:
            print(f"  ok   {clave}")
    print(f"Resumen: {len(resultado) - rotos}/{len(resultado)} en verde")
    return 1 if rotos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
