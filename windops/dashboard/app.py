"""WindOps 360 dashboard (Streamlit).

The dashboard never computes business rules itself: every number comes
from the API, so the screen and the API always agree.

Run from the project root (so .streamlit/config.toml is picked up):
    streamlit run windops/dashboard/app.py
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from windops.config import API_URL, ENERGY_PRICE_BRL_PER_MWH
from windops.core.generator import history_window
from windops.dashboard import client, views
from windops.dashboard.theme import inject_css

st.set_page_config(page_title="WindOps 360", page_icon=":material/wind_power:", layout="wide")
inject_css()

if not client.is_available():
    st.error(
        f"A API não respondeu em {API_URL}. Inicie com `uvicorn windops.api.main:app` "
        "ou suba tudo com `docker compose up` e recarregue a página."
    )
    st.stop()

# ---------- sidebar ----------
history_start, history_end = history_window()
last_year_start = history_end.replace(year=history_end.year - 1)

with st.sidebar:
    st.markdown("## :material/wind_power: WindOps 360")
    st.caption("Manutenção e performance de parques eólicos")

    companies = client.get("/companies")
    options = {"Todas as empresas": None} | {c["name"]: c["id"] for c in companies}
    company_label = st.selectbox("Empresa", list(options))
    company_id = options[company_label]

    period = st.date_input(
        "Período",
        value=(last_year_start.date(), (history_end - timedelta(days=1)).date()),
        min_value=date(2015, 1, 1),
        format="DD/MM/YYYY",
        help="Os indicadores são comparados com o período anterior de mesma duração.",
    )
    if not isinstance(period, tuple) or len(period) != 2:
        st.info("Escolha a data final do período.")
        st.stop()

    price = st.number_input("Preço da energia (R$/MWh)", min_value=0.0, value=ENERGY_PRICE_BRL_PER_MWH, step=10.0)
    target = st.slider("Meta de disponibilidade", 90.0, 99.5, 97.0, 0.5, format="%.1f%%") / 100

    st.divider()
    st.caption("Dados sintéticos gerados para demonstração. O preço da energia é uma premissa, não uma cotação.")

start = datetime.combine(period[0], time.min)
end = datetime.combine(period[1], time.min) + timedelta(days=1)
previous_start = start - (end - start)

base = {"company_id": company_id, "start": start.isoformat(), "end": end.isoformat(), "price": price}
overview = client.get("/overview", base)
previous = client.get("/overview", base | {"start": previous_start.isoformat(), "end": start.isoformat()})
reports = pd.DataFrame(client.get("/kpis/turbines", base))
alerts = client.get("/alerts", base | {"availability_target": target})

turbine_labels = {}
if not reports.empty:
    turbine_labels = {
        int(r.turbine_id): f"{r.turbine_code} ({r.company_name}, {r.farm_name})" for r in reports.itertuples()
    }

ctx = views.Context(
    company_id=company_id,
    company_label=company_label,
    start=start,
    end=end,
    price=price,
    target=target,
    reports=reports,
    overview=overview,
    previous=previous,
    alerts=alerts,
    turbine_labels=turbine_labels,
)

critical = sum(1 for a in alerts if a["severity"] == "critical")
tabs = st.tabs(
    [
        "Visão geral",
        "Raio-X da turbina",
        "Falhas",
        "Manutenções",
        "Priorização",
        f"Alertas ({len(alerts)})" if not critical else f"Alertas ({critical} críticos)",
    ]
)
for tab, render in zip(
    tabs, [views.overview, views.turbine, views.failures, views.maintenance, views.priority, views.alerts], strict=True
):
    with tab:
        render(ctx)
