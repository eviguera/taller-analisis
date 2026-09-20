"""Lectura estrategica automatica: insights basados en reglas sobre los datos.

Convierte los numeros en frases accionables para la direccion sin intervencion
manual. Cada insight tiene un tipo que define su tono visual en el reporte:
    positivo  - oportunidad o fortaleza
    negativo  - riesgo que requiere atencion
    apunte    - observacion neutra/contexto
"""


from .formato import moneda as _moneda


def _tendencia(ingresos_por_mes, n=3):
    """Var. de ingresos comparando los ultimos n meses vs los n anteriores."""
    serie = ingresos_por_mes["total"].tolist()
    if len(serie) < n + 1:
        return None, None
    recientes = sum(serie[-n:])
    previos = sum(serie[-2 * n:-n])
    if not previos:
        return None, None
    cambio = (recientes - previos) / previos
    return recientes, cambio


def generar_insights(analyzer, kpis, moneda="CLP", inventario_critico=0) -> list:
    """Construye la lista de insights a partir del analizador y los KPIs."""
    insights = []
    df = analyzer.df

    # 1) Tendencia de ingresos reciente vs previa
    serie = analyzer.ingresos_por_mes()
    recientes, cambio = _tendencia(serie)
    if cambio is not None:
        if cambio >= 0.05:
            insights.append({
                "tipo": "positivo",
                "titulo": "Los ingresos estan creciendo",
                "texto": (f"En los ultimos 3 meses se facturaron "
                          f"{_moneda(recientes, moneda)} de ingresos, con "
                          f"{cambio:+.0%} de variacion frente al trimestre anterior."),
            })
        elif cambio <= -0.05:
            insights.append({
                "tipo": "negativo",
                "titulo": "Los ingresos bajaron",
                "texto": (f"En los ultimos 3 meses los ingresos caen {cambio:.0%} "
                          "frente al trimestre anterior; conviene revisar clientes, "
                          "precios y esfuerzo comercial."),
            })
        else:
            insights.append({
                "tipo": "apunte",
                "titulo": "Ingresos estables",
                "texto": "Los ultimos 3 meses se mantienen dentro de la tendencia "
                         "del periodo anterior (variacion despreciable).",
            })

    # 2) Concentracion del ingreso en pocos clientes (riesgo por dependencia)
    if "cliente_id" in df.columns and "total" in df.columns:
        top = df.groupby("cliente_id")["total"].sum().sort_values(ascending=False)
        total = top.sum()
        if total > 0:
            share_top10 = top.head(10).sum() / total
            if share_top10 >= 0.5:
                insights.append({
                    "tipo": "negativo",
                    "titulo": "Dependencia de pocos clientes",
                    "texto": (f"El {share_top10:.0%} del ingreso se concentra en los "
                              "10 principales clientes. Una cartera mas diversa "
                              "protege el resultado ante perdidas puntuales."),
                })
            else:
                insights.append({
                    "tipo": "positivo",
                    "titulo": "Cartera diversificada",
                    "texto": f"Los 10 principales clientes aportan el {share_top10:.0%} "
                             "del ingreso, una concentracion razonable.",
                })

    # 3) Estacionalidad: pico y valle del ano
    est = analyzer.estacionalidad()
    por_mes = est.get("por_mes")
    if por_mes is not None and not por_mes.empty and por_mes["ingresos"].sum() > 0:
        pico = int(por_mes.loc[por_mes["ingresos"].idxmax(), "mes"])
        valle = int(por_mes.loc[por_mes["ingresos"].idxmin(), "mes"])
        if pico != valle:
            insights.append({
                "tipo": "apunte",
                "titulo": "Estacionalidad marcada",
                "texto": (f"El negocio concentra demanda en los meses de pico "
                          f"(mes {pico}) y cae en {valle}. Anticipe stock y "
                          "personal para el pico y refuerce la captacion en el valle."),
            })

    # 4) Valor del cliente y frecuencia de visita
    if kpis.get("ticket_promedio") and kpis.get("clientes_activos"):
        visita_prom = kpis["total_facturas"] / kpis["clientes_activos"]
        insights.append({
            "tipo": "apunte" if visita_prom < 2 else "positivo",
            "titulo": "Frecuencia de visita",
            "texto": (f"En promedio cada cliente activo visita "
                      f"{visita_prom:.1f} veces en el periodo con un ticket "
                      f"promedio de {_moneda(kpis['ticket_promedio'], moneda)}. "
                      "Subir la frecuencia o el ticket amplia el valor de vida del cliente."),
        })

    # 5) Segmentacion RFM: campeones vs riesgo/perdido
    rfm = analyzer.clientes_rfm()
    if not rfm.empty:
        campeones = int((rfm["segmento"] == "Campeones").sum())
        en_riesgo = int(rfm["segmento"].isin(["En Riesgo", "Perdido"]).sum())
        total_clientes = len(rfm)
        if campeones > 0:
            insights.append({
                "tipo": "positivo",
                "titulo": "Clientes Campeones",
                "texto": (f"{campeones} de {total_clientes} clientes son 'Campeones' "
                          "(recientes, frecuentes y de alto valor). Un plan de "
                          "fidelidad protege a este grupo que sostiene el ingreso."),
            })
        if en_riesgo > 0:
            insights.append({
                "tipo": "negativo",
                "titulo": "Clientes en riesgo de abandono",
                "texto": (f"{en_riesgo} de {total_clientes} clientes muestran senales "
                          "de abandono (poca recencia o frecuencia baja). Activarlos "
                          "con recordatorios y ofertas evita perderlos."),
            })

    # 6) Inventario critico
    if inventario_critico:
        insights.append({
            "tipo": "negativo",
            "titulo": "Productos bajo el minimo",
            "texto": f"{inventario_critico} productos estan bajo su stock minimo. "
                     "Reabastecerlos evita perder ventas por faltante.",
        })

    # 7) Ticket promedio por servicio mas demandado (contexto)
    servicios = analyzer.servicios_mas_solicitados()
    if not servicios.empty and len(servicios):
        mas_vendido = servicios.iloc[0]
        insights.append({
            "tipo": "apunte",
            "titulo": "Servicio mas demandado",
            "texto": (f"'{mas_vendido['servicio']}' encabeza la demanda con "
                      f"{int(mas_vendido['frecuencia'])} solicitudes. Es un buen "
                      "candidato para promocionar o cruzar con otros servicios."),
        })

    return insights[:6]