"""HTML building blocks: briefing sentence, instrument strip and alert rows."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape

import streamlit as st

from windops.dashboard.theme import brl_compact, hours, number, pct


@dataclass
class Cell:
    label: str
    value: str
    delta: str = ""
    tone: str = ""  # "good" | "bad" | ""


def period_phrase(start: datetime, end: datetime) -> str:
    last_day = end - timedelta(days=1)
    if start.month == 1 and start.day == 1 and end == start.replace(year=start.year + 1):
        return f"Em {start.year}"
    return f"Entre {start:%d/%m/%Y} e {last_day:%d/%m/%Y}"


def briefing(start: datetime, end: datetime, overview: dict, top: dict | None, alerts: list[dict]) -> None:
    if overview["failure_count"] == 0 and overview["energy_loss_mwh"] == 0:
        sentence = f"{period_phrase(start, end)}, nenhuma parada foi registrada nas turbinas selecionadas."
    else:
        sentence = (
            f"{period_phrase(start, end)}, as paradas custaram {brl_compact(overview['loss_brl'])} "
            f"em energia não gerada."
        )
        if top is not None:
            sentence += (
                f" Comece pela {top['turbine_code']} ({top['company_name']}, {top['farm_name']}): "
                f"{top['failure_count']} falhas e {hours(top['downtime_hours'])} parada."
            )
    critical = sum(1 for a in alerts if a["severity"] == "critical")
    warning = len(alerts) - critical
    if alerts:
        sub = (
            f"<strong>{critical} alerta{'s' if critical != 1 else ''} crítico{'s' if critical != 1 else ''}</strong> "
            f"e {warning} de atenção. Veja a aba Alertas para o que fazer agora."
        )
    else:
        sub = "Nenhum alerta para os filtros escolhidos."
    st.markdown(
        f'<p class="briefing">{escape(sentence)}</p><p class="briefing-sub">{sub}</p>',
        unsafe_allow_html=True,
    )


def strip(cells: list[Cell]) -> None:
    html = "".join(
        f'<div class="cell"><div class="label">{escape(c.label)}</div>'
        f'<div class="value" title="{escape(c.value)}">{escape(c.value)}</div>'
        f'<div class="delta {c.tone}">{escape(c.delta) or "&nbsp;"}</div></div>'
        for c in cells
    )
    st.markdown(f'<div class="strip" style="--cells:{len(cells)}">{html}</div>', unsafe_allow_html=True)


def _change(current: float, previous: float, higher_is_better: bool, fmt) -> tuple[str, str]:
    diff = current - previous
    if abs(diff) < 1e-9:
        return "igual ao período anterior", ""
    sign = "+" if diff > 0 else "−"
    tone = "good" if (diff > 0) == higher_is_better else "bad"
    return f"{sign}{fmt(abs(diff))} vs período anterior", tone


def _relative(current: float, previous: float, higher_is_better: bool) -> tuple[str, str]:
    if previous == 0:
        return "sem base no período anterior", ""
    change = (current - previous) / previous
    sign = "+" if change > 0 else "−"
    tone = "good" if (change > 0) == higher_is_better else "bad"
    return f"{sign}{number(abs(change) * 100, 0)}% vs período anterior", tone


def overview_cells(current: dict, previous: dict | None) -> list[Cell]:
    has_previous = previous is not None and (previous["failure_count"] > 0 or previous["energy_loss_mwh"] > 0)
    cells = [
        Cell("Disponibilidade da frota", pct(current["availability"])),
        Cell("Falhas iniciadas", number(current["failure_count"], 0)),
        Cell("Tempo médio de reparo", hours(current["mttr_hours"])),
        Cell("Energia não gerada", f"{number(current['energy_loss_mwh'], 0)} MWh"),
        Cell("Impacto estimado", brl_compact(current["loss_brl"])),
    ]
    if not has_previous:
        for cell in cells:
            cell.delta = "sem dados do período anterior"
        return cells

    cells[0].delta, cells[0].tone = _change(
        current["availability"] or 0, previous["availability"] or 0, True, lambda v: f"{number(v * 100, 2)} p.p."
    )
    cells[1].delta, cells[1].tone = _change(
        current["failure_count"], previous["failure_count"], False, lambda v: number(v, 0)
    )
    if current["mttr_hours"] is not None and previous["mttr_hours"] is not None:
        cells[2].delta, cells[2].tone = _change(
            current["mttr_hours"], previous["mttr_hours"], False, lambda v: f"{number(v, 0)} h"
        )
    cells[3].delta, cells[3].tone = _relative(current["energy_loss_mwh"], previous["energy_loss_mwh"], False)
    cells[4].delta, cells[4].tone = _relative(current["loss_brl"], previous["loss_brl"], False)
    return cells


SEVERITY_PT = {"critical": "Crítico", "warning": "Atenção"}


def alert_rows(alerts: list[dict]) -> None:
    html = "".join(
        f'<div class="alert-row {escape(a["severity"])}">'
        f'<div class="title"><span class="sev {escape(a["severity"])}">{SEVERITY_PT[a["severity"]]}</span>'
        f"{escape(a['title'])}</div>"
        f'<div class="who">{escape(a["turbine_label"])}</div>'
        f'<div class="detail">{escape(a["detail"])}</div></div>'
        for a in alerts
    )
    st.markdown(html, unsafe_allow_html=True)


# ---------- animated turbines ----------
# Presentation mapping only: how fast the drawing spins. The data (wind, availability,
# open failures) comes from the API.
SECONDS_PER_TURN_AT_8MS = 2.5
MIN_PERIOD_S, MAX_PERIOD_S = 0.9, 9.0


def rotor_period_from_wind(mean_wind_ms: float, cut_in_ms: float = 3.0) -> float | None:
    """Seconds per turn, proportional to wind. None = rotor still (below cut-in)."""
    if mean_wind_ms < cut_in_ms:
        return None
    period = SECONDS_PER_TURN_AT_8MS * 8.0 / mean_wind_ms
    return max(MIN_PERIOD_S, min(MAX_PERIOD_S, period))


def availability_factor(availability: float, target: float) -> float:
    """1.0 at 100% availability, down to 0.15 at 5 p.p. below the target."""
    floor = target - 0.05
    return max(0.15, min(1.0, (availability - floor) / (1.0 - floor)))


def turbine_svg(period_s: float | None, light: str, width: int, highlighted: bool = False) -> str:
    """A three-blade turbine as an <img> with an inline SVG data URI.

    Streamlit sanitises raw <svg> markup, so the drawing travels as an image.
    The rotation lives inside the SVG's own <style>, which browsers do run in
    SVG images, and it honours prefers-reduced-motion. period_s=None = still rotor.
    """
    tower = "#14303F" if highlighted else "#B9CBD4"
    animation = (
        f".rotor{{transform-origin:100px 78px;animation:spin {period_s:.2f}s linear infinite}}"
        "@keyframes spin{to{transform:rotate(360deg)}}"
        "@media (prefers-reduced-motion:reduce){.rotor{animation:none}}"
        if period_s
        else ".rotor{transform-origin:100px 78px;transform:rotate(18deg)}"
    )
    blade = "M100 78 C106 58 106 26 100 6 C96 26 95 58 100 78 Z"
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 300">'
        f"<style>{animation}</style>"
        f'<polygon points="96,82 104,82 112,292 88,292" fill="{tower}"/>'
        '<rect x="90" y="70" width="34" height="16" rx="5" fill="#14303F"/>'
        f'<circle cx="118" cy="66" r="7" fill="{light}" stroke="#FFFFFF" stroke-width="2"/>'
        '<g class="rotor">'
        f'<path d="{blade}" fill="#0E7C9A"/>'
        f'<path d="{blade}" fill="#0E7C9A" transform="rotate(120 100 78)"/>'
        f'<path d="{blade}" fill="#0E7C9A" transform="rotate(240 100 78)"/>'
        '<circle cx="100" cy="78" r="7" fill="#14303F"/>'
        "</g></svg>"
    )
    data = base64.b64encode(svg.encode()).decode()
    state = "parada" if not period_s else f"girando, uma volta a cada {number(period_s)} s"
    return f'<img class="turbine" src="data:image/svg+xml;base64,{data}" width="{width}" alt="Turbina {state}">'


def turbine_status(stopped: bool, availability: float, target: float) -> tuple[str, str]:
    """(light colour, status text)."""
    if stopped:
        return "#C8362B", "parada"
    if availability < target:
        return "#D99A1E", "abaixo da meta"
    return "#2F8F5B", "operando"


def farm_row(turbines: list[dict], selected_id: int, target: float, base_period_s: float | None) -> None:
    """Every turbine of a farm side by side; speed reflects availability."""
    cells = []
    for t in turbines:
        light, status = turbine_status(t["stopped_at_end"], t["availability"], target)
        if t["stopped_at_end"] or base_period_s is None:
            period = None
        else:
            period = base_period_s / availability_factor(t["availability"], target)
        selected = t["turbine_id"] == selected_id
        cells.append(
            f'<div class="farm-cell{" selected" if selected else ""}">'
            f"{turbine_svg(period, light, 92, highlighted=selected)}"
            f'<div class="code">{escape(t["turbine_code"])}</div>'
            f'<div class="avail">{pct(t["availability"])}</div>'
            f'<div class="status" style="color:{light}">{status}</div></div>'
        )
    st.markdown(f'<div class="farm-row">{"".join(cells)}</div>', unsafe_allow_html=True)


def hero_turbine(period_s: float | None, light: str) -> None:
    st.markdown(
        f'<div class="hero-turbine">{turbine_svg(period_s, light, 170, highlighted=True)}</div>',
        unsafe_allow_html=True,
    )
