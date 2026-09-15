"""CLI de GIRO, inteligencia de negocio.

Uso:
    python main.py resumen [--data DIR]
    python main.py etl [--data DIR]
    python main.py report [--output NOMBRE] [--abrir]
    python main.py predict [--tipo ingresos|demanda|churn|inventario|todos] [--meses N]
    python main.py importar <archivo> [--formato auto] [--dataset CLIENTES]
    python main.py exportar [--dataset TODOS] [--formato sav|csv]
    python main.py dashboard
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from src.core.config_manager import cargar_config
from src.core.pipeline import procesar_etl, load_all
from src.core.catalog import escanear_directorio, clasificar_archivo
from src.data_loader import get_data_summary
from src.analyzer import Analyzer
from src.predictions import Predictor
from src.reports import ReportGenerator

BASE_DIR = Path(__file__).parent


def _config(args):
    cfg = cargar_config()
    if getattr(args, "data", None):
        cfg.directorio_datos = Path(args.data)
    return cfg


def _formato(valor, dec=0):
    """Formatea con punto como separador de miles (es-CL)."""
    return f"{valor:,.{dec}f}".replace(",", ".")


def _moneda(valor, cfg):
    s = {"MXN": "$", "USD": "$", "EUR": "€"}.get(cfg.moneda, "$")
    return f"{s}{_formato(valor, 2)}"


def cmd_resumen(args):
    cfg = _config(args)
    print("=" * 70)
    print("RESUMEN DE NEGOCIO")
    print("=" * 70)
    data = load_all(cfg)
    for nombre, info in get_data_summary(data).items():
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
    resultado = procesar_etl(cfg)
    print(f"\nTablas registradas en DuckDB ({resultado.tiempo_carga}s):")
    for tabla, filas in resultado.tablas_registradas.items():
        print(f"  - {tabla}: {_formato(filas)} filas")
    if resultado.estructura:
        print("\nEsquema core materializado con claves:")
        for tabla, filas in resultado.estructura.items():
            print(f"  - core.{tabla}: {_formato(filas)} filas")
        print("  - vistas analiticas creadas en el almacen")
    if resultado.errores:
        print("\nErrores:")
        for n, e in resultado.errores.items():
            print(f"  - {n}: {e}")
    print("\nOK" if resultado.ok else "\nCOMPLETADO CON ERRORES")


def cmd_report(args):
    data, cfg = cmd_resumen(args)
    print("\n\nGenerando reporte HTML...")
    ruta, contenido = ReportGenerator(data).generar(args.output)
    print(f"Reporte generado en: {ruta}")
    if args.abrir:
        os.system(f"open '{ruta}'")


def cmd_predict(args):
    cfg = _config(args)
    data = load_all(cfg)
    predictor = Predictor(data)
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
    if args.dataset and args.dataset.lower() not in ("todos", "all"):
        datasets_sel = {args.dataset.lower(): data.get(args.dataset.lower(), None)}
    else:
        datasets_sel = data

    out = Path(cfg.directorio_datos) / "export"
    out.mkdir(parents=True, exist_ok=True)
    for nombre, df in datasets_sel.items():
        if df is None or (hasattr(df, "empty") and df.empty):
            continue
        if args.formato == "sav":
            from src.loaders.pspp_loader import exportar_sav
            exportar_sav(df, out / f"{nombre}.sav", label_archivo=f"{nombre} exportado")
            print(f"  {nombre}.sav -> {out}")
        elif args.formato == "por":
            from src.loaders.pspp_loader import exportar_por
            exportar_por(df, out / f"{nombre}.por")
            print(f"  {nombre}.por -> {out}")
        else:
            df.to_csv(out / f"{nombre}.csv", index=False, encoding="utf-8-sig")
            print(f"  {nombre}.csv -> {out}")


def cmd_dashboard(args):
    print("Iniciando dashboard web (Streamlit)...")
    cmd = [sys.executable, "-m", "streamlit", "run", str(BASE_DIR / "dashboard.py")]
    subprocess.run(cmd)


def main():
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

    pd = subparsers.add_parser("dashboard", help="Inicia el dashboard web")
    pd.add_argument("--data", type=str, default=None)
    pd.set_defaults(func=cmd_dashboard)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()