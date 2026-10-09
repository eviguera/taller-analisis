"""Pagina: Datos y Configuracion (asistente de importacion + integracion PSPP)."""

import contextlib
from pathlib import Path

import pandas as pd
import streamlit as st

from src.core.catalog import escanear_directorio, clasificar_archivo, vincular_archivos_a_datasets
from src.core import auth
from src.core.conector_sql import mensaje_error
from src.loaders import get_loader
from src.loaders.pspp_loader import exportar_sav

from ui import components as c
from ui.context import (cargar_datos, exigir, exigir_escritura, obtener_config,
                        obtener_estado, sesion)
from src.core.calidad import resumen as resumen_calidad

# Cuota por archivo en la subida: corta un fichero gigante. Va de la mano
# con server.maxUploadSize (200 MB por defecto), asi que por si sola no
# frena nada que el servidor no rechace ya.
LIMITE_SUBIDA_BYTES = 200 * 1024 * 1024
# Cuota acumulada del workspace: sin ella, N ficheros pequenos o subidas
# repetidas llenarian el disco del contenedor, que todos los tenants
# comparten. Es la que de verdad protege el disco compartido.
CUOTA_WORKSPACE_BYTES = 1024 * 1024 * 1024

EJEMPLOS_SQL = {
    "Facturas recientes": "SELECT * FROM facturas LIMIT 10",
    "Top clientes por gasto": "SELECT nombre, SUM(total) AS gasto FROM facturas GROUP BY nombre ORDER BY gasto DESC LIMIT 10",
    "Vehiculos por marca": "SELECT marca, COUNT(*) AS vehiculos FROM vehiculos GROUP BY marca ORDER BY vehiculos DESC",
    "Facturas por estado": "SELECT estado, SUM(total) AS monto, COUNT(*) AS facturas FROM facturas GROUP BY estado",
}


def _aplicar_ejemplo_sql():
    etiqueta = st.session_state.get("sql_ejemplo_lbl")
    st.session_state["sql_consulta"] = EJEMPLOS_SQL.get(etiqueta, "")


def _mostrar_calidad(calidad) -> None:
    """Bloque de calidad de datos tras un ETL (reglas por campo).

    Patron plano de gchq-data-quality: un resumen con cuantas reglas cumplen
    y, si algo falla, la tabla con las reglas que no pasan y su tasa. Nada
    de esconder los falles detras de un "OK".
    """
    if calidad is None or calidad.empty:
        return
    res = resumen_calidad(calidad)
    fallas = calidad[calidad["estado"] != "OK"]
    if fallas.empty:
        st.caption(f":material/verified: Calidad de datos: **{res['ok']}** reglas "
                   "sobre los datasets cargados, todas cumplen.")
        return
    st.warning(
        f":material/rule: Calidad de datos: **{res['revisar'] + res['error']}** de "
        f"**{res['total']}** reglas no se cumplen.")
    st.dataframe(
        fallas, width="stretch", hide_index=True,
        column_config={
            "evaluadas": st.column_config.NumberColumn("Evaluadas"),
            "cumplen": st.column_config.NumberColumn("Cumplen"),
            "tasa": st.column_config.NumberColumn("Tasa", format="percent"),
            "estado": st.column_config.TextColumn("Estado"),
        },
    )


def _pestana(tab):
    """Context manager no-op si la pestana no se creo para este rol."""
    return tab if tab is not None else contextlib.nullcontext()


def _mismo_contenido(ruta: Path, contenido) -> bool:
    """True si el fichero en disco ya es byte a byte el contenido subido.

    Se compara por bloques: cargar un fichero de 200 MB entero en RAM solo
    para descartar una reescritura seria mas caro que el propio guardado.
    """
    bloque = 1 << 20
    with open(ruta, "rb") as f:
        for inicio in range(0, len(contenido), bloque):
            if f.read(bloque) != bytes(contenido[inicio:inicio + bloque]):
                return False
        return f.read(1) == b""


def _guardar_subidas(subidos, destino_dir: Path, excluidos=frozenset()):
    """Guarda las subidas en el workspace, solo si su contenido cambio.

    El ``file_uploader`` conserva los ficheros mientras la pestana esta
    abierta y el bloque que lo envuelve se re-ejecuta en cada rerun:
    reescribirlos a ciegas movia el mtime de los originales, la firma de
    ``cargar_datos`` cambiaba siempre y la cache se invalidaba a si misma
    en bucle, recargando todo justo en la pantalla de importacion.

    Devuelve ``(guardados, sin_cambios, por_archivo, por_cuota)``.
    ``por_archivo`` corta un fichero mayor que el limite individual;
    ``por_cuota`` frena el acumulado del directorio de datos del workspace
    contra ``CUOTA_WORKSPACE_BYTES``. Los ficheros de ``excluidos`` (el
    almacen DuckDB y su WAL) no cuentan en la cuota: son derivados, no los
    sube nadie, y comerian la cuota del tenant sin motivo.
    """
    destino_dir = Path(destino_dir)
    destino_dir.mkdir(parents=True, exist_ok=True)
    guardados = sin_cambios = por_archivo = por_cuota = 0
    ocupado = sum(f.stat().st_size for f in destino_dir.iterdir()
                  if f.is_file() and f.name not in excluidos)
    for up in subidos:
        tam = up.size or 0
        if tam > LIMITE_SUBIDA_BYTES:
            por_archivo += 1
            continue
        if ocupado + tam > CUOTA_WORKSPACE_BYTES:
            por_cuota += 1
            continue
        # .name descarta cualquier ruta que traiga el nombre subido
        # ("../../x"): el archivo tiene que caer dentro del directorio
        # del workspace y de ningun otro sitio.
        destino = destino_dir / Path(up.name).name
        contenido = up.getbuffer()
        if (destino.exists() and destino.stat().st_size == tam
                and _mismo_contenido(destino, contenido)):
            sin_cambios += 1
            continue
        destino.write_bytes(contenido)
        ocupado += tam
        guardados += 1
    return guardados, sin_cambios, por_archivo, por_cuota


def _plural(n: int) -> str:
    """Sufijo plural (\"s\") para los recuentos del copy: evita \"1 archivo(s)\"."""
    return "" if n == 1 else "s"


def _css_estructura() -> None:
    """Reparaciones estructurales de accesibilidad de la pagina.

    Foco visible explicito, targets de accion de 44px y prosa ancha a 65ch.
    Va en CSS porque Streamlit no expone esos ajustes como widgets; el
    contraste lo hereda del tema (modo claro/oscuro) y el salto al contenido
    (skip-link) depende del shell de la app, no de esta pantalla.
    """
    try:
        oscuro = st.context.theme.type == "dark"
    except Exception:  # noqa: BLE001 (st.context fuera de runtime: se asume claro)
        oscuro = False
    contorno = "#60a5fa" if oscuro else "#2563eb"
    st.markdown(
        f"""
<style>
/* Foco visible explicito en todo lo interactivo (AA). */
a:focus-visible, button:focus-visible, input:focus-visible,
textarea:focus-visible, select:focus-visible, [role="tab"]:focus-visible {{
    outline: 3px solid {contorno};
    outline-offset: 2px;
}}
/* Targets de accion >= 44px: botones, descargas y envios de formulario. */
[data-testid="stButton"] button,
[data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button {{
    min-height: 44px;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}}
[data-testid="stButton"] button:hover:not(:disabled),
[data-testid="stDownloadButton"] button:hover,
[data-testid="stFormSubmitButton"] button:hover {{
    transform: translateY(-1px);
    box-shadow: 0 4px 10px rgba(15, 23, 42, 0.18);
}}
/* Prosa larga a 65ch; tablas y graficos van a todo el ancho. */
[data-testid="stMarkdownContainer"] p {{
    max-width: 65ch;
}}
</style>
""",
        unsafe_allow_html=True,
    )


def principal():
    _css_estructura()
    cfg, data, analyzer, predictor = obtener_estado()
    c.cabecera(
        "Mis datos",
        "Importa tus datos (CSV, Excel o PSPP), verifica calidad y procesa el ETL",
        icono=":material/database:",
    )

    # Conectores y consola SQL son de administracion: las pestanas no se crean
    # para quien no tiene el permiso. El permiso igual se vuelve a comprobar
    # dentro de ui.context, porque ocultar la pestana no protege la operacion.
    s = sesion()
    puede_conectores = s.puede(auth.PERMISO_CONECTORES)
    puede_sql = s.puede(auth.PERMISO_CONSOLA_SQL)

    titulos = ["Importar / detectar", "Procesar (ETL)", "Esquema de datos",
               "Calidad de datos", "Integracion PSPP/SPSS"]
    if puede_conectores:
        titulos.append("Conectores ERP/SQL")
    if puede_sql:
        titulos.append("Consultas SQL")

    tabs = st.tabs(titulos, key="tabs_datos", on_change="rerun")
    tab_importar, tab_etl, tab_esquema, tab_calidad, tab_pspp = tabs[:5]
    tab_conectores = tabs[5] if puede_conectores else None
    tab_sql = tabs[5 + int(puede_conectores)] if puede_sql else None

    if not puede_conectores or not puede_sql:
        st.info(
            "Estas funciones son de administracion. "
            "Pide a un administrador que te otorgue acceso.",
            icon=":material/admin_panel_settings:",
        )

    # ---------------------------------------------------------------
    #  PESTAÑA: IMPORTAR / DETECTAR
    # ---------------------------------------------------------------
    with tab_importar:
        if tab_importar.open:
            with st.container(border=True):
                st.markdown("**Ubicacion de los datos**")
                data_dir = st.text_input(
                    "Directorio de datos", value=str(cfg.directorio_datos),
                    label_visibility="collapsed",
                )
                st.caption("Los archivos de este directorio se detectan automaticamente: "
                           "CSV, Excel (.xlsx), PSPP (.sav/.zsav/.por).")

            directorio = Path(data_dir)
            permitido = Path(cfg.directorio_datos).resolve()
            if not directorio.resolve().is_relative_to(permitido):
                st.error("El directorio debe estar dentro del workspace actual.")
                return

            with st.container(border=True):
                st.markdown("**Subir archivos**")
                subidos = st.file_uploader(
                    "Arrastra o selecciona archivos",
                    type=["csv", "tsv", "xlsx", "xls", "sav", "zsav", "por", "parquet"],
                    accept_multiple_files=True,
                    help="Puedes cargar los archivos que exporta PSPP (.sav, .por) o hojas de calculo.",
                )
                if subidos:
                    exigir_escritura(
                        "Solo un administrador puede importar archivos en el workspace.")
                    destino_dir = Path(cfg.directorio_datos)
                    # El almacen DuckDB y su WAL son derivados, no subidos:
                    # no deben comerse la cuota del workspace.
                    db = Path(cfg.db_path).name
                    with st.spinner("Guardando archivos en tu directorio de datos…"):
                        guardados, sin_cambios, por_archivo, por_cuota = _guardar_subidas(
                            subidos, destino_dir, excluidos={db, f"{db}.wal", f"{db}.tmp"})
                    if por_archivo:
                        st.warning(
                            f"Límite por archivo ({LIMITE_SUBIDA_BYTES // (1024 * 1024)} MB): "
                            f"{c.miles(por_archivo)} archivo{_plural(por_archivo)} "
                            f"no guardado{_plural(por_archivo)}.")
                    if por_cuota:
                        st.warning(
                            f"Cuota del workspace ({CUOTA_WORKSPACE_BYTES // (1024 * 1024)} MB): "
                            f"{c.miles(por_cuota)} archivo{_plural(por_cuota)} "
                            f"no guardado{_plural(por_cuota)}.")
                    if guardados:
                        st.success(
                            f"{c.miles(guardados)} archivo{_plural(guardados)} "
                            f"guardado{_plural(guardados)} en tu directorio de datos.")
                    elif sin_cambios:
                        st.info("Los archivos subidos ya estaban guardados y sin cambios.")

            st.space("small")
            st.markdown("**Archivos detectados**")
            archivos = escanear_directorio(directorio)
            if archivos:
                filas = []
                for a in archivos:
                    dataset, score = (clasificar_archivo(a.ruta, a.formato) if a.dataset_estimado is None
                                      else (a.dataset_estimado, None))
                    filas.append({
                        "Archivo": a.nombre,
                        "Formato": c.formato_archivo(a.formato),
                        "Tamano (KB)": a.tamaño_kb,
                        "Dataset detectado": dataset or "?",
                        "Confianza": score if score is None else f"{score:.0%}",
                    })
                st.dataframe(pd.DataFrame(filas), width="stretch", height=250, column_config={
                    "Tamano (KB)": st.column_config.NumberColumn("Tamano (KB)"),
                })
            else:
                c.vacio(
                    "No hay archivos de datos en este directorio.",
                    icono=":material/folder_off:",
                    detalle="Sube un CSV, Excel o .sav en «Subir archivos» y aparecerán aquí.",
                )

            st.space("small")
            st.markdown("**Mapeo automatico de datasets**")
            asignaciones = vincular_archivos_a_datasets(archivos, cfg)
            if asignaciones:
                mapa = [{"Dataset": d, "Archivo": p.name} for d, p in asignaciones.items()]
                st.dataframe(pd.DataFrame(mapa), width="stretch")
            else:
                st.warning("No se pudo asociar archivos a los datasets canonicos. "
                           "Revisa el mapeo de columnas.")

    # ---------------------------------------------------------------
    #  PESTAÑA: PROCESAR (ETL)
    # ---------------------------------------------------------------
    with tab_etl:
        if tab_etl.open:
            with st.container(border=True):
                st.markdown("**Ejecutar pipeline de datos (ETL)**")
                st.caption("Carga los archivos detectados, normaliza columnas y tipos, "
                           "y registra las tablas en DuckDB (almacen analitico).")
                if st.button("Procesar datos ahora", type="primary", icon=":material/play_arrow:"):
                    from ui.context import ejecutar_etl_ui
                    # El ETL reescribe los datos y el almacen del workspace:
                    # el permiso se comprueba aqui, no solo con ocultar la pestana.
                    exigir_escritura()
                    with st.status("Procesando datos (ETL)...", expanded=False) as estado:
                        resultado = ejecutar_etl_ui()
                    if resultado.ok:
                        tabla_info = " · ".join(
                            f"**{k}**: {c.miles(v)} filas" for k, v in resultado.tablas_registradas.items())
                        estado.update(label="ETL completado", state="complete", expanded=False)
                        st.success(f"ETL completado en {resultado.tiempo_carga}s. "
                                   f"Tablas registradas: {tabla_info}")
                        c.kpi_grid([
                            ("ETL total", f"{resultado.tiempo_carga}s", None, None,
                             "Tiempo completo del pipeline (carga + esquema + vistas)"),
                            ("Estructura DuckDB", f"{resultado.tiempo_estructura*1000:.0f} ms",
                             None, None, "Materializacion del esquema core y vistas analitica"),
                            ("Tablas core", f"{c.miles(len(resultado.estructura))}", None, None,
                             "Tablas normalizadas con claves primarias/foraneas"),
                            ("Vistas analitica", f"{c.miles(resultado.n_vistas)}", None, None,
                             "Modelos dimensionales listos para los paneles"),
                        ])
                        if resultado.estructura:
                            st.caption(":material/hub: Esquema `core` normalizado con claves · "
                                       f"ha creado **{len(resultado.estructura)}** tablas y "
                                       f"**{resultado.n_vistas}** vistas en `analitica`.")
                        for nombre, adv in resultado.advertencias.items():
                            st.warning(f":material/warning: **{nombre}**: {adv}")
                        _mostrar_calidad(resultado.calidad)
                    else:
                        estado.update(label="ETL termino con errores", state="error", expanded=True)
                        st.error("El ETL termino con errores:")
                        for nombre, err in resultado.errores.items():
                            st.write(f"- **{nombre}**: {err}")

            st.space("small")
            st.markdown("**Descargar datos procesados**")
            datasets = list(data.keys())
            sel = st.pills(
                "Dataset", datasets, key="dl_dataset",
                default=datasets[0] if datasets else None, selection_mode="single",
                label_visibility="collapsed",
            )
            if sel and not data.get(sel, pd.DataFrame()).empty:
                c.descargar(data[sel], sel)

            st.space("small")
            st.markdown("**Exportar a PSPP desde la interfaz**")
            if st.button("Exportar todos los datasets a .sav",
                         icon=":material/ios_share:",
                         help="Genera los .sav en el subdirectorio export de tus datos."):
                out = Path(cfg.directorio_datos) / "export"
                out.mkdir(parents=True, exist_ok=True)
                exportados = 0
                fallos = {}
                with st.spinner("Exportando datasets a .sav…"):
                    for nombre, df in data.items():
                        if df.empty:
                            continue
                        try:
                            exportar_sav(df, out / f"{nombre}.sav", label_archivo=f"{nombre} exportado")
                            exportados += 1
                        except Exception as e:  # noqa: BLE001
                            fallos[nombre] = str(e)
                for nombre, err in fallos.items():
                    st.warning(f"{nombre}: no se pudo exportar ({err})")
                if exportados:
                    st.success(
                        f"{c.miles(exportados)} dataset{_plural(exportados)} "
                        f"exportado{_plural(exportados)} a `{out}`.")
                elif not fallos:
                    st.info("No hay datasets con datos que exportar.")

            st.space("small")
            st.markdown("**Exportar analitica completa a PSPP**")
            st.caption("Incluye los datasets y las vistas analiticas "
                       "(ingresos por vehiculo, RFM, churn, demanda, ...) como .sav.")
            if st.button("Exportar datasets + analitica a .sav",
                         icon=":material/ios_share:",
                         help="Genera .sav de datasets y vistas en data/export/"):
                from ui.context import exportar_analitica_pspp
                out = Path(cfg.directorio_datos) / "export"
                with st.status("Exportando datasets y analitica a PSPP...", expanded=False) as estado:
                    exportados, errores = exportar_analitica_pspp(out)
                if not errores:
                    estado.update(label="Exportacion completa", state="complete", expanded=False)
                    st.success(f"Exportados **{len(exportados)}** objetos .sav a `{out}`")
                else:
                    estado.update(label="Exportacion con errores", state="error", expanded=True)
                    st.success(f"Exportados: {', '.join(exportados)}")
                    st.warning(f"Con errores en: {', '.join(errores)}")

    # ---------------------------------------------------------------
    #  PESTAÑA: ESQUEMA DE DATOS (almacen normalizado DuckDB)
    # ---------------------------------------------------------------
    with tab_esquema:
        if tab_esquema.open:
            st.markdown("**Modelo del almacen analitico (DuckDB)**")
            st.caption("El ETL carga los datos en `core` (tablas normalizadas con claves) "
                       "y crea vistas listas para el analisis en `analitica`.")

            try:
                from ui.context import obtener_estructura, consultar_vista
                catalogo = obtener_estructura()
                col1, col2 = st.columns([1, 1.2], vertical_alignment="center")
                with col1:
                    with c.panel("Catalogo de objetos", "Tablas y vistas del almacen",
                                 icono=":material/hub:"):
                        if not catalogo.empty:
                            esquema_total = catalogo.groupby(["esquema", "tipo"]).size().reset_index(
                                name="objetos")
                            st.dataframe(esquema_total, width="stretch")
                        else:
                            c.vacio(
                                "Aún no hay objetos en el almacén.",
                                icono=":material/hub:",
                                detalle="Procesa el ETL para crear las tablas y vistas.",
                            )
                with col2:
                    with c.panel("Objetos por esquema", "Estructura detallada",
                                 icono=":material/schema:"):
                        st.dataframe(catalogo, width="stretch", height=260)

                vistas = catalogo[catalogo["tipo"] == "VIEW"]["objeto"].tolist() if not catalogo.empty else []
                if vistas:
                    st.space("small")
                    st.markdown("**Explorar vistas analiticas**")
                    vista = st.selectbox("Vista analitica", ["-- selecciona --"] + vistas,
                                         key="vista_analitica")
                    if vista != "-- selecciona --":
                        with c.panel(f"Vista: {vista}", "Resultado del modelo dimensional",
                                     icono=":material/table_view:"):
                            st.dataframe(consultar_vista(vista), width="stretch", height=320)
            except Exception as e:  # noqa: BLE001
                c.vacio(
                    "Aún no hay almacén analítico.",
                    icono=":material/storage:",
                    detalle=f"Procesa el ETL en la pestaña «Procesar (ETL)». Detalle técnico: {e}",
                )

    # ---------------------------------------------------------------
    #  PESTAÑA: CALIDAD DE DATOS
    # ---------------------------------------------------------------
    with tab_calidad:
        if tab_calidad.open:
            st.markdown("**Salud de los datos (nulos, duplicados, tipos)**")
            from ui.context import resumen_calidad
            calidad = resumen_calidad(data)
            if data:
                for nombre, resumen in calidad.items():
                    df = data.get(nombre, pd.DataFrame())
                    if df.empty:
                        st.warning(f"**{nombre}**: sin datos disponibles.")
                        continue
                    n_nulos = sum(resumen["nulos"].values()) if resumen["nulos"] else 0
                    with st.expander(f"**{nombre}** · {c.miles(len(df))} filas · {len(df.columns)} cols",
                                     icon=":material/database:"):
                        st.markdown(
                            " ".join([
                                c.badge(f"{c.miles(len(df))} filas", "azul"),
                                c.badge(f"{n_nulos} nulos", "verde" if n_nulos == 0 else "amarillo"),
                                c.badge(f"{resumen['duplicados']} duplicados",
                                        "verde" if resumen["duplicados"] == 0 else "rojo"),
                            ])
                        )
                        if resumen["nulos"]:
                            st.markdown("**Columnas con nulos:**")
                            st.dataframe(pd.DataFrame(list(resumen["nulos"].items()),
                                                      columns=["Columna", "Nulos"]), width="stretch")
                        if resumen["tipos"]:
                            st.markdown("**Tipos de columna:**")
                            st.dataframe(pd.DataFrame(list(resumen["tipos"].items()),
                                                      columns=["Columna", "Tipo"]), width="stretch")
                        st.markdown("**Vista previa**")
                        st.dataframe(df.head(10), width="stretch")
            else:
                c.vacio(
                    "Aún no hay datos que revisar.",
                    icono=":material/rule:",
                    detalle="Procesa el ETL en la pestaña «Procesar (ETL)» para evaluar "
                            "nulos, duplicados y tipos de columna.",
                )

    # ---------------------------------------------------------------
    #  PESTAÑA: INTEGRACION PSPP
    # ---------------------------------------------------------------
    with tab_pspp:
        if tab_pspp.open:
            st.markdown("## Integracion con PSPP / SPSS")
            st.markdown("""
El sistema trabaja con **CSV + PSPP a la vez**: si en `data/` hay un archivo
`.sav`/`.por` para un dataset, el ETL puede usarlo en lugar del CSV (o como
complemento). Formatos soportados:
- **.sav** - archivo de datos de SPSS/PSPP (recomendado)
- **.zsav** - version comprimida
- **.por** - formato portable (max 8 chars por nombre de variable)

Cuando cargas un `.sav`, tambien se importan las **etiquetas de variables y de
valores** (p. ej. `estado: 1=Pagada, 2=Pendiente`), de forma que el analisis
muestra textos legibles en lugar de numeros.
            """)

            st.markdown("### Variables disponibles en la analitica")
            st.markdown("""
La vista **`analitica.ingresos_por_vehiculo`** agrega los ingresos por vehiculo:
`marca`, `modelo`, `placa`, `anio`, `facturas`, `ingresos`, `ultima_visita`.
Se exporta a `.sav` con el boton **"Exportar datasets + analitica a .sav"**
de la pestana *Procesar (ETL)*.
            """)

            with st.expander("Como exportar tus datos desde PSPP a .sav?",
                             icon=":material/quiz:"):
                st.markdown("""
1. Abre tu data en PSPP (`File > Open`).
2. Haz clic en **File > Export** o usa la sintaxis:

   ```sps
   SAVE OUTFILE='C:/mis_datos/facturas.sav'.
   ```

3. Copia el archivo `.sav` a la carpeta `data/` del proyecto
   (o subelo con el boton de subida).
4. En este sistema, procesa los datos (ETL) y listo.
                """)

            sav_archivos = [a for a in escanear_directorio(Path(cfg.directorio_datos))
                            if a.formato in ("sav", "zsav", "por")]
            if sav_archivos:
                st.markdown("**Archivos PSPP detectados**")
                for a in sav_archivos:
                    try:
                        loader = get_loader(a.ruta)
                        res = loader.cargar(a.ruta)
                        labels = res.metadatos.get("etiquetas_valores", {}) or {}
                        st.markdown(
                            f"- **{a.nombre}** ({a.formato.upper()}) · {c.miles(len(res.datos))} filas · "
                            f"{len(res.datos.columns)} columnas · "
                            f"{len(labels)} variables con etiquetas",
                        )
                        columnas = ", ".join(str(x) for x in res.datos.columns)
                        st.caption(f"Columnas: `{columnas}`")
                        col_pre, col_meta = st.columns([2, 1], vertical_alignment="center")
                        with col_pre:
                            st.dataframe(res.datos.head(3), width="stretch")
                        with col_meta:
                            if labels:
                                filas_label = []
                                for var, mapa in labels.items():
                                    m = "; ".join(f"{k}={v}" for k, v in list(mapa.items())[:4])
                                    filas_label.append({"Variable": var, "Etiquetas": m})
                                st.dataframe(pd.DataFrame(filas_label), width="stretch", height=120)
                    except Exception as e:  # noqa: BLE001
                        st.warning(f"- **{a.nombre}**: error al leer ({e})")
            else:
                c.vacio(
                    "No hay archivos .sav, .zsav o .por en el directorio de datos.",
                    icono=":material/upload_file:",
                    detalle="Sube uno con el botón de arriba o usa los de ejemplo: "
                            "clientes.sav, facturas.sav.",
                )

    # ---------------------------------------------------------------
    #  PESTAÑA: CONECTORES ERP/SQL (Fase 2)
    # ---------------------------------------------------------------
    with _pestana(tab_conectores):
        if tab_conectores is not None and tab_conectores.open:
            from pathlib import Path as _Path

            from src.core.conector_sql import (conectores_desde_snapshot,
                                               crear_snapshot_erp,
                                               escribir_conectores,
                                               parsear_conectores,
                                               sincronizar_conectores)

            st.markdown("**Sincronizacion con origenes externos (ERP/SQL)**")
            st.caption("GIRO puede poblar sus datasets desde otros motores: "
                       "SQLite, DuckDB, CSV/Excel (archivo o URL). Los conectores "
                       "se ejecutan con el ETL y con 'Sincronizar ahora'.")

            configurados = parsear_conectores(cfg)
            if configurados:
                filas = []
                for x in configurados:
                    fuente = x.fuente
                    if fuente and "://" not in str(fuente):
                        existe = (_Path(cfg.directorio_datos) / str(fuente)).exists()
                    else:
                        existe = bool(fuente)
                    filas.append({
                        "Nombre": x.nombre, "Motor": x.motor, "Dataset": x.dataset,
                        "Fuente": str(fuente or "(consulta)"), "Forzar": x.forzar,
                        "Fuente presente": "OK" if existe else "NO",
                    })
                st.dataframe(pd.DataFrame(filas), width="stretch")

                if st.button("Sincronizar conectores ahora", type="primary",
                             icon=":material/sync:"):
                    with st.status("Sincronizando conectores...", expanded=False) as estado:
                        resumen = sincronizar_conectores(cfg)
                        st.cache_data.clear()
                        st.cache_resource.clear()
                    ok = [r for r in resumen if r["ok"]]
                    fallas = [r for r in resumen if not r["ok"]]
                    estado.update(label=f"Sincronizados {len(ok)}/{len(resumen)}",
                                  state="complete" if not fallas else "error",
                                  expanded=False)
                    for r in ok:
                        st.write(f"- :material/check: **{r['nombre']}** -> {r['dataset']}: "
                                 f"{c.miles(r['filas'])} filas")
                    for r in fallas:
                        st.warning(f":material/error: **{r['nombre']}**: {r['error']}")
            else:
                c.vacio(
                    "Aún no hay conectores configurados.",
                    icono=":material/cable:",
                    detalle="Crea un snapshot de prueba o registra uno a mano más abajo.",
                )

            st.divider()
            st.markdown("**Prueba rapida: snapshot SQLite (simula exportacion del ERP)**")
            st.caption("Exporta tus datasets a un archivo SQLite (datos + metadatos "
                       "de la exportacion) y luego conecta los datasets a el.")
            col_ver, col_con = st.columns(2, vertical_alignment="bottom")
            snapshot_ruta = _Path(cfg.directorio_datos) / "erp.sqlite"
            with col_ver:
                if st.button("1. Crear snapshot ERP (erp.sqlite)",
                             icon=":material/database_upload:"):
                    with st.status("Creando snapshot SQLite...", expanded=False) as estado:
                        ruta, conteos = crear_snapshot_erp(cfg, snapshot_ruta)
                    estado.update(label="Snapshot listo", state="complete", expanded=False)
                    st.success(f"Snapshot creado: `{ruta}` "
                               f"({len(conteos)} datasets, "
                               f"{c.miles(sum(conteos.values()))} filas)")
                    if conteos:
                        st.dataframe(
                            pd.DataFrame({"Dataset": list(conteos),
                                          "Filas": list(conteos.values())}),
                            width="stretch")
            with col_con:
                if st.button("2. Conectar datasets del snapshot", type="secondary",
                             icon=":material/link:",
                             disabled=not snapshot_ruta.exists()):
                    con = conectores_desde_snapshot(cfg, snapshot_ruta)
                    ruta, nuevos = escribir_conectores(cfg, con)
                    st.success(
                        f"Registrados **{len(nuevos)}** conectores en `{ruta}`. "
                        "Usa 'Sincronizar ahora' o ejecuta el ETL para poblar DuckDB.")

            st.divider()
            st.markdown("**Agregar conector a mano**")
            with st.form("form_conector", border=True):
                fc1, fc2 = st.columns(2)
                with fc1:
                    nom_con = st.text_input("Nombre", placeholder="erp_facturas",
                                            key="con_nombre")
                    motor_con = st.selectbox(
                        "Motor",
                        ["sqlite", "duckdb", "csv", "excel", "url", "sql"],
                        key="con_motor",
                        help="'sql' conecta via SQLAlchemy (postgresql://, mysql:// "
                             "o sqlite:/// con credenciales/DSN).")
                with fc2:
                    dataset_con = st.selectbox(
                        "Dataset destino", list(cfg.datasets) + ["factura_detalle"],
                        key="con_dataset")
                    forzar_con = st.checkbox("Forzar (reemplaza la fuente local)",
                                             value=False, key="con_forzar")
                fuente_con = st.text_input(
                    "Fuente (archivo relativo a data/, URL o DSN)",
                    placeholder="erp.sqlite · postgresql://user:pass@host:5432/db",
                    key="con_fuente")
                consulta_con = st.text_area(
                    "Consulta SQL (para sqlite/duckdb/sql)", height=70,
                    placeholder="SELECT * FROM facturas", key="con_consulta")
                enviar_con = st.form_submit_button("Registrar conector",
                                                   type="primary", icon=":material/add:")
                if enviar_con:
                    if not nom_con.strip() or not dataset_con:
                        st.error("Escribe un nombre y elige el dataset destino.")
                    else:
                        nuevo = [{
                            "nombre": nom_con.strip(),
                            "motor": motor_con,
                            "fuente": fuente_con.strip() or None,
                            "consulta": consulta_con.strip() or None,
                            "dataset": dataset_con,
                            "forzar": forzar_con,
                        }]
                        ruta, nuevos = escribir_conectores(cfg, nuevo)
                        st.success(f"Conector **{nom_con.strip()}** registrado en "
                                   f"`{ruta.name}`. Sincroniza o ejecuta el ETL.")

            st.divider()
            st.markdown("**Warehouse central (multi-DB)**")
            st.caption("Publica el almacen (datasets + capa core + vistas "
                       "analiticas) hacia tu warehouse SQL: Postgres/Neon, "
                       "MySQL, SQLite. Ideal para gobernanza de datos: GIRO "
                       "calcula localmente y entrega tablas listas para BI.")
            from src.core.warehouse import sincronizar as _wh_sync
            from src.core.warehouse import ver as _wh_ver
            wh_dsn = st.text_input(
                "URL de conexión al warehouse",
                placeholder="postgresql://user:pass@host:5432/warehouse · "
                            "sqlite:///warehouse.sqlite",
                key="wh_dsn")
            wh_c1, wh_c2 = st.columns(2)
            with wh_c1:
                # Secundario: la primaria de esta pestaña es "Sincronizar
                # conectores ahora" y el formulario de arriba; dos botones
                # primarios seguidos compiten por el mismo viewport.
                if st.button("Publicar en el warehouse",
                             icon=":material/cloud_upload:", disabled=not wh_dsn.strip()):
                    # El permiso se comprueba en la accion, no solo con
                    # ocultar la pestana (PERMISO_PUBLICAR_WAREHOUSE existia
                    # y nadie lo comprobaba).
                    exigir(auth.PERMISO_PUBLICAR_WAREHOUSE,
                           "Solo un administrador puede publicar en el warehouse.")
                    with st.status("Publicando...", expanded=False) as wh_estado:
                        try:
                            publicados = _wh_sync(cfg, wh_dsn.strip())
                            wh_estado.update(label=f"{len(publicados)} objetos publicados",
                                             state="complete", expanded=False)
                            st.dataframe(pd.DataFrame(publicados), width="stretch")
                        except Exception as e:  # noqa: BLE001
                            wh_estado.update(label="Fallo la publicacion", state="error")
                            # mensaje_error enmascara el DSN: una excepcion de
                            # SQLAlchemy/psycopg2 puede traer user:pass.
                            st.error(f"No se pudo publicar: {mensaje_error(e)}")
            with wh_c2:
                if st.button("Ver tablas publicadas", icon=":material/database_search:",
                             disabled=not wh_dsn.strip()):
                    try:
                        with st.spinner("Consultando las tablas publicadas…"):
                            df_wh = _wh_ver(cfg, wh_dsn.strip())
                        if df_wh.empty:
                            st.info("No hay tablas GIRO en el warehouse destino.")
                        else:
                            st.dataframe(df_wh, width="stretch")
                    except Exception as e:  # noqa: BLE001
                        st.error(f"No se pudo ver las tablas: {mensaje_error(e)}")

    # ---------------------------------------------------------------
    #  PESTAÑA: CONSULTAS SQL
    # ---------------------------------------------------------------
    with _pestana(tab_sql):
        if tab_sql is not None and tab_sql.open:
            st.markdown("## Consultas SQL sobre tus datos (DuckDB)")
            st.caption("Consulta las tablas del almacén en lenguaje SQL. "
                       "Útil cuando necesitas un dato que los paneles no muestran.")
            st.info(
                "Modo **solo lectura**: ejecuta una sentencia `SELECT` por vez. "
                "Las escrituras y el acceso a archivos o a la red estan "
                "bloqueados para proteger el almacen.",
                icon=":material/read_only:",
            )
            st.selectbox(
                "Ejemplos de consultas", list(EJEMPLOS_SQL), key="sql_ejemplo_lbl",
                on_change=_aplicar_ejemplo_sql,
            )
            with st.form("form_sql", border=False):
                consulta = st.text_area(
                    "SQL", key="sql_consulta", height=90, label_visibility="collapsed",
                    value=EJEMPLOS_SQL[list(EJEMPLOS_SQL)[0]],
                )
                enviar = st.form_submit_button("Ejecutar consulta", type="primary",
                                               icon=":material/play_arrow:")
            if enviar:
                from ui.context import consulta_sql
                try:
                    with st.spinner("Ejecutando consulta…"):
                        df_res = consulta_sql(consulta)
                    st.dataframe(df_res, width="stretch", height=300)
                    st.caption(f"{c.miles(len(df_res))} filas · "
                               f"{c.miles(len(df_res.columns))} columnas")
                except Exception as e:  # noqa: BLE001
                    st.error(f"No se pudo ejecutar la consulta. Verifica la sintaxis SQL: {e}")


def _wizard_primer_uso():
    """Wizard de primer uso: guia al usuario para cargar datos por primera vez.

    Solo se muestra si no hay datos cargados y el usuario no lo ha completado.
    No pasa por ``obtener_estado``: ese camino entrena los modelos y puede
    detener la renderizacion con un error tecnico; aqui basta saber si hay
    datos.
    """
    cfg = obtener_config()
    data = cargar_datos(cfg)
    hay_datos = bool(data) and any(
        isinstance(df, pd.DataFrame) and not df.empty for df in data.values()
    )

    if hay_datos or st.session_state.get("_onboarding_completado"):
        return

    with st.container(border=True):
        st.markdown("## :material/rocket_launch: Comenzando con GIRO")
        st.markdown(
            "Bienvenido. Para ver analisis y predicciones, primero cargamos "
            "los datos de tu negocio."
        )

        # Apilado y no columns: en el sidebar (donde se renderiza) tres
        # columnas quedan a ~90px y el texto se parte palabra por palabra.
        for titulo, detalle in [
            ("1. Sube tus archivos",
             "CSV, Excel o PSPP con tus facturas, clientes y servicios."),
            ("2. Procesa el ETL",
             "GIRO normaliza los datos y crea las vistas analíticas."),
            ("3. Explora el dashboard",
             "KPIs, predicciones y recomendaciones listos para usar."),
        ]:
            st.markdown(f"**{titulo}**")
            st.caption(detalle)

        st.markdown("---")
        st.markdown(
            "Ve a la pagina **Mis datos** para comenzar, o "
            "genera datos de ejemplo para probar."
        )

        # Apilados igual que los pasos: en el sidebar tres botones a ~90px
        # no permiten leer la etiqueta.
        if st.button("Ir a Mis datos", type="primary",
                     icon=":material/arrow_forward:", width="stretch",
                     key="wizard_ir_datos"):
            # No se marca completado aqui: si el usuario se pierde sin
            # importar nada, el wizard debe volver a aparecer.
            st.switch_page("ui/pages/datos.py")
        if st.button("Generar datos de ejemplo",
                     icon=":material/auto_awesome:", width="stretch",
                     key="wizard_generar_ejemplo"):
            from generate_data import main as generar_ejemplos

            # Escribe ficheros en el workspace: mismo criterio que el resto
            # de acciones que persisten.
            exigir_escritura()

            # Los archivos van al directorio de datos del workspace
            # activo, no al data/ de la raiz (regla 1: aislamiento).
            try:
                with st.spinner("Generando datos de ejemplo…"):
                    destino = generar_ejemplos(cfg.clave)
                st.success(f"Datos de ejemplo generados en `{destino}`. Recarga la pagina.")
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"No se pudo generar datos de ejemplo: {e}")
        if st.button("Lo haré después",
                     icon=":material/later:", width="stretch",
                     key="wizard_despues"):
            st.session_state["_onboarding_completado"] = True
            st.rerun()


if __name__ == "__main__":
    principal()