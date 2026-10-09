"""Pagina: Inventario (stock, valor, reposicion y rotacion)."""

import pandas as pd
import streamlit as st

from ui import components as c
from ui.context import obtener_estado


def principal():
    cfg, data, analyzer, predictor = obtener_estado()

    inv = analyzer.inventario_data()
    c.cabecera(
        "Inventario",
        "Niveles de stock, valor y rotacion de repuestos",
        icono=":material/inventory_2:",
    )
    if inv.empty:
        c.vacio(
            "No hay datos de inventario.",
            icono=":material/inventory_2:",
            detalle="Importa tu inventario en 'Mis datos' para continuar.",
        )
        return

    with st.spinner("Calculando la reposicion sugerida..."):
        pred_inv = predictor.predecir_inventario()

    valor_total = inv["valor_inventario"].sum()
    stock_bajo = int((inv["estado_stock"] == "Bajo").sum())
    reabastecer = int((pred_inv["recomendacion"] == "Reabastecer").sum())
    margen_prom = inv["margen_pct"].mean()

    c.kpi_grid([
        ("Productos", c.miles(len(inv)), None, None, "Productos en catalogo"),
        ("Valor del inventario", c.moneda(valor_total, cfg.moneda), None, None,
         "Valor total de la mercancia"),
        ("Stock bajo", c.miles(stock_bajo), None, None, "Productos por debajo del minimo"),
        ("Para reabastecer", c.miles(reabastecer), None, None, "Productos que requieren pedido"),
        ("Margen promedio", f"{margen_prom:.0f}%", None, None, "Margen de ganancia promedio"),
    ])

    tab_estado, tab_stock, tab_repos, tab_margen, tab_tabla = st.tabs(
        ["Estado del stock", "Niveles de stock", "Reposicion", "Margenes", "Todos los productos"],
        key="tabs_inventario", on_change="rerun",
    )

    columnas_tabla = {
        "producto": st.column_config.TextColumn("Producto"),
        "categoria": st.column_config.TextColumn("Categoria"),
        "stock_actual": st.column_config.NumberColumn("Stock actual"),
        "stock_minimo": st.column_config.NumberColumn("Stock minimo"),
        "estado_stock": st.column_config.TextColumn("Estado"),
        "valor_inventario": st.column_config.NumberColumn("Valor", format=c.formato_moneda(cfg.moneda)),
        "valor_stock": st.column_config.NumberColumn("Valor stock", format=c.formato_moneda(cfg.moneda)),
        "margen_unitario": st.column_config.NumberColumn("Margen unit.", format=c.formato_moneda(cfg.moneda)),
        "precio_costo": st.column_config.NumberColumn("Costo", format=c.formato_moneda(cfg.moneda)),
        "precio_venta": st.column_config.NumberColumn("Venta", format=c.formato_moneda(cfg.moneda)),
        "margen_pct": st.column_config.NumberColumn("Margen %", format="%.0f%%"),
    }

    with tab_estado:
        if tab_estado.open:
            estado = inv["estado_stock"].value_counts().reset_index()
            estado.columns = ["Estado", "Cantidad"]
            col1, col2 = st.columns(2, vertical_alignment="center")
            with col1:
                with c.panel("Estado del stock", "Salud general del inventario"):
                    c.mostrar_grafico(c.grafico_pastel(estado, "Estado", "Cantidad"),
                                    width="stretch", height="stretch")
            with col2:
                with c.panel("Desglose por categoria", "Stock y valor por familia de producto"):
                    cat = inv.groupby("categoria").agg(
                        productos=("id", "count"),
                        stock_total=("stock_actual", "sum"),
                        valor=("valor_inventario", "sum"),
                    ).sort_values("valor", ascending=False).reset_index()
                    st.dataframe(cat, width="stretch", column_config={
                        "categoria": st.column_config.TextColumn("Categoria"),
                        "productos": st.column_config.NumberColumn("Productos"),
                        "stock_total": st.column_config.NumberColumn("Unidades en stock"),
                        "valor": st.column_config.NumberColumn("Valor", format=c.formato_moneda(cfg.moneda)),
                    })

    with tab_stock:
        if tab_stock.open:
            orden = inv.sort_values("stock_actual", ascending=False)
            with c.panel("Stock actual por producto", "Unidades disponibles por articulo",
                         icono=":material/warehouse:"):
                c.mostrar_grafico(c.grafico_barras(
                    orden, "producto", "stock_actual", color="estado_stock",
                    etiquetas={"producto": "Producto", "stock_actual": "Unidades"},
                ), width="stretch", height="stretch")

    with tab_repos:
        if tab_repos.open:
            orden_repo = pred_inv.sort_values("meses_cobertura", ascending=True)
            with c.panel("Meses de cobertura", "Menor cobertura = mayor urgencia",
                         icono=":material/update:"):
                c.mostrar_grafico(c.grafico_barras(
                    orden_repo, "producto", "meses_cobertura", color="recomendacion",
                    etiquetas={"producto": "Producto", "meses_cobertura": "Meses"},
                ), width="stretch", height="stretch")
            faltan = pred_inv[pred_inv["recomendacion"] == "Reabastecer"]
            if not faltan.empty:
                st.warning(f"Hay {c.miles(len(faltan))} productos que requieren pedido inmediato.",
                           icon=":material/priority_high:")
                with c.panel("Detalle del pedido", "Unidades a pedir de cada producto"):
                    st.dataframe(
                        faltan[["producto", "categoria", "stock_actual", "stock_minimo",
                                "demanda_mensual", "meses_cobertura", "cantidad_recomendada"]],
                        width="stretch",
                        column_config={
                            "producto": st.column_config.TextColumn("Producto"),
                            "categoria": st.column_config.TextColumn("Categoria"),
                            "stock_actual": st.column_config.NumberColumn("Stock actual"),
                            "stock_minimo": st.column_config.NumberColumn("Stock minimo"),
                            "demanda_mensual": st.column_config.NumberColumn("Demanda (unid/mes)", format="%.1f"),
                            "meses_cobertura": st.column_config.NumberColumn("Cobertura (meses)", format="%.1f"),
                            "cantidad_recomendada": st.column_config.NumberColumn("Pedir (unid)"),
                        },
                    )
            else:
                st.success("Stock suficiente: no hay productos criticos.", icon=":material/verified:")

    with tab_margen:
        if tab_margen.open:
            marg = inv.sort_values("margen_pct", ascending=False)
            with c.panel("Margen por producto (%)", "Rentabilidad unitaria",
                         icono=":material/percent:"):
                c.mostrar_grafico(c.grafico_barras(
                    marg, "producto", "margen_pct", color_cont="Tealgrn",
                    etiquetas={"producto": "Producto", "margen_pct": "Margen %"},
                ), width="stretch", height="stretch")

    with tab_tabla:
        if tab_tabla.open:
            st.dataframe(
                inv[["producto", "categoria", "precio_costo", "precio_venta", "stock_actual",
                     "stock_minimo", "margen_pct", "estado_stock", "valor_inventario"]],
                width="stretch", height=380, column_config=columnas_tabla,
            )


if __name__ == "__main__":
    principal()