"""CLI de GIRO, inteligencia de negocio.

Uso:
    python main.py resumen [--data DIR]
    python main.py etl [--data DIR]
    python main.py report [--output NOMBRE] [--abrir]
    python main.py predict [--tipo ingresos|demanda|churn|inventario|todos] [--meses N]
    python main.py importar <archivo> [--formato auto] [--dataset CLIENTES]
    python main.py exportar [--dataset TODOS] [--formato sav|csv]
    python main.py alertas [--reporte] [--enviar-email]
    python main.py workspace crear <clave> [--nombre ...] [--moneda ...] [--muestra]
    python main.py workspace listar
    python main.py workspace config <clave>
    python main.py workspace init-db
    python main.py conector listar|sincronizar|seed-erp [--data DIR] [--usar]
    python main.py warehouse sync|ver --dsn DSN [--esquemas ...] [--prefijo giro_]
    python main.py reporte listar
    python main.py reporte generar [--tipo resumen|ventas|clientes|inventario|predicciones|todos]
                                   [--periodo ...] [--pdf] [--enviar-email] [--abrir]
    python main.py dashboard
    python main.py landing [--port 8501]
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from src import aplicacion
from src.core.pipeline import load_all
from src.core.calidad import resumen as _resumen_calidad
from src.core.catalog import escanear_directorio, clasificar_archivo
from src.storage.schema import VISTAS_ANALITICA
from src.analyzer import Analyzer
from src.predictions import Predictor
from src.reports import ReportGenerator

BASE_DIR = Path(__file__).parent


def _config(args):
    from src import workspaces as ws
    cfg = ws.config_actual()
    if getattr(args, "data", None):
        cfg.directorio_datos = Path(args.data)
    return cfg


def _formato(valor, dec=0):
    """Formatea con punto como separador de miles (es-CL).

    Delegado en ``src.formatos``: la CLI no debe importar la UI para
    pintar un numero.
    """
    from src.formatos import miles
    return miles(valor, dec)


def _moneda(valor, cfg):
    from src.formatos import moneda
    return moneda(valor, cfg.moneda)


def cmd_resumen(args):
    cfg = _config(args)
    print("=" * 70)
    print("RESUMEN DE NEGOCIO")
    print("=" * 70)
    data = load_all(cfg)
    for nombre, info in aplicacion.resumen_calidad(data).items():
        print(f"\n[{nombre}]  {_formato(info['registros'])} registros · {len(info['columnas'])} columnas")
        nulos = [f"{k}={v}" for k, v in info["nulos"].items() if v > 0]
        if nulos:
            print("  Nulos:", ", ".join(nulos))

    analyzer = Analyzer(data)
    kpis = analyzer.kpis_globales()
    print("\n" + "=" * 70)
    print("KPIs")
    print("=" * 70)
    for k, v in kpis.items():
        if isinstance(v, (int, float)):
            print(f"  {k.replace('_', ' ').title():32s}: {_formato(v, 2)}")
        else:
            print(f"  {k.replace('_', ' ').title():32s}: {v}")
    return data, cfg


def cmd_etl(args):
    cfg = _config(args)
    print("Ejecutando pipeline ETL...")
    resultado = aplicacion.ejecutar_etl(cfg)
    print(f"\nTablas registradas en DuckDB ({resultado.tiempo_carga}s):")
    for tabla, filas in resultado.tablas_registradas.items():
        print(f"  - {tabla}: {_formato(filas)} filas")
    if resultado.estructura:
        print("\nEsquema core materializado con claves:")
        for tabla, filas in resultado.estructura.items():
            print(f"  - core.{tabla}: {_formato(filas)} filas")
        print(f"  - vistas analiticas creadas: {resultado.n_vistas}")
    # Las advertencias (totales no parseables, vistas no creadas, conectores
    # caidos) antes solo se veian en la UI: por CLI el ETL imprimia "OK".
    if resultado.advertencias:
        print("\nAdvertencias:")
        for n, aviso in resultado.advertencias.items():
            print(f"  - {n}: {aviso}")
    if not resultado.calidad.empty:
        res = _resumen_calidad(resultado.calidad)
        print(f"\nCalidad de datos: {res['ok']}/{res['total']} reglas cumplen")
        fallas = resultado.calidad[resultado.calidad["estado"] != "OK"]
        for _, f in fallas.iterrows():
            print(f"  - [{f['estado']}] {f['dataset']}.{f['campo']} "
                  f"({f['dimension']}): {f['regla']} -> "
                  f"{f['cumplen']}/{f['evaluadas']} ({f['tasa']*100:.0f}%)")
    if resultado.errores:
        print("\nErrores:")
        for n, e in resultado.errores.items():
            print(f"  - {n}: {e}")
    print("\nOK" if resultado.ok else "\nCOMPLETADO CON ERRORES")


def _abrir_en_navegador(ruta) -> None:
    """Abre un HTML en el navegador local (solo macOS) sin shell.

    Lista de argumentos: una ruta con comillas no puede convertirse en
    comando. En otros SO se indica que el archivo se abra a mano.
    """
    if sys.platform != "darwin":
        print(f"Abre el archivo en tu navegador: {ruta}")
        return
    try:
        subprocess.run(["open", str(ruta)], check=False, timeout=15)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"No se pudo abrir el navegador: {type(e).__name__}: {e}")


def cmd_report(args):
    data, cfg = cmd_resumen(args)
    print("\n\nGenerando reporte HTML...")
    ruta, contenido = ReportGenerator(data, cfg=cfg).generar(args.output)
    print(f"Reporte generado en: {ruta}")
    if args.abrir:
        _abrir_en_navegador(ruta)


def cmd_predict(args):
    cfg = _config(args)
    data = load_all(cfg)
    predictor = Predictor(data, cfg=cfg)
    tipos = args.tipo.split(",") if "," in args.tipo else [args.tipo]
    if "todos" in tipos:
        tipos = ["ingresos", "demanda", "churn", "inventario"]

    for t in tipos:
        print(f"\n{'=' * 70}")
        print(f"PREDICCION: {t.upper()}")
        print("=" * 70)
        if t == "ingresos":
            res = predictor.predecir_ingresos(args.meses)
            print(f"Modelo: {res['modelo']}")
            if res.get("evaluacion"):
                for k, v in res["evaluacion"].items():
                    print(f"  {k}: {_formato(v, 2)}" if isinstance(v, (int, float)) else f"  {k}: {v}")
            print(res["predicciones"].to_string(index=False))
        elif t == "demanda":
            res = predictor.predecir_demanda(args.meses)
            print(f"Modelo: {res['modelo']}")
            if not res["predicciones"].empty:
                print(res["predicciones"].to_string(index=False))
            else:
                print("Datos insuficientes.")
        elif t == "churn":
            res = predictor.predecir_churn()
            print(f"Modelo: {res['modelo']}")
            if res.get("evaluacion"):
                for k, v in res["evaluacion"].items():
                    if not isinstance(v, dict):
                        print(f"  {k}: {v}")
            cols = [c for c in ["nombre", "recencia", "frecuencia", "monto", "churn", "prob_churn"] if c in res["resultados"]]
            print("\nTop 15 clientes en riesgo:")
            print(res["resultados"][cols].head(15).to_string(index=False))
        elif t == "inventario":
            res = predictor.predecir_inventario()
            criticos = res[res["recomendacion"] == "Reabastecer"]
            print(f"{len(criticos)} productos requieren reabastecimiento:")
            cols = [c for c in ["producto", "stock_actual", "stock_minimo", "meses_cobertura", "recomendacion"] if c in res.columns]
            print(res[cols].to_string(index=False))


def cmd_importar(args):
    cfg = _config(args)
    ruta = Path(args.archivo)
    if not ruta.exists():
        print(f"Archivo no encontrado: {ruta}")
        sys.exit(1)
    import shutil
    destino = cfg.directorio_datos / ruta.name
    if ruta.resolve() == destino.resolve():
        print(f"El archivo ya esta en el directorio de datos: {destino}")
    else:
        shutil.copy2(ruta, destino)
        print(f"Copiado a: {destino}")

    archivo = [a for a in escanear_directorio(cfg.directorio_datos) if a.ruta == destino][0]
    dataset, score = clasificar_archivo(archivo.ruta, archivo.formato)
    print(f"Formato detectado: {archivo.formato}")

    if args.dataset and args.dataset.lower() != "auto":
        print(f"Asociado al dataset: {args.dataset}")
        cfg.datasets[args.dataset.lower()].fuentes_alternativas.append(destino.name)
    elif dataset:
        print(f"Dataset detectado automaticamente: {dataset} ({score:.0%})")
    else:
        print("Dataset no reconocido automaticamente. Usa --dataset para forzarlo.")


def cmd_exportar(args):
    cfg = _config(args)
    data = load_all(cfg)
    todos = args.dataset and args.dataset.lower() in ("todos", "all")
    if not todos:
        datasets_sel = {args.dataset.lower(): data.get(args.dataset.lower(), None)}
    else:
        datasets_sel = data

    out = Path(cfg.directorio_datos) / "export"
    out.mkdir(parents=True, exist_ok=True)
    for nombre, df in datasets_sel.items():
        if df is None or (hasattr(df, "empty") and df.empty):
            continue
        _exportar_archivo(df, out / nombre, args.formato)

    # Vistas analiticas del almacen (Idea 1): ademas de los datasets,
    # se exportan las agregaciones consumidas por los paneles.
    if todos:
        try:
            from src.data_loader import get_store
            store = get_store(cfg, usar_cache=False)
            try:
                for vista in VISTAS_ANALITICA:
                    try:
                        df = store.consultar_vista(vista)
                    except Exception:  # noqa: BLE001
                        continue
                    if df is None or df.empty:
                        continue
                    _exportar_archivo(df, out / f"analitica_{vista}", args.formato)
            finally:
                store.cerrar()
        except Exception as e:  # noqa: BLE001
            print(f"  (vistas analiticas no exportadas: {e})")


def _exportar_archivo(df, ruta_base: Path, formato: str):
    out = ruta_base
    if formato == "sav":
        from src.loaders.pspp_loader import exportar_sav
        destino = Path(str(out) + ".sav")
        exportar_sav(df, destino, label_archivo=f"{out.name} exportado")
        print(f"  {out.name}.sav")
    elif formato == "por":
        from src.loaders.pspp_loader import exportar_por
        destino = Path(str(out) + ".por")
        exportar_por(df, destino)
        print(f"  {out.name}.por")
    else:
        destino = Path(str(out) + ".csv")
        df.to_csv(destino, index=False, encoding="utf-8-sig")
        print(f"  {out.name}.csv")


def cmd_conector(args):
    from src.aplicacion import (conectores_desde_snapshot, crear_snapshot_erp,
                                escribir_conectores, parsear_conectores,
                                sincronizar_conectores)
    cfg = _config(args)

    if args.accion == "listar":
        conectores = parsear_conectores(cfg)
        if not conectores:
            print("Sin conectores configurados en este workspace.")
            print("Prueba: python main.py conector seed-erp --usar")
            return 0
        print(f"Conectores de [{cfg.clave}] ({len(conectores)}):")
        for c in conectores:
            fuente = c.fuente
            existe = False
            if fuente and "://" in str(fuente):
                existe = True
            elif fuente:
                existe = (cfg.directorio_datos / str(fuente)).exists()
            estado = "OK" if existe else "fuente no encontrada"
            forzar = "  [forzar]" if c.forzar else ""
            print(f"  - {c.nombre}: {c.motor} -> {c.dataset} ({estado}){forzar}")
        return 0

    if args.accion == "sincronizar":
        print(f"Sincronizando conectores de [{cfg.clave}]...")
        resumen = sincronizar_conectores(cfg)
        ok = [r for r in resumen if r["ok"]]
        fallas = [r for r in resumen if not r["ok"]]
        for r in ok:
            print(f"  - {r['nombre']}: {_formato(r['filas'])} filas -> {r['dataset']}")
        for r in fallas:
            print(f"  - {r['nombre']}: FALLO ({r['error']})")
        print(f"\nOK ({len(ok)}/{len(resumen)})" if not fallas
              else f"\nCOMPLETADO CON ERRORES ({len(fallas)}/{len(resumen)})")
        return 0 if not fallas else 1

    if args.accion == "seed-erp":
        destino = Path(args.destino) if args.destino else cfg.directorio_datos / "erp.sqlite"
        print(f"Creando snapshot SQLite (simula exportacion del ERP)...")
        ruta, conteos = crear_snapshot_erp(cfg, destino)
        print(f"Snapshot creado: {ruta}")
        for nombre, n in conteos.items():
            print(f"  - {nombre}: {_formato(n)} filas")
        if args.usar:
            conectores = conectores_desde_snapshot(cfg, ruta)
            ruta_cfg, nuevos = escribir_conectores(cfg, conectores)
            print(f"\nRegistrados {len(nuevos)} conectores (forzar=true) en {ruta_cfg}")
            print("Ejecuta 'python main.py conector sincronizar' o 'python main.py etl' "
                  "para poblar DuckDB desde la BD del ERP.")
        else:
            print("\nUsa '--usar' para registrar los conectores en el config "
                  "(forzar=true) y sincronizar.")
        return 0


def cmd_dashboard(args):
    print("Iniciando dashboard web (Streamlit)...")
    cmd = [sys.executable, "-m", "streamlit", "run", str(BASE_DIR / "dashboard.py")]
    subprocess.run(cmd)


def cmd_landing(args):
    print("Iniciando landing publica (Streamlit)...")
    cmd = [sys.executable, "-m", "streamlit", "run", str(BASE_DIR / "landing.py"),
           "--server.port", str(args.port)]
    subprocess.run(cmd)


def cmd_alertas(args):
    from src.alerts import evaluar_alertas, resumen_alertas, generar_reporte_alertas, enviar_email

    cfg = _config(args)
    data = load_all(cfg)
    alertas = evaluar_alertas(cfg, data)
    res = resumen_alertas(alertas)

    print("=" * 70)
    print("ALERTAS DE NEGOCIO")
    print("=" * 70)
    print(f"Total: {res['total']} · Criticas: {res['critica']} · Medias: {res['media']} · Bajas: {res['baja']}")
    print(f"Por tipo: {', '.join(f'{k}={v}' for k, v in res['por_tipo'].items()) or 'sin reglas disparadas'}")
    if not alertas:
        print("\nSin alertas activas.")
    for a in alertas:
        print(f"\n[{a['severidad'].upper()}] {a['titulo']}")
        print(f"    {a['detalle']}")

    if args.reporte:
        ruta = generar_reporte_alertas(cfg, data, alertas)
        print(f"\nReporte generado en: {ruta}")
    if args.enviar_email:
        cuerpo = "<ul>" + "".join(
            f"<li><b>{a['titulo']}</b><br>{a['detalle']}</li>" for a in alertas) + "</ul>"
        if enviar_email(cfg, f"[GIRO] Alertas de {cfg.negocio_nombre}", cuerpo):
            print("Alertas enviadas por email.")
        else:
            print("SMTP no configurado; alertas no enviadas.")


def cmd_reporte(args):
    """Genera reportes ejecutivos white-label (automatizables via cron)."""
    from src.reporting import catalogo, por_clave
    from src.reporting.engine import GeneradorReportes, listar_generados

    cfg = _config(args)
    data = load_all(cfg)
    gen = GeneradorReportes(cfg, data)

    if args.accion == "listar":
        print(f"Reportes disponibles para [{cfg.negocio_nombre}] "
              f"({cfg.clave}):")
        for r in catalogo.REPORTES:
            print(f"  - {r['clave']:<12} {r['titulo']}")
            print(f"      {r['descripcion']}")
        generados = listar_generados(cfg)
        print(f"\nGenerados en reports/ ({len(generados)}):")
        for g in generados:
            print(f"  - [{g['tipo']}] {g['nombre']}")
        if not generados:
            print("  (aun no hay reportes; usa 'python main.py reporte generar')")
        return 0

    ocasion = args.periodo or ""
    if args.tipo == catalogo.TODOS:
        resultados = gen.generar_todos(ocasion_label=ocasion)
        total = len(resultados)
        print(f"Reportes generados para [{cfg.negocio_nombre}] "
              f"({cfg.clave}):")
        for meta in resultados:
            print(f"  - {meta['tipo']:<12} {meta['archivo']}")
        return 0 if total else 1

    if por_clave(args.tipo) is None:
        print(f"Tipo desconocido: {args.tipo}. Usa {catalogo.tipos_hint()}.")
        return 1

    ruta, meta = gen.generar(args.tipo, ocasion_label=ocasion,
                             base_filename=args.output)
    print(f"Reporte generado: {ruta}")
    print(f"  tipo: {meta['tipo']} · insights: {meta['num_insights']}")
    if args.pdf:
        ruta_pdf = gen.a_pdf(ruta)
        if ruta_pdf:
            print(f"  PDF : {ruta_pdf}")
        else:
            print("  (PDF omitido: instala weasyprint para generarlo)")
    if args.enviar_email:
        asunto = f"[GIRO] {meta['titulo']} · {cfg.negocio_nombre}"
        cuerpo = open(ruta, encoding="utf-8").read()
        if gen.enviar_email(asunto, cuerpo):
            print("  Enviado por email (SMTP).")
        else:
            print("  Email no enviado (SMTP no configurado).")
    if args.abrir:
        _abrir_en_navegador(ruta)


def _asegurar_base_postgres(cfg) -> int:
    """Crea la base de Postgres del workspace recien creado (solo si el
    motor es postgres). Devuelve 0 si la base esta lista (creada o ya
    existente) y 1 si fallo.

    Ante un fallo NO se borra el workspace: un rollback del directorio
    podria borrar uno preexistente (``crear_workspace`` es idempotente) y
    el desfase es reparable. Lo que si pasa es el aviso —con el nombre
    exacto de la base que falta— y el codigo de salida distinto de cero,
    para que ningun script de despliegue lo ignore.
    """
    from src.data_loader import dbname_postgres
    from src.storage.postgres import asegurar_base_workspace

    nombre = dbname_postgres(cfg)
    try:
        creada = asegurar_base_workspace(cfg)
    except Exception as e:  # noqa: BLE001 — se informa al operador, no se traga
        # El motivo puede ser multilinea (la accion del operador viene
        # dentro): se indenta para que no se pierda entre los avisos.
        print()
        print("AVISO: el workspace se creo en disco, pero su base de "
              "Postgres NO existe:")
        print(f"  base requerida: {nombre}")
        print("  motivo: " + str(e).replace("\n", "\n    "))
        print("  Reparacion:  python main.py workspace init-db")
        return 1
    print(f"  base postgres: {nombre} "
          f"({'creada' if creada else 'ya existia'})")
    return 0


def cmd_workspace(args):
    from src import workspaces as ws
    from src.core.config_manager import cargar_config
    from src.data_loader import MOTOR_POSTGRES, dbname_postgres, motor_almacen
    from src.storage.postgres import asegurar_base_workspace

    if args.accion == "crear":
        cfg = ws.crear_workspace(
            args.clave, nombre=args.nombre, moneda=args.moneda,
            slogan=args.slogan, sector=args.sector, con_datos_muestra=args.muestra)
        print(f"Workspace '{cfg.clave}' creado:")
        print(f"  nombre: {cfg.negocio_nombre} · sector: {cfg.sector} · moneda: {cfg.moneda}")
        print(f"  datos: {cfg.directorio_datos}")
        print(f"  almacen: {cfg.db_path}")
        if motor_almacen(cfg) == MOTOR_POSTGRES and _asegurar_base_postgres(cfg):
            raise SystemExit(1)
    elif args.accion == "init-db":
        # Repara el desfase entre workspaces/ y las bases de Postgres:
        # recorre todos (el workspace raiz 'principal' incluido) y crea
        # las bases que falten, informando por workspace. Sale con codigo
        # distinto de cero si alguna fallo, para automatizar el despliegue.
        if motor_almacen() != MOTOR_POSTGRES:
            print("Motor de almacen: duckdb — no hay bases de Postgres "
                  "que crear.")
            print("Si este servidor usa PostgreSQL, vuelve a ejecutar con "
                  "GIRO_ALMACEN_MOTOR=postgres.")
            return
        claves = [ws.CLAVE_PRINCIPAL] + [
            c for c in ws.listar_workspaces() if c != ws.CLAVE_PRINCIPAL]
        print(f"Bases de Postgres por workspace ({len(claves)}):")
        creadas = existias = 0
        fallos = []
        for clave in claves:
            try:
                # 'principal' no vive en workspaces/: es la config raiz.
                cfg = (cargar_config() if clave == ws.CLAVE_PRINCIPAL
                       else ws.config_workspace(clave))
                nombre = dbname_postgres(cfg)
                creada = asegurar_base_workspace(cfg)
            except Exception as e:  # noqa: BLE001 — se informa por workspace, no se traga
                # El motivo puede traer la accion del operador en varias
                # lineas: se indenta para que no se pierda el detalle.
                print(f"  - {clave}: ERROR: "
                      + str(e).replace("\n", "\n      "))
                fallos.append(clave)
                continue
            if creada:
                print(f"  - {clave}: creada ({nombre})")
                creadas += 1
            else:
                print(f"  - {clave}: ya existia ({nombre})")
                existias += 1
        print(f"\n{creadas} creadas · {existias} ya existian · "
              f"{len(fallos)} con error")
        if fallos:
            print("Revisa GIRO_PG_HOST/PORT/USER/PASSWORD/DBNAME (y que el "
                  "usuario tenga CREATEDB) y vuelve a ejecutar.")
            raise SystemExit(1)
    elif args.accion == "listar":
        lista = ws.listar_workspaces()
        print(f"Workspaces ({len(lista)}):")
        for clave in lista or ["(sin workspaces creados)"]:
            print(f"  - {clave}")
    elif args.accion == "config":
        try:
            cfg = ws.config_workspace(args.clave)
            print(f"[{cfg.clave}] {cfg.negocio_nombre} · {cfg.sector} · {cfg.moneda}")
            print(f"  datos: {cfg.directorio_datos} · almacen: {cfg.db_path}")
            print(f"  inventario: horizonte={cfg.inventario.get('horizonte_meses')}m, "
                  f"lead={cfg.inventario.get('lead_time_meses')}m, "
                  f"{len(cfg.inventario.get('mapeo_servicio_categoria') or {})} mapeos")
            print(f"  mantenimiento: {len(cfg.mantenimiento.get('intervalos_meses') or {})} intervalos")
            print(f"  alertas: {len([k for k, v in cfg.alertas.items() if k != 'smtp' and v])} reglas activas")
        except FileNotFoundError as e:
            print(f"Error: {e}")
            raise SystemExit(1)


def _dsn_seguro(dsn: str) -> str:
    """DSN apto para logs/consola: nunca muestra usuario ni password."""
    import re as _re
    return _re.sub(r"(\w+://)[^@/\s]+@", r"\1***@", str(dsn))


def cmd_warehouse(args):
    """Publica el almacen DuckDB hacia un warehouse SQL externo (multi-DB)."""
    cfg = _config(args)

    if args.accion == "sync":
        esquemas = tuple(e.strip() for e in (args.esquemas or "datasets,core,analitica").split(","))
        publicados = aplicacion.publicar_warehouse(cfg, args.dsn, esquemas=esquemas,
                                                   prefijo=args.prefijo)
        print(f"Publicados {len(publicados)} objetos al warehouse ({_dsn_seguro(args.dsn)}):")
        print(f"  {'esquema':<10} {'origen':<24} {'tabla':<30} {'filas':>8}")
        for p in publicados:
            print(f"  {p['esquema']:<10} {p['origen']:<24} {p['tabla']:<30} {p['filas']:>8}")
        if not publicados:
            print("  (nada que publicar)")
    elif args.accion == "ver":
        df = aplicacion.ver_warehouse(cfg, args.dsn, prefijo=args.prefijo)
        if df.empty:
            print("No hay objetos GIRO en el warehouse.")
        else:
            print(df.to_string(index=False))


def cmd_eval(args):
    """Ejecuta la suite de evaluación determinística (recomendaciones y alertas)."""
    from src.evaluacion import ejecutar_todos

    resultados = ejecutar_todos()
    print("=" * 70)
    print("EVALUACION DETERMINISTICA DE GIRO")
    print("=" * 70)
    todos_pasan = True
    for nombre, ok, mensaje in resultados:
        estado = "PASS" if ok else "FAIL"
        detalle = mensaje if mensaje else "OK"
        print(f"[{estado}] {nombre}: {detalle}")
        if not ok:
            todos_pasan = False
    print()
    if todos_pasan:
        print(f"Todos los escenarios ({len(resultados)}) pasaron.")
        return 0
    else:
        print(f"Algunos escenarios fallaron ({len(resultados)} ejecutados).")
        return 1


def cmd_onboarding(args):
    """Genera la configuracion inicial de un workspace por sector vertical."""
    from src.onboarding import configuracion_por_sector, SECTORES, validar_sector

    try:
        cfg = configuracion_por_sector(
            args.sector, args.clave, nombre=args.nombre, moneda=args.moneda)
    except ValueError as e:
        print(f"Error: {e}")
        print(f"Sectores disponibles: {', '.join(SECTORES)}")
        return 1

    print("=" * 70)
    print(f"ONBOARDING · sector={args.sector} · workspace={args.clave}")
    print("=" * 70)
    print(f"  nombre: {cfg['negocio_nombre']}")
    print(f"  moneda: {cfg['moneda']}")
    print(f"  alertas activas: {sum(1 for v in cfg['alertas'].values() if v)} reglas")
    print(f"  intervalos de mantenimiento: {len(cfg['mantenimiento'].get('intervalos_meses', {}))}")
    print(f"  tema: color primario {cfg['tema']['color_primario']}")
    print()
    print("Configuracion generada (lista para escribir en config.yaml):")
    import yaml
    print(yaml.dump(cfg, allow_unicode=True, sort_keys=False))

    if args.escribir:
        from pathlib import Path
        ruta = Path(args.escribir)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(yaml.dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"Escrito en: {ruta}")
    return 0


def cmd_scheduler(args):
    """Ejecuta el scheduler de jobs recurrentes del workspace."""
    import asyncio
    from src.scheduler import Scheduler

    cfg = _config(args)
    sched = Scheduler(cfg.directorio_datos, poll_interval_seconds=args.intervalo)
    print(f"Scheduler iniciado para workspace '{cfg.clave}' (intervalo {args.intervalo}s).")
    print("Presiona Ctrl+C para detener.")
    try:
        asyncio.run(sched.run())
    except KeyboardInterrupt:
        print("\nScheduler detenido.")
    return 0


def cmd_briefing(args):
    """Genera el briefing ejecutivo narrativo del workspace."""
    from src.alertas_avanzadas import evaluar_alertas_avanzadas
    from src.analyzer import Analyzer
    from src.briefing import generar_briefing
    from src.data_loader import load_all
    from src.negocio import salud_cartera

    cfg = _config(args)
    data = load_all(cfg)
    analyzer = Analyzer(data)
    kpis = analyzer.kpis_globales()
    salud = salud_cartera(analyzer)
    alertas = evaluar_alertas_avanzadas(cfg, data)

    texto = generar_briefing(data, kpis, alertas, salud, cfg)
    print("=" * 70)
    print("BRIEFING EJECUTIVO")
    print("=" * 70)
    print(texto)
    return 0


def cmd_memoria(args):
    """Muestra el ledger de decisiones del workspace (memoria operativa)."""
    from src.memoria import (
        inicializar_db, obtener_decisiones_recientes, listar_decisiones,
        obtener_iniciativas_activas, ruta_db_por_workspace,
    )

    cfg = _config(args)
    db_path = ruta_db_por_workspace(cfg.directorio_datos)
    inicializar_db(db_path)

    if args.accion == "decisiones":
        decisiones = obtener_decisiones_recientes(limite=args.limite, db_path=db_path)
        print("=" * 70)
        print(f"DECISIONES RECIENTES · workspace={cfg.clave}")
        print("=" * 70)
        if not decisiones:
            print("(sin decisiones registradas)")
        for d in decisiones:
            print(f"\n[{d.timestamp[:10]}] {d.dominio}: {d.resumen[:100]}")
            if d.justificacion:
                print(f"   justificacion: {d.justificacion[:120]}")
            if d.resultado:
                print(f"   resultado: {d.resultado[:120]}")
    elif args.accion == "iniciativas":
        iniciativas = obtener_iniciativas_activas(db_path=db_path)
        print("=" * 70)
        print(f"INICIATIVAS ACTIVAS · workspace={cfg.clave}")
        print("=" * 70)
        if not iniciativas:
            print("(sin iniciativas activas)")
        for i in iniciativas:
            print(f"\n- {i.titulo} [{i.estado}]")
            if i.resumen:
                print(f"   {i.resumen[:120]}")
    return 0


def cmd_usuarios(args):
    """Gestiona el registro de usuarios y los roles de acceso a la app."""
    from getpass import getpass

    from src.core import auth
    from src import workspaces as ws

    def _pass(args) -> str:
        if getattr(args, "password", None):
            return args.password
        return getpass(f"Contrasena para {args.username}: ")

    if args.accion == "listar":
        usuarios = auth.cargar_registro()
        if not usuarios:
            print(f"Sin usuarios registrados ({auth.ruta_registro()}).")
            print("Crea el primero con:  python main.py usuarios crear <nombre> --admin")
            return
        print(f"Registro: {auth.ruta_registro()}")
        print(f"Usuarios ({len(usuarios)}):")
        for u in sorted(usuarios.values(), key=lambda x: x.username):
            alcance = "todas las empresas" if u.es_admin else \
                (", ".join(u.workspaces) or "sin empresas asignadas")
            estado = "" if u.activo else "  [DESACTIVADO]"
            print(f"  - {u.username} ({u.rol}){estado}")
            print(f"      nombre: {u.nombre}")
            print(f"      acceso: {alcance}")

    elif args.accion == "crear":
        try:
            workspaces = ws.listar_workspaces() if args.todas else (args.workspace or [])
            u = auth.crear_usuario(
                args.username, _pass(args), nombre=args.nombre or args.username,
                rol=auth.ROL_ADMIN if args.admin else auth.ROL_CLIENTE,
                workspaces=workspaces, email=args.email or "")
        except ValueError as e:
            print(f"Error: {e}")
            raise SystemExit(1)
        alcance = "todas las empresas" if u.es_admin else (", ".join(u.workspaces) or "ninguna")
        print(f"Usuario '{u.username}' creado con rol '{u.rol}'")
        print(f"  acceso a: {alcance}")

    elif args.accion == "password":
        if not auth.actualizar_password(args.username, _pass(args)):
            print(f"Error: no existe el usuario '{args.username}'")
            raise SystemExit(1)
        print(f"Contrasena de '{args.username}' actualizada.")

    elif args.accion == "acceso":
        try:
            workspaces = ws.listar_workspaces() if args.todas else (args.workspace or [])
            usuarios = auth.cargar_registro()
            u = usuarios.get(args.username)
            if u is None:
                print(f"Error: no existe el usuario '{args.username}'")
                raise SystemExit(1)
            u.workspaces = workspaces
            if args.rol:
                u.rol = args.rol
            if args.activo is not None:
                u.activo = args.activo
            auth.guardar_registro(usuarios)
        except ValueError as e:
            print(f"Error: {e}")
            raise SystemExit(1)
        alcance = "todas las empresas" if u.es_admin else (", ".join(u.workspaces) or "ninguna")
        print(f"'{u.username}' → rol {u.rol} · acceso: {alcance} · "
              f"{'activo' if u.activo else 'desactivado'}")


def main():
    # Los avisos de los modulos (vista no creada, totales no parseables,
    # tablas huerfanas del warehouse) salen por logging y por CLI nadie los
    # veia: WARNING a stderr. Nada de INFO, que traeria el SQL de sqlalchemy.
    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="GIRO - Inteligencia de negocio")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    pr = subparsers.add_parser("resumen", help="Resumen de datos y KPIs")
    pr.add_argument("--data", type=str, default=None)
    pr.set_defaults(func=cmd_resumen)

    pe = subparsers.add_parser("etl", help="Ejecuta el pipeline ETL (DuckDB)")
    pe.add_argument("--data", type=str, default=None)
    pe.set_defaults(func=cmd_etl)

    pr = subparsers.add_parser("report", help="Genera reporte HTML")
    pr.add_argument("--data", type=str, default=None)
    pr.add_argument("--output", type=str, default=None)
    pr.add_argument("--abrir", action="store_true")
    pr.set_defaults(func=cmd_report)

    pp = subparsers.add_parser("predict", help="Ejecuta predicciones")
    pp.add_argument("--data", type=str, default=None)
    pp.add_argument("--tipo", type=str, default="todos",
                    choices=["ingresos", "demanda", "churn", "inventario", "todos"])
    pp.add_argument("--meses", type=int, default=6)
    pp.set_defaults(func=cmd_predict)

    pi = subparsers.add_parser("importar", help="Importa un archivo al directorio de datos")
    pi.add_argument("archivo", type=str)
    pi.add_argument("--data", type=str, default=None)
    pi.add_argument("--formato", type=str, default="auto")
    pi.add_argument("--dataset", type=str, default="auto")
    pi.set_defaults(func=cmd_importar)

    px = subparsers.add_parser("exportar", help="Exporta datasets a CSV/.sav/.por")
    px.add_argument("--data", type=str, default=None)
    px.add_argument("--dataset", type=str, default="todos")
    px.add_argument("--formato", type=str, default="csv", choices=["csv", "sav", "por"])
    px.set_defaults(func=cmd_exportar)

    pa = subparsers.add_parser("alertas", help="Evalua las reglas de negocio y genera reporte")
    pa.add_argument("--data", type=str, default=None)
    pa.add_argument("--reporte", action="store_true", help="Genera HTML en reports/")
    pa.add_argument("--enviar-email", action="store_true", help="Envia por SMTP si esta configurado")
    pa.set_defaults(func=cmd_alertas)

    pw = subparsers.add_parser("workspace", help="Gestion de workspaces (multiempresa)")
    pw_sub = pw.add_subparsers(dest="accion", required=True)
    pw_c = pw_sub.add_parser("crear", help="Crea un workspace")
    pw_c.add_argument("clave", type=str)
    pw_c.add_argument("--nombre", type=str, default=None)
    pw_c.add_argument("--moneda", type=str, default=None)
    pw_c.add_argument("--slogan", type=str, default=None)
    pw_c.add_argument("--sector", type=str, default=None,
                     help="Vertical: taller | clinica | retail | logistica")
    pw_c.add_argument("--muestra", action="store_true", help="Copiar datos de ejemplo")
    pw_c.set_defaults(func=cmd_workspace)
    pw_l = pw_sub.add_parser("listar", help="Lista los workspaces")
    pw_l.set_defaults(func=cmd_workspace)
    pw_f = pw_sub.add_parser("config", help="Muestra la configuracion de un workspace")
    pw_f.add_argument("clave", type=str)
    pw_f.set_defaults(func=cmd_workspace)
    pw_i = pw_sub.add_parser(
        "init-db", help="Crea las bases de Postgres que falten "
                        "(requiere GIRO_ALMACEN_MOTOR=postgres)")
    pw_i.set_defaults(func=cmd_workspace)

    pd = subparsers.add_parser("dashboard", help="Inicia el dashboard web")
    pd.add_argument("--data", type=str, default=None)
    pd.set_defaults(func=cmd_dashboard)

    pcon = subparsers.add_parser(
        "conector", help="Conectores ERP/SQL (sqlite, duckdb, csv, excel, url)")
    pcon.add_argument("accion", choices=["listar", "sincronizar", "seed-erp"],
                      help="listar: muestra los configurados · sincronizar: trae "
                           "datos al almacen · seed-erp: crea un snapshot SQLite demo")
    pcon.add_argument("--data", type=str, default=None)
    pcon.add_argument("--destino", type=str, default=None,
                      help="Ruta del snapshot (por defecto data/erp.sqlite)")
    pcon.add_argument("--usar", action="store_true",
                      help="seed-erp: registra los conectores en el config (forzar=true)")
    pcon.set_defaults(func=cmd_conector)

    pl = subparsers.add_parser("landing", help="Inicia la landing publica de ventas")
    pl.add_argument("--port", type=int, default=8502)
    pl.set_defaults(func=cmd_landing)

    pwh = subparsers.add_parser(
        "warehouse", help="Warehouse central (multi-DB): publica DuckDB a Postgres/MySQL/SQLite")
    pwh.add_argument("accion", choices=["sync", "ver"])
    pwh.add_argument("--dsn", type=str, required=True,
                     help="DSN SQLAlchemy del destino (postgresql://…, mysql://…, sqlite:///…)")
    pwh.add_argument("--esquemas", type=str, default="datasets,core,analitica")
    pwh.add_argument("--prefijo", type=str, default="giro_",
                     help="Prefijo de las tablas publicadas (default: giro_)")
    pwh.add_argument("--data", type=str, default=None)
    pwh.set_defaults(func=cmd_warehouse)

    prpt = subparsers.add_parser(
        "reporte", help="Reportes ejecutivos white-label (reventa)")
    prpt_sub = prpt.add_subparsers(dest="accion", required=True)
    prpt_l = prpt_sub.add_parser("listar", help="Tipos disponibles y generados")
    prpt_l.add_argument("--data", type=str, default=None)
    prpt_l.set_defaults(func=cmd_reporte)
    prpt_g = prpt_sub.add_parser(
        "generar", help="Genera reportes (resumen|ventas|clientes|inventario|predicciones|todos)")
    prpt_g.add_argument("--data", type=str, default=None)
    prpt_g.add_argument("--tipo", type=str, default="resumen",
                        help="Tipo de reporte o 'todos' (default: resumen)")
    prpt_g.add_argument("--periodo", type=str, default="",
                        help="Rotulo de portada, p. ej. 'Reporte mensual'")
    prpt_g.add_argument("--output", type=str, default=None,
                        help="Nombre del archivo HTML (opcional)")
    prpt_g.add_argument("--pdf", action="store_true",
                        help="Convierte a PDF si weasyprint esta instalado")
    prpt_g.add_argument("--enviar-email", action="store_true",
                        help="Envia por SMTP si esta configurado")
    prpt_g.add_argument("--abrir", action="store_true", help="Abre el reporte")
    prpt_g.set_defaults(func=cmd_reporte)

    # --- Usuarios y acceso (autenticacion de la app web) ---
    pu = subparsers.add_parser(
        "usuarios", help="Gestiona usuarios, roles y acceso a empresas")
    pu_g = pu.add_subparsers(dest="accion", required=True)

    pu_l = pu_g.add_parser("listar", help="Muestra el registro de usuarios")
    pu_l.set_defaults(func=cmd_usuarios)

    pu_c = pu_g.add_parser("crear", help="Crea un usuario")
    pu_c.add_argument("username", type=str, help="Nombre de usuario")
    pu_c.add_argument("--password", type=str, default=None,
                      help="Contrasena (si se omite, se pide de forma oculta)")
    pu_c.add_argument("--nombre", type=str, default=None, help="Nombre a mostrar")
    pu_c.add_argument("--email", type=str, default=None)
    pu_c.add_argument("--admin", action="store_true",
                      help="Admin: ve todas las empresas, usa la consola SQL")
    pu_c.add_argument("--workspace", type=str, action="append", default=[],
                      help="Empresa a la que accede (repetible)")
    pu_c.add_argument("--todas", action="store_true",
                      help="Le da acceso a todas las empresas existentes")
    pu_c.set_defaults(func=cmd_usuarios)

    pu_p = pu_g.add_parser("password", help="Cambia la contrasena de un usuario")
    pu_p.add_argument("username", type=str)
    pu_p.add_argument("--password", type=str, default=None)
    pu_p.set_defaults(func=cmd_usuarios)

    pu_a = pu_g.add_parser("acceso", help="Cambia rol, acceso o estado de un usuario")
    pu_a.add_argument("username", type=str)
    pu_a.add_argument("--rol", type=str, default=None, choices=["admin", "cliente"])
    pu_a.add_argument("--workspace", type=str, action="append", default=[])
    pu_a.add_argument("--todas", action="store_true")
    pu_a.add_argument("--activo", type=lambda v: v.lower() in ("1", "true", "si", "yes"),
                      default=None)
    pu_a.set_defaults(func=cmd_usuarios)

    # --- Evaluacion deterministica ---
    pev = subparsers.add_parser("eval", help="Ejecuta la suite de evaluacion deterministica")
    pev.set_defaults(func=cmd_eval)

    # --- Onboarding por sector vertical ---
    pon = subparsers.add_parser("onboarding", help="Genera config inicial de un workspace por sector")
    pon.add_argument("sector", type=str, help="Vertical: " + ", ".join(sorted(__import__("src.onboarding", fromlist=["SECTORES"]).SECTORES)))
    pon.add_argument("clave", type=str, help="Clave del workspace (p. ej. taller-don-juan)")
    pon.add_argument("--nombre", type=str, default=None, help="Nombre del negocio")
    pon.add_argument("--moneda", type=str, default=None, help="Moneda (p. ej. MXN, CLP, USD)")
    pon.add_argument("--escribir", type=str, default=None, help="Ruta donde escribir el config.yaml generado")
    pon.set_defaults(func=cmd_onboarding)

    # --- Scheduler de jobs recurrentes ---
    psc = subparsers.add_parser("scheduler", help="Ejecuta el scheduler de jobs recurrentes")
    psc.add_argument("--data", type=str, default=None)
    psc.add_argument("--intervalo", type=int, default=30, help="Segundos entre polls (default: 30)")
    psc.set_defaults(func=cmd_scheduler)

    # --- Briefing ejecutivo narrativo ---
    pbr = subparsers.add_parser("briefing", help="Genera el briefing ejecutivo narrativo")
    pbr.add_argument("--data", type=str, default=None)
    pbr.set_defaults(func=cmd_briefing)

    # --- Memoria operativa (ledger de decisiones) ---
    pme = subparsers.add_parser("memoria", help="Ledger de decisiones y memoria operativa del workspace")
    pme.add_argument("--data", type=str, default=None)
    pme_sub = pme.add_subparsers(dest="accion", required=True)
    pme_d = pme_sub.add_parser("decisiones", help="Muestra decisiones recientes")
    pme_d.add_argument("--limite", type=int, default=10)
    pme_d.set_defaults(func=cmd_memoria)
    pme_i = pme_sub.add_parser("iniciativas", help="Muestra iniciativas activas")
    pme_i.set_defaults(func=cmd_memoria)

    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, FileNotFoundError) as e:
        # Errores de entrada (clave de workspace invalida, workspace que no
        # existe, formato desconocido): mensaje y codigo de salida, no un
        # traceback que asuste a quien escribio el comando.
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1) from None

if __name__ == "__main__":
    main()