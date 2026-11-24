"""One function per tab. Each receives the shared context built in app.py."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from html import escape

import pandas as pd
import streamlit as st

from windops.core.entities import Component, FailureCause
from windops.dashboard import charts, client
from windops.dashboard.components import (
    Cell,
    alert_rows,
    briefing,
    farm_row,
    hero_turbine,
    overview_cells,
    rotor_period_from_wind,
    strip,
    turbine_status,
)
from windops.dashboard.theme import (
    CAUSE_PT,
    COMPONENT_PT,
    SIGNAL_COLORS,
    SIGNAL_MAX,
    SIGNAL_PT,
    brl_compact,
    hours,
    number,
    pct,
)

PLOT_CONFIG = {"displayModeBar": False}
DATE_COL = st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")
FAILURE_COLUMNS = {
    "Falha": st.column_config.NumberColumn(format="%d", width="small"),
    "Início": DATE_COL,
    "Duração (h)": st.column_config.NumberColumn(format="%.1f"),
}
MAINTENANCE_COLUMNS = {
    "Nº": st.column_config.NumberColumn(format="%d", width="small"),
    "Início": DATE_COL,
    "Fim": DATE_COL,
    "Falha": st.column_config.TextColumn(width="small"),
}


@dataclass
class Context:
    company_id: int | None
    company_label: str
    start: datetime
    end: datetime
    price: float
    target: float
    reports: pd.DataFrame
    overview: dict
    previous: dict | None
    alerts: list[dict]
    turbine_labels: dict[int, str] = field(default_factory=dict)

    @property
    def params(self) -> dict:
        return {
            "company_id": self.company_id,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "price": self.price,
        }


def plot(fig) -> None:
    st.plotly_chart(fig, config=PLOT_CONFIG, width="stretch")


def _failures(ctx: Context, **extra) -> pd.DataFrame:
    params = {"company_id": ctx.company_id, "start": ctx.start.isoformat(), "end": ctx.end.isoformat(), "limit": 2000}
    return pd.DataFrame(client.get("/failures", params | extra))


def _maintenances(ctx: Context, **extra) -> pd.DataFrame:
    params = {"company_id": ctx.company_id, "start": ctx.start.isoformat(), "end": ctx.end.isoformat(), "limit": 2000}
    return pd.DataFrame(client.get("/maintenances", params | extra))


def _empty(message: str) -> None:
    st.info(message)


# ---------- overview ----------
def overview(ctx: Context) -> None:
    top = ctx.reports.iloc[0].to_dict() if not ctx.reports.empty else None
    briefing(ctx.start, ctx.end, ctx.overview, top, ctx.alerts)
    strip(overview_cells(ctx.overview, ctx.previous))

    st.subheader("Energia não gerada mês a mês")
    monthly = pd.DataFrame(client.get("/financials/monthly", ctx.params))
    plot(charts.monthly_loss(monthly, ctx.start, ctx.end))
    st.markdown(
        '<p class="note">A área sombreada é a temporada de ventos fortes: a mesma parada custa mais ali.</p>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 1.15], gap="large")
    with left:
        st.subheader("Disponibilidade por parque")
        farms = pd.DataFrame(client.get("/financials/summary", ctx.params | {"level": "farm"}))
        if farms.empty:
            _empty("Sem parques para os filtros escolhidos.")
        else:
            plot(charts.availability_by_farm(farms, ctx.target))
    with right:
        st.subheader("Onde está o prejuízo")
        if ctx.reports.empty or ctx.reports["loss_brl"].sum() == 0:
            _empty("Sem perdas no período.")
        else:
            plot(charts.loss_tree(ctx.reports))
            st.markdown(
                '<p class="note">Tamanho = R$ perdido. Cor = criticidade (azul claro baixa, vermelho alta).</p>',
                unsafe_allow_html=True,
            )

    st.subheader("Quais componentes mais seguram as turbinas paradas")
    failures = _failures(ctx)
    if failures.empty or failures["duration_hours"].dropna().empty:
        _empty("Nenhuma falha encerrada no período.")
    else:
        plot(charts.component_pareto(failures))


# ---------- turbine drill-down ----------
def turbine(ctx: Context) -> None:
    if ctx.reports.empty:
        _empty("Nenhuma turbina para os filtros escolhidos.")
        return
    ids = ctx.reports["turbine_id"].tolist()  # already sorted by criticality
    turbine_id = st.selectbox(
        "Turbina",
        ids,
        format_func=lambda i: (
            f"{ctx.turbine_labels[i]}  ·  criticidade "
            f"{number(float(ctx.reports.set_index('turbine_id').loc[i, 'criticality']))}"
        ),
        help="Ordenadas da mais crítica para a menos crítica.",
    )
    row = ctx.reports.set_index("turbine_id").loc[turbine_id]
    info = client.get(f"/turbines/{turbine_id}")
    fleet = ctx.reports

    failures = _failures(ctx, turbine_id=turbine_id)
    maintenances = _maintenances(ctx, turbine_id=turbine_id)

    # --- animated turbine: speed = farm's mean wind; still + red light when stopped ---
    stopped = bool(row["stopped_at_end"])
    light, _ = turbine_status(stopped, row["availability"], ctx.target)
    period = None if stopped else rotor_period_from_wind(row["mean_wind_ms"], info["cut_in_ms"])
    if stopped:
        running = (
            failures[failures["ended_at"].isna() | (pd.to_datetime(failures["ended_at"]) > ctx.end)]
            if not failures.empty
            else failures
        )
        if running.empty:
            status = "Parada no fim do período, por uma falha iniciada antes dele. Rotor parado."
        else:
            f = running.iloc[0]
            status = (
                f"Parada no fim do período: falha #{f['id']} ({COMPONENT_PT[f['component']].lower()}) "
                f"desde {pd.Timestamp(f['started_at']):%d/%m %H:%M}. Rotor parado."
            )
    elif period is None:
        status = f"Vento médio de {number(row['mean_wind_ms'])} m/s, abaixo do cut-in. Rotor parado."
    else:
        status = (
            f"Em operação. Vento médio de {number(row['mean_wind_ms'])} m/s no período: "
            "o rotor gira proporcional a ele."
        )
        if row["availability"] < ctx.target:
            status += " Disponibilidade abaixo da meta."

    art, head = st.columns([1, 4], gap="medium", vertical_alignment="center")
    with art:
        hero_turbine(period, light)
    with head:
        st.markdown(
            f'<div class="turbine-title">{row["turbine_code"]}</div>'
            f'<div class="turbine-meta">{row["company_name"]}, {row["farm_name"]}. '
            f"{number(row['rated_power_mw'])} MW, em operação desde {pd.Timestamp(info['commissioned_at']).year}. "
            f"Posição {ids.index(turbine_id) + 1} de {len(ids)} no ranking de criticidade.</div>"
            f'<div class="status-line"><span class="dot" style="background:{light}"></span>{escape(status)}</div>',
            unsafe_allow_html=True,
        )

    def versus(value, fleet_value, fmt, higher_is_better=False) -> tuple[str, str]:
        if value is None or fleet_value is None or pd.isna(fleet_value):
            return "", ""
        tone = "good" if (value > fleet_value) == higher_is_better else "bad"
        if abs(value - fleet_value) < 1e-9:
            tone = ""
        return f"média da frota: {fmt(fleet_value)}", tone

    mttr = None if pd.isna(row["mttr_hours"]) else row["mttr_hours"]
    cells = [
        Cell(
            "Disponibilidade",
            pct(row["availability"]),
            *versus(row["availability"], fleet["availability"].mean(), pct, True),
        ),
        Cell(
            "Falhas",
            number(row["failure_count"], 0),
            *versus(row["failure_count"], fleet["failure_count"].mean(), lambda v: number(v, 1)),
        ),
        Cell("Tempo médio de reparo", hours(mttr), *versus(mttr, fleet["mttr_hours"].mean(), hours)),
        Cell(
            "Horas paradas",
            hours(row["downtime_hours"]),
            *versus(row["downtime_hours"], fleet["downtime_hours"].mean(), hours),
        ),
        Cell(
            "Impacto estimado",
            brl_compact(row["loss_brl"]),
            *versus(row["loss_brl"], fleet["loss_brl"].mean(), brl_compact),
        ),
    ]
    strip(cells)

    st.subheader(f"Turbinas do {row['farm_name']} ({row['company_name']})")
    siblings = ctx.reports[ctx.reports["farm_id"] == row["farm_id"]].sort_values("turbine_code")
    farm_row(siblings.to_dict("records"), turbine_id, ctx.target, rotor_period_from_wind(row["mean_wind_ms"]))
    st.markdown(
        '<p class="note">Aqui a velocidade de cada rotor acompanha a disponibilidade: quanto mais tempo parada '
        "no período, mais devagar ela gira. Luz verde: operando. Âmbar: abaixo da meta. "
        "Vermelha e rotor parado: falha em aberto no fim do período.</p>",
        unsafe_allow_html=True,
    )

    if not failures.empty:
        failures["cause_pt"] = failures["cause"].map(CAUSE_PT)
        failures["duration_label"] = failures["duration_hours"].map(lambda h: "em aberto" if pd.isna(h) else hours(h))

    st.subheader("Linha do tempo das paradas")
    if failures.empty and maintenances.empty:
        _empty("Sem falhas ou manutenções no período.")
    else:
        plot(charts.turbine_timeline(failures, maintenances, ctx.start, ctx.end))

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Energia não gerada por mês")
        plot(charts.turbine_monthly(row["loss_by_month_mwh"], ctx.start, ctx.end))
    with right:
        st.subheader("Por que ela é crítica")
        breakdown = row["criticality_breakdown"]
        total = sum(breakdown.values())
        if total == 0:
            st.caption("Nenhuma falha no período: criticidade zero.")
        else:
            parts = sorted(breakdown.items(), key=lambda item: -item[1])
            rows_html = "".join(
                f'<div class="factor"><div class="factor-head"><span>{SIGNAL_PT[sig]}</span>'
                f"<span>{number(pts)} de {SIGNAL_MAX[sig]} pts</span></div>"
                f'<div class="track"><div class="fill" style="width:{pts / SIGNAL_MAX[sig] * 100:.1f}%;'
                f'background:{SIGNAL_COLORS[sig]}"></div></div></div>'
                for sig, pts in parts
            )
            st.markdown(rows_html, unsafe_allow_html=True)
            main = SIGNAL_PT[parts[0][0]].lower()
            st.markdown(
                f'<p class="note">Maior peso: {main}, com {number(parts[0][1] / total * 100, 0)}% dos '
                f"{number(total)} pontos. Cada barra mostra quanto do máximo daquele fator a turbina atingiu.</p>",
                unsafe_allow_html=True,
            )

    st.subheader("Histórico")
    tab_f, tab_m = st.tabs([f"Falhas ({len(failures)})", f"Manutenções ({len(maintenances)})"])
    with tab_f:
        if failures.empty:
            _empty("Nenhuma falha no período.")
        else:
            st.dataframe(_failure_table(failures, ctx), hide_index=True, width="stretch", column_config=FAILURE_COLUMNS)
    with tab_m:
        if maintenances.empty:
            _empty("Nenhuma manutenção no período.")
        else:
            st.dataframe(
                _maintenance_table(maintenances, ctx),
                hide_index=True,
                width="stretch",
                column_config=MAINTENANCE_COLUMNS,
            )


def _failure_table(failures: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    table = pd.DataFrame(
        {
            "Falha": failures["id"],
            "Turbina": failures["turbine_id"].map(ctx.turbine_labels),
            "Componente": failures["component"].map(COMPONENT_PT),
            "Causa": failures["cause"].map(CAUSE_PT),
            "Início": pd.to_datetime(failures["started_at"]),
            "Fim": pd.to_datetime(failures["ended_at"]).map(
                lambda ts: "em aberto" if pd.isna(ts) else f"{ts:%d/%m/%Y %H:%M}"
            ),
            "Duração (h)": pd.to_numeric(failures["duration_hours"]),
            "Situação": failures["ended_at"].isna().map({True: "Aberta", False: "Encerrada"}),
        }
    )
    return table


def _maintenance_table(maintenances: pd.DataFrame, ctx: Context) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Nº": maintenances["id"],
            "Turbina": maintenances["turbine_id"].map(ctx.turbine_labels),
            "Tipo": maintenances["type"].map({"Preventive": "Preventiva", "Corrective": "Corretiva"}),
            "Início": pd.to_datetime(maintenances["started_at"]),
            "Fim": pd.to_datetime(maintenances["ended_at"]),
            "Técnico": maintenances["technician"],
            "Peças": maintenances["parts_used"].apply(", ".join),
            "Falha": maintenances["failure_id"].map(lambda f: "—" if pd.isna(f) else f"#{int(f)}"),
        }
    )


# ---------- failures ----------
def failures(ctx: Context) -> None:
    data = _failures(ctx)
    open_now = pd.DataFrame(client.get("/failures", {"company_id": ctx.company_id, "state": "open"}))

    st.subheader("Quando e onde as falhas acontecem")
    if data.empty:
        _empty("Nenhuma falha no período.")
    else:
        plot(charts.failure_heatmap(data, ctx.start, ctx.end))
        st.markdown(
            '<p class="note">Cada quadrado é um mês; quanto mais escuro, mais falhas.</p>', unsafe_allow_html=True
        )

    st.subheader("Registro de falhas")
    col_a, col_b = st.columns([1, 2])
    state = col_a.segmented_control("Situação", ["Todas", "Abertas", "Encerradas"], default="Todas")
    components = col_b.multiselect(
        "Componentes", list(COMPONENT_PT), format_func=COMPONENT_PT.get, placeholder="Todos os componentes"
    )
    if not data.empty:
        view = data
        if state == "Abertas":
            view = view[view["ended_at"].isna()]
        elif state == "Encerradas":
            view = view[view["ended_at"].notna()]
        if components:
            view = view[view["component"].isin(components)]
        table = _failure_table(view, ctx)
        st.dataframe(
            table,
            hide_index=True,
            width="stretch",
            column_config=FAILURE_COLUMNS,
        )
        st.download_button("Baixar CSV", table.to_csv(index=False).encode("utf-8"), "windops_falhas.csv", "text/csv")

    left, right = st.columns(2, gap="large")
    with left, st.expander("Registrar falha", icon=":material/add_alert:"):
        _new_failure_form(ctx)
    with right, st.expander(f"Encerrar falha aberta ({len(open_now)})", icon=":material/task_alt:"):
        _close_failure_form(ctx, open_now)


def _new_failure_form(ctx: Context) -> None:
    with st.form("new_failure", clear_on_submit=True):
        turbine_id = st.selectbox("Turbina", list(ctx.turbine_labels), format_func=ctx.turbine_labels.get)
        c1, c2 = st.columns(2)
        component = c1.selectbox("Componente", [c.value for c in Component], format_func=COMPONENT_PT.get)
        cause = c2.selectbox("Causa", [c.value for c in FailureCause], format_func=CAUSE_PT.get)
        c3, c4 = st.columns(2)
        day = c3.date_input("Início", value=ctx.end.date() - timedelta(days=1), format="DD/MM/YYYY")
        at = c4.time_input("Hora", value=time(8, 0))
        description = st.text_input("Descrição", placeholder="Opcional")
        if st.form_submit_button("Registrar falha", type="primary"):
            ok, body = client.send(
                "POST",
                "/failures",
                {
                    "turbine_id": turbine_id,
                    "component": component,
                    "cause": cause,
                    "started_at": datetime.combine(day, at).isoformat(),
                    "description": description,
                },
            )
            if ok:
                st.success(f"Falha #{body['id']} registrada como aberta.")
            else:
                st.error(f"Não foi possível registrar: {body}")


def _close_failure_form(ctx: Context, open_now: pd.DataFrame) -> None:
    if open_now.empty:
        st.caption("Nenhuma falha aberta.")
        return
    labels = {
        row["id"]: f"#{row['id']} · {ctx.turbine_labels.get(row['turbine_id'], row['turbine_id'])} · "
        f"{COMPONENT_PT[row['component']]} desde {pd.Timestamp(row['started_at']):%d/%m %H:%M}"
        for _, row in open_now.iterrows()
    }
    with st.form("close_failure"):
        failure_id = st.selectbox("Falha", list(labels), format_func=labels.get)
        c1, c2 = st.columns(2)
        day = c1.date_input("Fim", value=ctx.end.date() - timedelta(days=1), format="DD/MM/YYYY")
        at = c2.time_input("Hora do fim", value=time(18, 0))
        if st.form_submit_button("Encerrar falha", type="primary"):
            ok, body = client.send(
                "PATCH", f"/failures/{failure_id}/close", {"ended_at": datetime.combine(day, at).isoformat()}
            )
            if ok:
                st.success(f"Falha #{failure_id} encerrada após {hours(body['duration_hours'])}.")
            else:
                st.error(f"Não foi possível encerrar: {body}")


# ---------- maintenance ----------
def maintenance(ctx: Context) -> None:
    data = _maintenances(ctx)
    if data.empty:
        _empty("Nenhuma manutenção no período.")
        return
    counts = data["type"].value_counts()
    durations = (pd.to_datetime(data["ended_at"]) - pd.to_datetime(data["started_at"])).dt.total_seconds() / 3600
    preventive_share = counts.get("Preventive", 0) / len(data)
    strip(
        [
            Cell("Preventivas", number(counts.get("Preventive", 0), 0)),
            Cell("Corretivas", number(counts.get("Corrective", 0), 0)),
            Cell("Parcela preventiva", pct(preventive_share, 0), "quanto maior, mais a equipe se antecipa às falhas"),
            Cell("Horas de equipe em campo", hours(durations.sum())),
        ]
    )
    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Preventivas e corretivas por mês")
        plot(charts.maintenance_mix(data, ctx.start, ctx.end))
    with right:
        st.subheader("Carga por técnico")
        plot(charts.technician_load(data))

    st.subheader("Registro de manutenções")
    table = _maintenance_table(data, ctx)
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        column_config=MAINTENANCE_COLUMNS,
    )
    st.download_button("Baixar CSV", table.to_csv(index=False).encode("utf-8"), "windops_manutencoes.csv", "text/csv")


# ---------- prioritisation ----------
def priority(ctx: Context) -> None:
    if ctx.reports.empty:
        _empty("Nenhuma turbina para os filtros escolhidos.")
        return
    st.subheader("Ordem de atenção")
    st.markdown(
        '<p class="note">Cada barra soma até 100 pontos: impacto financeiro vale até 40, número de falhas 25, '
        "horas paradas 20 e tempo de reparo 15. A comparação é entre as turbinas filtradas.</p>",
        unsafe_allow_html=True,
    )
    plot(charts.criticality_bars(ctx.reports))

    st.subheader("Frequência contra tempo de reparo")
    st.markdown(
        '<p class="note">Bolha maior = mais R$ perdido. No quadrante de cima à direita ficam as turbinas que falham '
        "muito e demoram a voltar.</p>",
        unsafe_allow_html=True,
    )
    plot(charts.risk_scatter(ctx.reports))

    table = pd.DataFrame(
        {
            "Turbina": ctx.reports["turbine_id"].map(ctx.turbine_labels),
            "Criticidade": ctx.reports["criticality"],
            "Impacto (R$)": ctx.reports["loss_brl"],
            "Energia (MWh)": ctx.reports["energy_loss_mwh"],
            "Falhas": ctx.reports["failure_count"],
            "Horas paradas": ctx.reports["downtime_hours"],
            "MTTR (h)": pd.to_numeric(ctx.reports["mttr_hours"]),
            "MTBF (h)": pd.to_numeric(ctx.reports["mtbf_hours"]),
            "Disponibilidade": ctx.reports["availability"] * 100,
        }
    )
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        height=(len(table) + 1) * 35 + 3,
        column_config={
            "Criticidade": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
            "Impacto (R$)": st.column_config.NumberColumn(format="R$ %.0f"),
            "Energia (MWh)": st.column_config.NumberColumn(format="%.1f"),
            "Horas paradas": st.column_config.NumberColumn(format="%.0f"),
            "MTTR (h)": st.column_config.NumberColumn(format="%.0f"),
            "MTBF (h)": st.column_config.NumberColumn(format="%.0f"),
            "Disponibilidade": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
    st.download_button("Baixar CSV", table.to_csv(index=False).encode("utf-8"), "windops_priorizacao.csv", "text/csv")


# ---------- alerts ----------
def alerts(ctx: Context) -> None:
    if not ctx.alerts:
        st.success("Nenhum alerta para os filtros escolhidos.")
        return
    kinds = {
        "open_failure": "Falhas abertas",
        "low_availability": "Disponibilidade baixa",
        "slow_repair": "Reparos lentos",
        "recurrence": "Falhas recorrentes",
    }
    present = [k for k in kinds if any(a["kind"] == k for a in ctx.alerts)]
    chosen = st.pills(
        "Tipo de alerta",
        present,
        selection_mode="multi",
        default=present,
        format_func=lambda k: f"{kinds[k]} ({sum(1 for a in ctx.alerts if a['kind'] == k)})",
    )
    visible = [a for a in ctx.alerts if a["kind"] in chosen]
    alert_rows(visible)
    st.caption(
        f"Regras: falha aberta vira crítica após 72 h; disponibilidade abaixo de {pct(ctx.target, 0)} gera atenção "
        f"e abaixo de {pct(ctx.target - 0.02, 0)} é crítica; reparo lento é MTTR acima de 1,5× a média da frota; "
        "recorrência é o mesmo componente falhando 3 vezes em 90 dias."
    )
