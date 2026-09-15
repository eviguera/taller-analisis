import csv
import random
from datetime import datetime, timedelta

random.seed(42)

NOMBRES = [
    "Carlos Ramirez", "Maria Lopez", "Juan Perez", "Ana Garcia", "Pedro Martinez",
    "Laura Hernandez", "Miguel Torres", "Sofia Diaz", "Fernando Ruiz", "Elena Morales",
    "Roberto Sanchez", "Carmen Flores", "Luis Aguilar", "Patricia Vargas", "Jorge Ramirez",
    "Isabel Cruz", "Antonio Reyes", "Rosa Mendez", "Francisco Ortiz", "Teresa Navarro",
    "Manuel Gutierrez", "Lucia Romero", "Ricardo Castillo", "Gabriela Ramos", "Alejandro Flores",
    "Daniela Herrera", "Enrique Mendoza", "Valeria Cruz", "Pablo Soto", "Adriana Medina",
    "Sergio Rojas", "Claudia Silva", "Andres Paredes", "Monica Vega", "Diego Contreras",
    "Laura Campos", "Rafael Luna", "Sandra Torres", "Oscar Guzman", "Mariana Delgado",
    "Felipe Cortez", "Gloria Estrada", "Raul Bravo", "Cristina Munoz", "Hector Fuentes",
    "Beatriz Salazar", "Julian Castro", "Nancy Mejia", "Gustavo Vargas", "Paola Rios"
]

MARCAS = ["Toyota", "Honda", "Ford", "Chevrolet", "Nissan", "Volkswagen", "Mazda", "Hyundai", "Kia", "BMW"]
MODELOS = {
    "Toyota": ["Corolla", "Camry", "Hilux", "RAV4", "Yaris"],
    "Honda": ["Civic", "Accord", "CR-V", "Fit", "HR-V"],
    "Ford": ["Focus", "Escape", "Ranger", "Explorer", "Edge"],
    "Chevrolet": ["Spark", "Onix", "Sail", "Tracker", "Cheyenne"],
    "Nissan": ["Sentra", "Versa", "Qashqai", "X-Trail", "March"],
    "Volkswagen": ["Golf", "Polo", "T-Cross", "Tiguan", "Jetta"],
    "Mazda": ["Mazda3", "Mazda6", "CX-5", "CX-30", "BT-50"],
    "Hyundai": ["i10", "Accent", "Tucson", "Creta", "Santa Fe"],
    "Kia": ["Rio", "Cerato", "Sportage", "Seltos", "Morning"],
    "BMW": ["Serie 3", "Serie 5", "X1", "X3", "X5"]
}

SERVICIOS = [
    ("Cambio de aceite", 800, 45),
    ("Frenos delanteros", 2500, 90),
    ("Frenos traseros", 2200, 80),
    ("Alineacion y balance", 600, 40),
    ("Cambio de llantas", 1500, 60),
    ("Diagnostico computarizado", 500, 30),
    ("Cambio de bujias", 700, 35),
    ("Revision de suspension", 400, 25),
    ("Cambio de correa", 1800, 70),
    ("Reparacion de motor", 8000, 240),
    ("Cambio de transmision", 6000, 180),
    ("Reparacion de suspension", 1200, 60),
    ("Cambio de bateria", 1500, 45),
    ("Limpieza de inyectores", 900, 50),
    ("Cambio de filtro de aire", 350, 20),
    ("Reparacion de electricidad", 500, 40),
    ("Cambio de antifreeze", 700, 30),
    ("Servicio de climatizacion", 900, 45),
    ("Cambio de aceite de transmision", 650, 35),
    ("Reparacion de turbo", 3500, 150),
]

REPUESTOS = [
    ("Aceite 5W30 4L", "Aceites", 350, 120, 25),
    ("Aceite 10W40 4L", "Aceites", 320, 110, 20),
    ("Filtro de aceite universal", "Filtros", 80, 35, 50),
    ("Filtro de aire universal", "Filtros", 95, 40, 45),
    ("Filtro de cabina", "Filtros", 120, 50, 30),
    ("Pastillas de freno delanteras", "Frenos", 450, 180, 35),
    ("Pastillas de freno traseras", "Frenos", 380, 150, 30),
    ("Disco de freno delantero", "Frenos", 600, 250, 20),
    ("Disco de freno trasero", "Frenos", 520, 210, 18),
    ("Bujia iridium", "Motor", 150, 65, 40),
    ("Correa de distribucion", "Motor", 350, 140, 15),
    ("Correa auxiliar", "Motor", 200, 85, 20),
    ("Amortiguador delantero", "Suspension", 800, 350, 12),
    ("Amortiguador trasero", "Suspension", 750, 320, 12),
    ("Brazo de suspension", "Suspension", 550, 230, 10),
    ("Bateria 60Ah", "Electrico", 1200, 500, 8),
    ("Bateria 100Ah", "Electrico", 1800, 750, 5),
    ("Llanta 195/65R15", "Llantas", 850, 450, 15),
    ("Llanta 205/55R16", "Llantas", 1100, 600, 10),
    ("Llanta 225/45R17", "Llantas", 1500, 800, 8),
    ("Refrigerante 4L", "Climatizacion", 280, 100, 18),
    ("Gas Refrigerante R134a", "Climatizacion", 400, 150, 12),
    ("Aceite de transmision ATF", "Transmision", 250, 95, 22),
    ("Filtro de transmision", "Transmision", 300, 120, 10),
]

MESES_VENTAS = {
    1: 0.85, 2: 0.90, 3: 1.10, 4: 1.05,
    5: 1.00, 6: 0.95, 7: 1.15, 8: 1.20,
    9: 1.10, 10: 1.05, 11: 0.90, 12: 1.30
}

def gen_clientes(n=50):
    rows = []
    for i in range(1, n + 1):
        nombre = random.choice(NOMBRES)
        tel = f"55{random.randint(10000000, 99999999)}"
        email = nombre.lower().replace(" ", ".") + "@email.com"
        fecha = datetime(2020, 1, 1) + timedelta(days=random.randint(0, 1500))
        rows.append([i, nombre, tel, email, fecha.strftime("%Y-%m-%d")])
    return rows

def gen_vehiculos(clientes):
    rows = []
    vid = 1
    for cid, *_ in clientes:
        n_veh = random.choices([1, 2, 3], weights=[0.5, 0.35, 0.15])[0]
        for _ in range(n_veh):
            marca = random.choice(MARCAS)
            modelo = random.choice(MODELOS[marca])
            anio = random.randint(2010, 2024)
            placa = f"{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.randint(1000,9999)}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"
            color = random.choice(["Blanco", "Negro", "Gris", "Rojo", "Azul", "Plata", "Verde"])
            km = random.randint(5000, 200000)
            rows.append([vid, cid, marca, modelo, anio, placa, color, km])
            vid += 1
    return rows

def gen_servicios(n=300):
    rows = []
    sid = 1
    base = datetime(2023, 1, 1)
    for _ in range(n):
        servicio_info = random.choice(SERVICIOS)
        nombre_serv = servicio_info[0]
        precio_base = servicio_info[1]
        tiempo = servicio_info[2]
        meses = random.randint(0, 30)
        dias = random.randint(0, 28)
        fecha = base + timedelta(days=meses * 30 + dias)
        mes = fecha.month
        precio = round(precio_base * random.uniform(0.9, 1.15) * MESES_VENTAS[mes], 2)
        rows.append([sid, nombre_serv, round(precio, 2), tiempo])
        sid += 1
    return rows

def gen_facturas(clientes, vehiculos, servicios_list, n=350):
    rows = []
    fid = 1
    base = datetime(2023, 1, 1)
    cliente_vehiculos = {}
    for v in vehiculos:
        cid = v[1]
        if cid not in cliente_vehiculos:
            cliente_vehiculos[cid] = []
        cliente_vehiculos[cid].append(v[0])

    for _ in range(n):
        cid = random.choice(list(cliente_vehiculos.keys()))
        vid = random.choice(cliente_vehiculos[cid])
        fecha = base + timedelta(days=random.randint(0, 800))
        n_servicios = random.choices([1, 2, 3, 4], weights=[0.4, 0.35, 0.15, 0.10])[0]
        serv_ids = random.sample(range(1, len(servicios_list) + 1), min(n_servicios, len(servicios_list)))

        total = 0
        detalles = []
        for sid in serv_ids:
            s = servicios_list[sid - 1]
            cantidad = random.randint(1, 3)
            subtotal = s[2] * cantidad
            total += subtotal
            detalles.append(f"{sid}:{cantidad}:{round(subtotal, 2)}")

        descuento = round(total * random.uniform(0, 0.10), 2) if random.random() < 0.2 else 0
        total_final = round(total - descuento, 2)
        estado = random.choices(
            ["Pagada", "Pendiente", "Cancelada"],
            weights=[0.75, 0.15, 0.10]
        )[0]

        rows.append([fid, cid, vid, fecha.strftime("%Y-%m-%d"), total_final, descuento, estado, ";".join(detalles)])
        fid += 1
    return rows

def gen_inventario(repuestos):
    rows = []
    iid = 1
    for nombre, cat, precio_venta, precio_costo, stock in repuestos:
        stock_actual = stock + random.randint(-5, 15)
        stock_actual = max(0, stock_actual)
        min_stock = max(2, stock // 3)
        ultima_venta = (datetime(2024, 6, 1) + timedelta(days=random.randint(0, 120))).strftime("%Y-%m-%d")
        rows.append([iid, nombre, cat, precio_costo, precio_venta, stock_actual, min_stock, ultima_venta])
        iid += 1
    return rows

def write_csv(filename, headers, rows):
    with open(filename, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    print(f"  {filename} - {len(rows)} registros")

if __name__ == "__main__":
    import os
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    print("Generando datos de ejemplo...")

    clientes = gen_clientes(50)
    write_csv(os.path.join(data_dir, "clientes.csv"),
              ["id", "nombre", "telefono", "email", "fecha_registro"], clientes)

    vehiculos = gen_vehiculos(clientes)
    write_csv(os.path.join(data_dir, "vehiculos.csv"),
              ["id", "cliente_id", "marca", "modelo", "anio", "placa", "color", "kilometraje"], vehiculos)

    servicios = gen_servicios(40)
    write_csv(os.path.join(data_dir, "servicios.csv"),
              ["id", "nombre", "precio_base", "tiempo_estimado_min"], servicios)

    facturas = gen_facturas(clientes, vehiculos, servicios, 350)
    write_csv(os.path.join(data_dir, "facturas.csv"),
              ["id", "cliente_id", "vehiculo_id", "fecha", "total", "descuento", "estado", "detalles"], facturas)

    inventario = gen_inventario(REPUESTOS)
    write_csv(os.path.join(data_dir, "inventario.csv"),
              ["id", "producto", "categoria", "precio_costo", "precio_venta", "stock_actual", "stock_minimo", "ultima_venta"], inventario)

    print("\nExportando version PSPP (.sav y .por) para probar la integracion...")
    try:
        import pandas as pd
        clientes_df = pd.DataFrame(clientes, columns=["id", "nombre", "telefono", "email", "fecha_registro"])
        clientes_df["fecha_registro"] = pd.to_datetime(clientes_df["fecha_registro"])
        facturas_df = pd.DataFrame(facturas, columns=["id", "cliente_id", "vehiculo_id", "fecha", "total", "descuento", "estado", "detalles"])
        facturas_df["fecha"] = pd.to_datetime(facturas_df["fecha"])
        estados = {"Pagada": 1, "Pendiente": 2, "Cancelada": 3}
        facturas_df["estado_cod"] = facturas_df["estado"].map(estados)

        from src.loaders.pspp_loader import exportar_sav, exportar_por
        etq = {
            "cliente_id": "Identificador del cliente",
            "total": "Monto total de la factura",
            "estado_cod": "Estado de la factura",
        }
        val = {
            "estado_cod": {1: "Pagada", 2: "Pendiente", 3: "Cancelada"},
            "cliente_id": {},  # dejar vacio para numerico
        }
        exportar_sav(clientes_df, os.path.join(data_dir, "clientes.sav"),
                     etiquetas_columnas={c: c.replace("_", " ").title() for c in clientes_df.columns},
                     label_archivo="Clientes del taller")
        print("  clientes.sav - exportado")
        exportar_sav(facturas_df[["id", "cliente_id", "fecha", "total", "estado_cod"]],
                     os.path.join(data_dir, "facturas.sav"),
                     etiquetas_columnas=etq, etiquetas_valores=val,
                     label_archivo="Facturas del taller")
        print("  facturas.sav - exportado")
        try:
            import pyreadstat
            if hasattr(pyreadstat, "write_por"):
                exportar_por(clientes_df.head(20), os.path.join(data_dir, "clientes.por"))
                exportar_por(facturas_df[["id", "cliente_id", "fecha", "total", "estado_cod"]].head(30),
                             os.path.join(data_dir, "facturas.por"))
                print("  clientes.por + facturas.por - exportados")
        except Exception as e:
            print(f"  (exportacion .por omitida: {e})")

    except Exception as e:
        print(f"  Advertencia: no se exporto .sav - {e}")

    print("\nDatos generados exitosamente!")
