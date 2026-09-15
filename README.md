# Sistema de Analisis de Datos para Taller Mecanico

Sistema completo para obtener informacion valiosa de los datos de un taller mecanico:
analisis de clientes, servicios, vehiculos, inventario y predicciones (ingresos,
demanda, churn y reposicion de inventario).

## Requisitos

- Python 3.10+
- Instalar dependencias: `pip install -r requirements.txt`

## Estructura

```
taller-analisis/
├── data/                    # Archivos CSV con los datos del taller
│   ├── clientes.csv         # id, nombre, telefono, email, fecha_registro
│   ├── vehiculos.csv        # id, cliente_id, marca, modelo, anio, placa, color, kilometraje
│   ├── servicios.csv        # id, nombre, precio_base, tiempo_estimado_min
│   ├── facturas.csv         # id, cliente_id, vehiculo_id, fecha, total, descuento, estado, detalles
│   └── inventario.csv       # id, producto, categoria, precio_costo, precio_venta, stock_actual, stock_minimo
├── src/
│   ├── data_loader.py       # Carga y limpieza de datos
│   ├── analyzer.py          # Analisis exploratorio (KPIs, RFM, estacionalidad)
│   ├── predictions.py       # Modelos de prediccion
│   └── reports.py           # Generacion de reportes HTML
├── dashboard.py             # Dashboard web interactivo (Streamlit)
├── generate_data.py         # Genera datos de ejemplo (opcional)
├── main.py                  # Interfaz de linea de comandos
└── reports/                 # Reportes HTML generados
```

## Uso

### 1. Dashboard web (recomendado)

```bash
python main.py dashboard
# o directamente:
streamlit run dashboard.py
```

Se abrira en el navegador (por defecto http://localhost:8501) con secciones:
- **Resumen General**: KPIs, filtros de fecha, ingresos y estacionalidad
- **Clientes**: segmentacion RFM, top clientes
- **Servicios**: servicios mas solicitados y series de tiempo
- **Vehiculos**: analisis por marca, antiguedad y kilometraje
- **Inventario**: estado del stock y recomendaciones de reposicion
- **Predicciones**: ingresos, demanda, churn e inventario
- **Reporte**: generacion de reporte HTML descargable

### 2. Linea de comandos

```bash
# Resumen de los datos y KPIs
python main.py resumen

# Generar reporte HTML (se guarda en reports/)
python main.py report --abrir

# Predicciones (ingresos, demanda, churn, inventario)
python main.py predict --tipo todos --meses 6

# Prediccion especifica
python main.py predict --tipo churn
```

### 3. Usar tus propios datos

Reemplaza los archivos CSV en `data/` con los tuyos, manteniendo las mismas
columnas. Si tus datos estan en otro directorio:

```bash
python main.py resumen --data /ruta/a/tus/datos
python main.py dashboard --data /ruta/a/tus/datos
```

## Predicciones incluidas

| Tipo | Metodo | Que predice |
|---|---|---|
| Ingresos | Gradient Boosting + lags | Ingresos mensuales a futuro |
| Demanda | Regresion Lineal | Demanda de cada servicio |
| Churn | Random Forest + RFM | Probabilidad de que un cliente deje de visitar |
| Inventario | Reglas de negocio | Rotacion, cobertura y reposicion |

## Despliegue gratis (escalabilidad a costo cero)

Todo el stack es software libre (Streamlit Apache-2.0, DuckDB MIT, pandas/scikit-learn BSD,
plotly MIT, PSPP Apache-2.0). No hay licencias ni royalties que pagar; solo gastarias
infraestructura si algun dia superas los planes gratuitos.

### Opcion A - Streamlit Community Cloud (recomendada para demo/pitch)

1. Sube el proyecto a un repositorio en GitHub (no incluyas `data/almacen.duckdb`,
   `data/cache/` ni `data/export/`; se regeneran solos al ejecutar el ETL).
2. Entra a https://share.streamlit.io y crea una app nueva desde el repo.
3. Configura: main file `dashboard.py`, Python 3.11.
4. En pocos minutos tienes una URL publica gratuita `https://tu-app.streamlit.app`.

### Opcion B - Hugging Face Spaces (plan CPU gratuito)

El repositorio ya incluye un `Dockerfile` listo para Spaces:

1. Crea un Space: https://huggingface.co/new-space (SDK: Docker).
2. Sube el proyecto (git push) con `requirements.txt`, `Dockerfile` y `data/`.
3. Espera el build y abre la URL `https://hf.co/spaces/<usuario>/<space>`.

### Opcion C - Prueba de escalado sin costo (VPS gratuita)

Si quieres medir rendimiento con muchos usuarios antes de invertir:

- **Oracle Cloud Always Free** o **AWS/GCP free tier*: una VM gratuita donde ejecutar
  `docker build -t taller .` y `docker run -p 8501:8501 taller`.
- **DNS/subdominio gratuitos**: `*.streamlit.app` o `*.hf.space` cubren el enlace público.

### Notas de despliegue

- `data/almacen.duckdb`, `data/cache/` y `data/export/` se regeneran automaticamente
  al procesar el ETL; no es necesario subirlos a git.
- Las predicciones (scikit-learn) se recalculan sobre los datos cargados; no requiere
  servicios externos pagos.
- Si el volumen crece, DuckDB puede apuntar a un Postgres gratuito (p. ej. Neon/Supabase)
  sin cambiar la interfaz: reconstruir el esquema en `core`/`analitica`.

## Datos de ejemplo

`generate_data.py` crea 50 clientes, 88 vehiculos, 40 servicios, 350 facturas
y 24 productos de inventario con datos realistas ficticios.