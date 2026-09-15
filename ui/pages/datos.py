"""Pagina: Datos y Configuracion (asistente de importacion + integracion PSPP)."""

from pathlib import Path

import pandas as pd
import streamlit as st

from src.core.catalog import escanear_directorio, clasificar_archivo, vincular_archivos_a_datasets
from src.loaders import get_loader
from src.loaders.pspp_loader import exportar_sav

from ui import components as c
from ui.context import obtener_config, obtener_estado

EJEMPLOS_SQL = {
    "Facturas recientes": "SELECT * FROM facturas LIMIT 10",
    "Top clientes por gasto": "SELECT nombre, SUM(total) AS gasto FROM facturas GROUP BY nombre ORDER BY gasto DESC LIMIT 10",
    "Vehiculos por marca": "SELECT marca, COUNT(*) AS vehiculos FROM vehiculos GROUP BY marca ORDER BY vehiculos DESC",
    "Facturas por estado": "SELECT estado, SUM(total) AS monto, COUNT(*) AS facturas FROM facturas GROUP BY estado",
}


def _aplicar_ejemplo_sql():
    etiqueta = st.session_state.get("sql_ejemplo_lbl")
    st.session_state["sql_consulta"] = EJEMPLOS_SQL.get(etiqueta, "")


def principal():
    cfg, data, analyzer, predictor = obtener_estado()
    c.cabecera(
        "Datos y configuracion",
        "Importa tus datos (CSV, Excel o PSPP), verifica calidad y procesa el ETL",
        icono=":material/database:",
    )

    tab_importar, tab_etl, tab_esquema, tab_calidad, tab_pspp, tab_sql = st.tabs(
        ["Importar / detectar", "Procesar (ETL)", "Esquema de datos",
         "Calidad de datos", "Integracion PSPP/SPSS", "Consultas SQL"],
        key="tabs_datos", on_change="rerun",
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

            with st.container(border=True):
                st.markdown("**Subir archivos**")
                subidos = st.file_uploader(
                    "Arrastra o selecciona archivos",
                    type=["csv", "tsv", "xlsx", "xls", "sav", "zsav", "por", "parquet"],
                    accept_multiple_files=True,
                    help="Puedes cargar los archivos que exporta PSPP (.sav, .por) o hojas de calculo.",
                )
                if subidos:
                    destino_dir = cfg.directorio_datos if directorio == Path(cfg.directorio_datos) else directorio
                    destino_dir.mkdir(parents=True, exist_ok=True)
                    guardados = 0
                    for up in subidos:
                        (destino_dir / up.name).write_bytes(up.getbuffer())
                        guardados += 1
                    st.success(f"{guardados} archivo(s) guardados en {destino_dir}")

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
                st.info("No se encontraron archivos de datos en el directorio.")

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
                            ("Tablas core", f"{len(resultado.estructura)}", None, None,
                             "Tablas normalizadas con claves primarias/foraneas"),
                            ("Vistas analitica", f"{resultado.n_vistas}", None, None,
                             "Modelos dimensionales listos para los paneles"),
                        ])
                        if resultado.estructura:
                            st.caption(":material/hub: Esquema `core` normalizado con claves · "
                                       f"ha creado **{len(resultado.estructura)}** tablas y "
                                       f"**{resultado.n_vistas}** vistas en `analitica`.")
                    else:
                        estado.update(label="ETL termino con errores", state="error", expanded=True)
                        st.error("El ETL termino con errores:")
                        for nombre, err in resultado.errores.items():
                            st.write(f"- **{nombre}**: {err}")

            st.markdown("**Descargar datos procesados**")
            datasets = list(data.keys())
            sel = st.pills(
                "Dataset", datasets, key="dl_dataset",
                default=datasets[0] if datasets else None, selection_mode="single",
                label_visibility="collapsed",
            )
            if sel and not data.get(sel, pd.DataFrame()).empty:
                c.descargar(data[sel], sel)

            st.markdown("**Exportar a PSPP desde la interfaz**")
            if st.button("Exportar todos los datasets a .sav",
                         icon=":material/ios_share:",
                         help="Genera archivos .sav en data/export/"):
                out = Path(cfg.directorio_datos) / "export"
                out.mkdir(parents=True, exist_ok=True)
                for nombre, df in data.items():
                    if df.empty:
                        continue
                    try:
                        exportar_sav(df, out / f"{nombre}.sav", label_archivo=f"{nombre} exportado")
                    except Exception as e:  # noqa: BLE001
                        st.warning(f"{nombre}: {e}")
                st.success(f"Exportados a {out}")

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
                            st.caption("Sin objetos registrados. Procesa el ETL primero.")
                with col2:
                    with c.panel("Objetos por esquema", "Estructura detallada",
                                 icono=":material/schema:"):
                        st.dataframe(catalogo, width="stretch", height=260)

                vistas = catalogo[catalogo["tipo"] == "VIEW"]["objeto"].tolist() if not catalogo.empty else []
                if vistas:
                    st.markdown("**Explorar vistas analiticas**")
                    vista = st.selectbox("Vista analitica", ["-- selecciona --"] + vistas,
                                         key="vista_analitica")
                    if vista != "-- selecciona --":
                        with c.panel(f"Vista: {vista}", "Resultado del modelo dimensional",
                                     icono=":material/table_view:"):
                            st.dataframe(consultar_vista(vista), width="stretch", height=320)
            except Exception as e:  # noqa: BLE001
                st.info(f"No hay almacen disponible todavia: {e}")

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
                st.info("Procesa los datos primero para ver su calidad.")

    # ---------------------------------------------------------------
    #  PESTAÑA: INTEGRACION PSPP
    # ---------------------------------------------------------------
    with tab_pspp:
        if tab_pspp.open:
            st.markdown("### Integracion con PSPP / SPSS")
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

            st.markdown("#### Variables disponibles en la analitica")
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
                st.info("No hay archivos .sav/.zsav/.por en el directorio de datos. "
                        "Sube uno o usa los de ejemplo (clientes.sav, facturas.sav).")

    # ---------------------------------------------------------------
    #  PESTAÑA: CONSULTAS SQL
    # ---------------------------------------------------------------
    with tab_sql:
        if tab_sql.open:
            st.markdown("### Consultas SQL sobre tus datos (DuckDB)")
            st.caption("Consulta todas las tablas en lenguaje SQL. "
                       "Util para informacion avanzada y portatil.")
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
                    df_res = consulta_sql(consulta)
                    st.dataframe(df_res, width="stretch", height=300)
                except Exception as e:  # noqa: BLE001
                    st.error(f"No se pudo ejecutar: {e}")


if __name__ == "__main__":
    principal()