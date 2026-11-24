"""Plotly figure builders. They only draw: every number comes from the API."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.colors import sample_colorscale

from windops.dashboard.theme import (
    COMPANY_COLORS,
    COMPONENT_COLORS,
    COMPONENT_PT,
    INK,
    LINE,
    MUTED,
    SIGNAL,
    SIGNAL_COLORS,
    SIGNAL_PT,
    SKY,
    WIND,
    WIND_SOFT,
    brl,
    month_label,
    number,
)

WINDY_MONTHS = (8, 10)  # August to October
CRITICALITY_SCALE = [[0, "#DCEAF0"], [0.5, WIND_SOFT], [1, SIGNAL]]


def _alpha(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def _months(start: datetime, end: datetime) -> pd.DatetimeIndex:
    return pd.date_range(pd.Timestamp(start).to_period("M").start_time, end, freq="MS", inclusive="left")


def _pt_month_axis(fig: go.Figure, months: pd.DatetimeIndex, axis: str = "x") -> None:
    """Portuguese month ticks (Plotly only ships English month names)."""
    step = 1 if len(months) <= 12 else 2 if len(months) <= 24 else 3
    ticks = months[::step]
    text = [
        f"{month_label(m, False)}<br>{m.year}" if i == 0 or m.month <= step else month_label(m, False)
        for i, m in enumerate(ticks)
    ]
    fig.update_layout(**{f"{axis}axis": {"tickvals": list(ticks), "ticktext": text}})


def _windy_season(fig: go.Figure, start: datetime, end: datetime, label: bool = True) -> None:
    """Shade the windy season: the same stop costs more there."""
    for year in range(start.year, end.year + 1):
        band_start = max(pd.Timestamp(year, WINDY_MONTHS[0], 1), pd.Timestamp(start))
        band_end = min(pd.Timestamp(year, WINDY_MONTHS[1] + 1, 1), pd.Timestamp(end))
        if band_end <= band_start:
            continue
        fig.add_vrect(
            x0=band_start - pd.Timedelta(days=15),
            x1=band_end - pd.Timedelta(days=15),
            fillcolor=WIND,
            opacity=0.07,
            line_width=0,
            layer="below",
        )
        if label:
            fig.add_annotation(
                x=band_start - pd.Timedelta(days=12),
                y=1,
                yref="paper",
                xanchor="left",
                yanchor="bottom",
                text="temporada de ventos fortes",
                showarrow=False,
                font={"color": MUTED, "size": 11},
            )


def monthly_loss(monthly: pd.DataFrame, start: datetime, end: datetime) -> go.Figure:
    """Stacked area of lost energy per company, with R$ in the tooltip."""
    months = _months(start, end)
    fig = go.Figure()
    companies = sorted(monthly["company_name"].unique()) if not monthly.empty else []
    for index, company in enumerate(companies):
        rows = monthly[monthly["company_name"] == company].copy()
        rows["date"] = pd.to_datetime(rows["month"] + "-01")
        rows = rows.set_index("date")[["energy_loss_mwh", "loss_brl"]].reindex(months, fill_value=0.0)
        color = COMPANY_COLORS[index % len(COMPANY_COLORS)]
        fig.add_trace(
            go.Scatter(
                x=rows.index,
                y=rows["energy_loss_mwh"],
                name=company,
                stackgroup="loss",
                mode="lines",
                line={"width": 1.6, "color": color},
                fillcolor=_alpha(color, 0.30 if index == 0 else 0.45),
                customdata=list(zip([month_label(m) for m in rows.index], rows["loss_brl"].map(brl), strict=True)),
                hovertemplate=(
                    f"<b>{company}</b> %{{customdata[0]}}<br>%{{y:,.1f}} MWh, %{{customdata[1]}}<extra></extra>"
                ),
            )
        )
    _windy_season(fig, start, end)
    fig.update_layout(height=330, hovermode="closest", yaxis_title="MWh não gerados", margin={"t": 26})
    _pt_month_axis(fig, months)
    return fig


def availability_by_farm(farms: pd.DataFrame, target: float) -> go.Figure:
    data = farms.sort_values("availability")
    colors = [SIGNAL if a < target else WIND for a in data["availability"]]
    labels = data["farm_name"] + " (" + data["company_name"] + ")"
    fig = go.Figure(
        go.Bar(
            x=data["availability"] * 100,
            y=labels,
            orientation="h",
            marker_color=colors,
            text=[f"{number(a * 100, 2)}%" for a in data["availability"]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>%{x:.2f}%<extra></extra>",
        )
    )
    low = min(float(data["availability"].min()) * 100, target * 100) - 1.5
    fig.add_vline(x=target * 100, line={"color": INK, "dash": "dot", "width": 1})
    fig.add_annotation(
        x=target * 100,
        y=1.06,
        yref="paper",
        text=f"meta {number(target * 100, 0)}%",
        showarrow=False,
        font={"color": INK, "size": 12},
    )
    fig.update_layout(height=60 + 46 * len(data), xaxis={"range": [low, 100.4], "ticksuffix": "%"}, bargap=0.35)
    return fig


def loss_tree(reports: pd.DataFrame) -> go.Figure:
    """Company > farm > turbine, sized by R$. Only turbines are coloured (by criticality)."""
    ids, labels, parents, values, colors, hover = [], [], [], [], [], []
    for company, c_rows in reports.groupby("company_name"):
        ids.append(company)
        labels.append(company)
        parents.append("")
        values.append(c_rows["loss_brl"].sum())
        colors.append(SKY)
        hover.append(brl(c_rows["loss_brl"].sum()))
        for farm, f_rows in c_rows.groupby("farm_name"):
            farm_id = f"{company}/{farm}"
            ids.append(farm_id)
            labels.append(farm)
            parents.append(company)
            values.append(f_rows["loss_brl"].sum())
            colors.append("#E3ECF1")
            hover.append(brl(f_rows["loss_brl"].sum()))
            for _, row in f_rows.iterrows():
                ids.append(f"{farm_id}/{row['turbine_code']}")
                labels.append(row["turbine_code"])
                parents.append(farm_id)
                values.append(row["loss_brl"])
                colors.append(sample_colorscale(CRITICALITY_SCALE, [row["criticality"] / 100])[0])
                hover.append(f"{brl(row['loss_brl'])}<br>criticidade {number(row['criticality'])}")
    fig = go.Figure(
        go.Treemap(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            marker={"colors": colors, "line": {"color": "#FFFFFF", "width": 2}},
            root={"color": "rgba(0,0,0,0)"},
            tiling={"pad": 3},
            customdata=hover,
            hovertemplate="<b>%{label}</b><br>%{customdata}<extra></extra>",
            texttemplate="<b>%{label}</b><br>%{percentRoot:.0%}",
            textfont={"family": "Barlow Semi Condensed, Barlow, sans-serif", "size": 15, "color": INK},
            pathbar={"visible": False},
        )
    )
    fig.update_layout(height=340, margin={"l": 0, "r": 0, "t": 0, "b": 0})
    return fig


def component_pareto(failures: pd.DataFrame) -> go.Figure:
    """Repair hours per component with the cumulative share."""
    closed = failures.dropna(subset=["duration_hours"])
    totals = closed.groupby("component")["duration_hours"].sum().sort_values(ascending=False)
    cumulative = totals.cumsum() / totals.sum() * 100
    names = [COMPONENT_PT.get(c, c) for c in totals.index]
    fig = go.Figure()
    fig.add_bar(
        x=names,
        y=totals.values,
        marker_color=[COMPONENT_COLORS.get(c, WIND) for c in totals.index],
        name="Horas de reparo",
        hovertemplate="%{x}<br>%{y:,.0f} h<extra></extra>",
    )
    fig.add_scatter(
        x=names,
        y=cumulative.values,
        yaxis="y2",
        mode="lines+markers",
        name="% acumulado",
        line={"color": INK, "width": 1.5},
        marker={"size": 6},
        hovertemplate="%{x}<br>%{y:.0f}% acumulado<extra></extra>",
    )
    fig.update_layout(
        height=320,
        yaxis={"title": "horas de reparo"},
        yaxis2={
            "overlaying": "y",
            "side": "right",
            "range": [0, 105],
            "ticksuffix": "%",
            "showgrid": False,
            "tickvals": [0, 25, 50, 75, 100],
            "ticktext": ["0%", "25%", "50%", "75%", "100%"],
        },
        showlegend=False,
        bargap=0.35,
    )
    return fig


def failure_heatmap(failures: pd.DataFrame, start: datetime, end: datetime) -> go.Figure:
    data = failures.copy()
    data["month"] = pd.to_datetime(data["started_at"]).dt.to_period("M").dt.to_timestamp()
    months = _months(start, end)
    grid = data.pivot_table(index="component", columns="month", values="id", aggfunc="count", fill_value=0)
    grid = grid.reindex(columns=months, fill_value=0).reindex(list(COMPONENT_PT), fill_value=0)
    fig = go.Figure(
        go.Heatmap(
            z=grid.values,
            x=grid.columns,
            y=[COMPONENT_PT[c] for c in grid.index],
            colorscale=[[0, "#FFFFFF"], [0.35, WIND_SOFT], [1, INK]],
            xgap=3,
            ygap=3,
            showscale=False,
            customdata=[[month_label(m) for m in grid.columns]] * len(grid.index),
            hovertemplate="%{y}, %{customdata}<br>%{z} falha(s)<extra></extra>",
        )
    )
    fig.update_layout(height=250)
    _pt_month_axis(fig, months)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)
    return fig


def criticality_bars(reports: pd.DataFrame) -> go.Figure:
    """Each turbine's score split into the four signals that make it up."""
    data = reports.sort_values("criticality")
    labels = data["turbine_code"] + " (" + data["company_name"] + ", " + data["farm_name"] + ")"
    fig = go.Figure()
    for signal, title in SIGNAL_PT.items():
        values = data["criticality_breakdown"].map(lambda b, s=signal: b.get(s, 0))
        fig.add_bar(
            y=labels,
            x=values,
            orientation="h",
            name=title,
            marker_color=SIGNAL_COLORS[signal],
            hovertemplate=f"%{{y}}<br>{title}: %{{x:.1f}} pts<extra></extra>",
        )
    fig.add_scatter(
        y=labels,
        x=data["criticality"],
        mode="text",
        text=[number(v) for v in data["criticality"]],
        textposition="middle right",
        textfont={"family": "Barlow Semi Condensed", "size": 14, "color": INK},
        showlegend=False,
        hoverinfo="skip",
    )
    fig.update_layout(
        barmode="stack",
        height=70 + 34 * len(data),
        bargap=0.3,
        xaxis={"range": [0, 108], "title": "pontos de criticidade (0 a 100)"},
        legend={"y": 1.02, "yanchor": "bottom", "traceorder": "normal"},
    )
    return fig


def risk_scatter(reports: pd.DataFrame) -> go.Figure:
    """Frequency vs repair time, bubble = R$ lost."""
    data = reports.copy()
    data["mttr"] = data["mttr_hours"].fillna(0)
    top = set(data.nlargest(5, "criticality")["turbine_id"])
    data["label"] = [
        code if tid in top else "" for code, tid in zip(data["turbine_code"], data["turbine_id"], strict=True)
    ]
    size_ref = max(data["loss_brl"].max(), 1) / 46**2
    fig = go.Figure(
        go.Scatter(
            x=data["failure_count"],
            y=data["mttr"],
            mode="markers+text",
            text=data["label"],
            textposition="middle right",
            textfont={"size": 12, "color": INK},
            hovertext=data["turbine_code"],
            marker={
                "size": data["loss_brl"],
                "sizemode": "area",
                "sizeref": size_ref,
                "sizemin": 5,
                "color": data["criticality"],
                "colorscale": CRITICALITY_SCALE,
                "cmin": 0,
                "cmax": 100,
                "line": {"color": INK, "width": 0.6},
                "opacity": 0.85,
            },
            customdata=data[["company_name", "farm_name", "loss_brl"]].assign(loss=data["loss_brl"].map(brl)),
            hovertemplate=(
                "<b>%{hovertext}</b> (%{customdata[0]}, %{customdata[1]})<br>"
                "%{x} falhas · MTTR %{y:.0f} h<br>%{customdata[3]}<extra></extra>"
            ),
        )
    )
    fig.add_hline(y=data["mttr"].mean(), line={"color": LINE, "dash": "dot"})
    fig.add_vline(x=data["failure_count"].mean(), line={"color": LINE, "dash": "dot"})
    fig.update_layout(height=380, xaxis_title="falhas no período", yaxis_title="tempo médio de reparo (h)")
    return fig


def turbine_timeline(failures: pd.DataFrame, maintenances: pd.DataFrame, start: datetime, end: datetime) -> go.Figure:
    """Every stop of one turbine on a single time axis."""
    fig = go.Figure()
    if not failures.empty:
        for component, rows in failures.groupby("component"):
            ends = rows["ended_at"].fillna(end.isoformat())
            starts = pd.to_datetime(rows["started_at"])
            durations = (pd.to_datetime(ends) - starts).dt.total_seconds() * 1000
            fig.add_bar(
                base=starts,
                x=durations,
                y=[COMPONENT_PT[component]] * len(rows),
                orientation="h",
                marker_color=COMPONENT_COLORS[component],
                name=COMPONENT_PT[component],
                customdata=rows[["id", "cause_pt", "duration_label"]],
                hovertemplate=(
                    "Falha #%{customdata[0]}<br>%{base|%d/%m/%Y %H:%M}<br>"
                    "%{customdata[1]} · %{customdata[2]}<extra></extra>"
                ),
                width=0.55,
            )
    preventive = maintenances[maintenances["type"] == "Preventive"] if not maintenances.empty else maintenances
    if not preventive.empty:
        fig.add_scatter(
            x=pd.to_datetime(preventive["started_at"]),
            y=["Preventiva"] * len(preventive),
            mode="markers",
            marker={"symbol": "diamond", "size": 11, "color": WIND},
            name="Preventiva",
            hovertemplate="Preventiva<br>%{x|%d/%m/%Y}<extra></extra>",
        )
    order = ["Preventiva"] + [COMPONENT_PT[c] for c in reversed(list(COMPONENT_PT))]
    _windy_season(fig, start, end, label=False)
    fig.update_layout(height=320, showlegend=False, barmode="overlay")
    fig.update_xaxes(type="date", range=[start, end])
    _pt_month_axis(fig, _months(start, end))
    fig.update_yaxes(categoryorder="array", categoryarray=order, showgrid=False)
    return fig


def turbine_monthly(loss_by_month: dict[str, float], start: datetime, end: datetime) -> go.Figure:
    months = _months(start, end)
    series = pd.Series({pd.Timestamp(k + "-01"): v for k, v in loss_by_month.items()}).reindex(months, fill_value=0)
    fig = go.Figure(
        go.Bar(
            x=series.index,
            y=series.values,
            marker_color=SIGNAL,
            customdata=[month_label(m) for m in series.index],
            hovertemplate="%{customdata}<br>%{y:,.1f} MWh<extra></extra>",
        )
    )
    _windy_season(fig, start, end, label=False)
    fig.update_layout(height=280, yaxis_title="MWh não gerados", bargap=0.25)
    _pt_month_axis(fig, months)
    return fig


def maintenance_mix(maintenances: pd.DataFrame, start: datetime, end: datetime) -> go.Figure:
    data = maintenances.copy()
    data["month"] = pd.to_datetime(data["started_at"]).dt.to_period("M").dt.to_timestamp()
    months = _months(start, end)
    grid = data.pivot_table(index="month", columns="type", values="id", aggfunc="count", fill_value=0)
    grid = grid.reindex(months, fill_value=0)
    fig = go.Figure()
    for kind, title, color in [("Corrective", "Corretivas", SIGNAL), ("Preventive", "Preventivas", WIND)]:
        if kind in grid:
            fig.add_bar(
                x=grid.index,
                y=grid[kind],
                name=title,
                marker_color=color,
                customdata=[month_label(m) for m in grid.index],
                hovertemplate=f"{title}, %{{customdata}}: %{{y}}<extra></extra>",
            )
    fig.update_layout(
        barmode="stack", height=300, bargap=0.25, legend={"y": 1.02, "yanchor": "bottom", "traceorder": "normal"}
    )
    _pt_month_axis(fig, months)
    return fig


def technician_load(maintenances: pd.DataFrame) -> go.Figure:
    data = maintenances.copy()
    data["hours"] = (pd.to_datetime(data["ended_at"]) - pd.to_datetime(data["started_at"])).dt.total_seconds() / 3600
    load = data.groupby(["technician", "type"])["hours"].sum().unstack(fill_value=0)
    load = load.assign(total=load.sum(axis=1)).sort_values("total")
    fig = go.Figure()
    for kind, title, color in [("Corrective", "Corretivas", SIGNAL), ("Preventive", "Preventivas", WIND)]:
        if kind in load:
            fig.add_bar(
                y=load.index,
                x=load[kind],
                orientation="h",
                name=title,
                marker_color=color,
                hovertemplate=f"%{{y}}<br>{title}: %{{x:,.0f}} h<extra></extra>",
            )
    fig.update_layout(
        barmode="stack",
        height=300,
        bargap=0.3,
        xaxis_title="horas em campo",
        legend={"y": 1.02, "yanchor": "bottom", "traceorder": "normal"},
    )
    return fig
