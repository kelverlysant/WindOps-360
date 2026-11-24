"""Visual identity: palette, CSS, Plotly template and number formatting.

Direction "sky and nacelle": cool ice-blue background, white surfaces,
petrol-blue ink and a wind-blue primary. Losses and critical states use
the red of the obstruction lights on top of the towers; warnings use amber.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

SKY = "#EEF3F6"
SURFACE = "#FFFFFF"
INK = "#14303F"
MUTED = "#5B7383"
LINE = "#D5E0E6"
WIND = "#0E7C9A"
WIND_SOFT = "#7FB3C6"
SIGNAL = "#C8362B"
AMBER = "#D99A1E"
GOOD = "#2F8F5B"

COMPANY_COLORS = [WIND, INK, AMBER, WIND_SOFT]
COMPONENT_COLORS = {
    "Generator": "#14303F",
    "Gearbox": "#0E7C9A",
    "Electrical": "#D99A1E",
    "Sensor": "#7FB3C6",
    "Blade": "#9C6B98",
}
COMPONENT_PT = {
    "Generator": "Gerador",
    "Gearbox": "Caixa multiplicadora",
    "Electrical": "Elétrico",
    "Sensor": "Sensor",
    "Blade": "Pá",
}
CAUSE_PT = {
    "Wear": "Desgaste",
    "Weather": "Clima",
    "Electrical Fault": "Falha elétrica",
    "Manufacturing Defect": "Defeito de fabricação",
    "Operational Error": "Erro operacional",
}
SIGNAL_PT = {
    "loss_brl": "Impacto financeiro",
    "failure_count": "Nº de falhas",
    "downtime_hours": "Horas paradas",
    "mttr_hours": "Tempo de reparo",
}
SIGNAL_MAX = {"loss_brl": 40, "failure_count": 25, "downtime_hours": 20, "mttr_hours": 15}
MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def month_label(ts, with_year: bool = True) -> str:
    return f"{MONTHS_PT[ts.month - 1]}/{ts.year % 100:02d}" if with_year else MONTHS_PT[ts.month - 1]


SIGNAL_COLORS = {"loss_brl": SIGNAL, "failure_count": INK, "downtime_hours": WIND, "mttr_hours": AMBER}

HEADING_FONT = "Barlow Semi Condensed, Barlow, system-ui, sans-serif"
BODY_FONT = "Barlow, system-ui, sans-serif"


# ---------- number formatting (pt-BR) ----------
def number(value: float, decimals: int = 1) -> str:
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def brl(value: float) -> str:
    return f"R$ {number(value, 2)}"


def brl_compact(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"R$ {number(value / 1_000_000, 2)} mi"
    if abs(value) >= 1_000:
        return f"R$ {number(value / 1_000, 0)} mil"
    return brl(value)


def pct(value: float | None, decimals: int = 2) -> str:
    return "—" if value is None else f"{number(value * 100, decimals)}%"


def hours(value: float | None) -> str:
    return "—" if value is None else f"{number(value, 0)} h"


# ---------- plotly ----------
def _register_template() -> None:
    template = go.layout.Template()
    template.layout = go.Layout(
        font={"family": BODY_FONT, "color": INK, "size": 13},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=COMPANY_COLORS,
        margin={"l": 8, "r": 8, "t": 8, "b": 8},
        xaxis={"gridcolor": LINE, "linecolor": LINE, "zeroline": False, "tickfont": {"color": MUTED}},
        yaxis={"gridcolor": LINE, "linecolor": LINE, "zeroline": False, "tickfont": {"color": MUTED}},
        legend={"orientation": "h", "y": -0.18, "x": 0, "font": {"color": MUTED}},
        hoverlabel={"font": {"family": BODY_FONT}, "bgcolor": SURFACE, "bordercolor": LINE},
        separators=",.",
    )
    pio.templates["windops"] = template
    pio.templates.default = "windops"


_register_template()


# ---------- CSS ----------
_CSS = f"""
<style>
.block-container {{ padding-top: 2.2rem; max-width: 1320px; }}
h1, h2, h3 {{ letter-spacing: -0.01em; }}
h3 {{ font-size: 1.35rem !important; margin-top: 1.2rem; }}
[data-testid="stSidebar"] {{ border-right: 1px solid {LINE}; }}
[data-testid="stCaptionContainer"], .muted {{ color: {MUTED}; }}
.stTabs [data-baseweb="tab"] {{ font-family: {HEADING_FONT}; font-size: 1.05rem; font-weight: 500; }}

/* Briefing: the opening sentence is the hero */
[data-testid="stMarkdownContainer"] p.briefing {{
  font-family: {HEADING_FONT}; font-weight: 500; color: {INK};
  font-size: clamp(1.6rem, 2.6vw, 2.35rem); line-height: 1.18;
  max-width: 34ch; margin: 0.2rem 0 0.6rem 0;
  font-variant-numeric: tabular-nums;
}}
[data-testid="stMarkdownContainer"] p.briefing-sub {{
  color: {MUTED}; font-size: 1.05rem; max-width: 70ch; margin-bottom: 1.4rem;
}}
p.briefing-sub strong {{ color: {INK}; font-weight: 600; }}

/* Instrument strip: one panel, cells split by rules */
.strip {{
  display: grid; grid-template-columns: repeat(var(--cells), minmax(0, 1fr));
  background: {SURFACE}; border: 1px solid {LINE}; border-radius: 6px; margin: 0.4rem 0 1.6rem 0;
}}
.strip .cell {{ padding: 0.9rem 1.1rem 1rem; border-left: 1px solid {LINE}; min-width: 0; }}
.strip .cell:first-child {{ border-left: none; }}
.strip .label {{ color: {MUTED}; font-size: 0.9rem; }}
.strip .value {{
  font-family: {HEADING_FONT}; font-weight: 600; font-size: 2rem; line-height: 1.15;
  font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.strip .delta {{ font-size: 0.85rem; color: {MUTED}; font-variant-numeric: tabular-nums; }}
.strip .delta.good {{ color: {GOOD}; }}
.strip .delta.bad {{ color: {SIGNAL}; }}
@media (max-width: 900px) {{
  .strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .strip .cell {{ border-left: none; border-top: 1px solid {LINE}; }}
}}

/* Alerts: the left rule encodes severity */
.alert-row {{
  background: {SURFACE}; border: 1px solid {LINE}; border-left: 4px solid {AMBER};
  border-radius: 6px; padding: 0.75rem 1rem; margin-bottom: 0.55rem;
}}
.alert-row.critical {{ border-left-color: {SIGNAL}; }}
.alert-row .title {{ font-weight: 600; font-size: 1.02rem; }}
.alert-row .who {{ color: {MUTED}; font-size: 0.92rem; }}
.alert-row .detail {{ font-size: 0.95rem; margin-top: 0.2rem; }}
.sev {{ font-size: 0.8rem; font-weight: 600; margin-right: 0.45rem; }}
.sev.critical {{ color: {SIGNAL}; }}
.sev.warning {{ color: #9A6A0C; }}

/* Criticality factors in the drill-down */
.factor {{ margin-bottom: 0.85rem; }}
.factor-head {{ display: flex; justify-content: space-between; font-size: 0.98rem; margin-bottom: 0.25rem; }}
.factor-head span:last-child {{ color: {MUTED}; font-variant-numeric: tabular-nums; }}
.track {{ height: 10px; background: {SURFACE}; border: 1px solid {LINE}; border-radius: 5px; overflow: hidden; }}
.track .fill {{ height: 100%; }}

/* Animated turbines: the rotation lives inside each SVG image */
.hero-turbine {{ display: flex; justify-content: center; }}
.farm-row {{ display: flex; flex-wrap: wrap; gap: 0.5rem 1.6rem; align-items: flex-end; margin: 0.2rem 0 1rem; }}
.farm-cell {{ text-align: center; padding: 0.4rem 0.6rem 0.5rem; border-radius: 6px; min-width: 110px; }}
.farm-cell.selected {{ background: {SURFACE}; border: 1px solid {LINE}; }}
.farm-cell .code {{ font-family: {HEADING_FONT}; font-weight: 600; font-size: 1.15rem; margin-top: 0.2rem; }}
.farm-cell .avail {{ font-variant-numeric: tabular-nums; }}
.farm-cell .status {{ font-size: 0.85rem; font-weight: 600; }}
.status-line {{ font-size: 1rem; margin: -0.4rem 0 1rem; }}
.status-line .dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 0.4rem; }}

/* Turbine heading in the drill-down */
.turbine-title {{ font-family: {HEADING_FONT}; font-weight: 700; font-size: 3rem; line-height: 1; color: {INK}; }}
.turbine-meta {{ color: {MUTED}; font-size: 1.02rem; margin: 0.35rem 0 1rem; }}
[data-testid="stMarkdownContainer"] p.note {{
  color: {MUTED}; font-size: 0.92rem; margin-top: -0.4rem;
}}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
