"""'How customers switch' chart: which chat vendor ran on each customer's site, month by month.

Built with Plotly from the cached timelines of backend.switch_timeline. Pure functions
(segments, figure, headline) so they can be tested without Streamlit.
"""
from __future__ import annotations

from html import escape

import pandas as pd
import plotly.graph_objects as go

from backend import switch_timeline as stl

# class → (icon, legend label template, colour, hatch pattern or "")
STYLE = {
    stl.OURS_ONLY:              ("🟢", "{p} only", "#0ca30c", ""),
    stl.BOTH:                   ("🟠", "Overlap / possible trial", "#ec835a", ""),
    stl.COMPETITOR_ONLY:        ("⚫", "Competitor only", "#52514e", ""),
    stl.COMPETITOR_OURS_HIDDEN: ("◐", "Competitor seen · {p} hidden (Tag Manager)", "#52514e", "/"),
    stl.CHAT_HIDDEN:            ("◌", "Chat via Tag Manager · not visible in archive", "#c3c2b7", "/"),
    stl.NONE_DETECTED:          ("⚪", "No chat detected", "#c3c2b7", ""),
    stl.NO_SNAPSHOT:            ("▨", "No archive snapshot", "#e1e0d9", "x"),
}
ROW_HEIGHT = 56
WARNING_MONTHS = 3  # the threshold the headline talks about


def label(cls: str, product: str) -> str:
    icon, text, *_ = STYLE[cls]
    return f"{icon} {text.format(p=product)}"


def _month_start(m: str) -> pd.Timestamp:
    return pd.Timestamp(f"{m}-01")


def _month_end(m: str) -> pd.Timestamp:
    return _month_start(m) + pd.offsets.MonthBegin(1)


def _fmt(m: str) -> str:
    return _month_start(m).strftime("%b %Y")


def segments(months: list[dict]) -> list[dict]:
    """Contiguous runs of the same class: [{"class", "start", "end", "vendors", "snapshot", "n_captures"}]."""
    out = []
    for m in months:
        if out and out[-1]["class"] == m["class"]:
            seg = out[-1]
            seg["end"] = m["month"]
        else:
            seg = {"class": m["class"], "start": m["month"], "end": m["month"], "vendors": set(),
                   "snapshot": None, "n_captures": 0}
            out.append(seg)
        seg["vendors"] |= set(m.get("vendors", []))
        if m.get("snapshots"):
            seg["n_captures"] += 1
            seg["snapshot"] = seg["snapshot"] or m["snapshots"][0]["url"]
    for seg in out:
        seg["vendors"] = sorted(seg["vendors"])
    return out


def switch_text(summary: dict, product: str) -> str | None:
    sw = summary.get("switch")
    if not sw:
        return None
    a, b = sw["window"]
    when = _fmt(a) if a == b else f"{_month_start(a).strftime('%b')}–{_fmt(b)}" \
        if a[:4] == b[:4] else f"{_fmt(a)}–{_fmt(b)}"
    text = f"{product} → {', '.join(sw['to'])} · {when}"
    if summary.get("warning_months") is not None:
        text += f" · {summary['warning_months']} mo warning"
    return text


def headline(entries: list[dict], product: str) -> str:
    """Sentence computed from the data; never states a number the data doesn't have."""
    real = [e for e in entries if not e["timeline"].get("demo")]
    done = [e for e in real if e["timeline"]["summary"].get("switch")]
    if not done:
        if any(e["timeline"]["summary"].get("switch") for e in entries):
            return "No completed switches among real customers in the archived period; only the demo customer shows one."
        return "No completed switches found in the archived period."
    warned = [e["timeline"]["summary"]["warning_months"] for e in done
              if e["timeline"]["summary"].get("warning_months") is not None]
    early = sum(1 for wm in warned if wm >= WARNING_MONTHS)
    n = len(done)
    s = "switch" if n == 1 else "switches"
    if early:
        return (f"In {early} of {n} completed {s} the competitor appeared on the site "
                f"{WARNING_MONTHS}+ months before {product} was removed.")
    if warned:
        return (f"In {len(warned)} of {n} completed {s} the competitor appeared before {product} was removed, "
                f"but less than {WARNING_MONTHS} months before.")
    return f"{n} completed {s}; the archive shows no overlap before {product} was removed."


def figure(entries: list[dict], product: str, status_icons: dict) -> go.Figure:
    """entries: [{"site", "status", "timeline"}], already in display order (most urgent first)."""
    rows = [f"{status_icons.get(e['status'], '')} {e['site']}" for e in entries]
    fig = go.Figure()
    for row, e in zip(rows, entries):
        for seg in segments(e["timeline"]["months"]):
            cls = seg["class"]
            _, _, color, hatch = STYLE[cls]
            start, end = _month_start(seg["start"]), _month_end(seg["end"])
            period = _fmt(seg["start"]) if seg["start"] == seg["end"] else f"{_fmt(seg['start'])} – {_fmt(seg['end'])}"
            proof = seg["snapshot"] or "no snapshot in this period"
            fig.add_trace(go.Bar(
                y=[row], x=[(end - start).total_seconds() * 1000], base=[start], orientation="h",
                marker=dict(color=color, pattern=dict(shape=hatch, fgcolor="#52514e", size=6) if hatch else None,
                            line=dict(width=0)),
                width=0.46, name=label(cls, product), showlegend=False,
                customdata=[[period, ", ".join(seg["vendors"]) or "–", seg["n_captures"], proof]],
                hovertemplate=("<b>%{y}</b><br>%{customdata[0]}<br>" + escape(label(cls, product)) +
                               "<br>Detected: %{customdata[1]}<br>Archive snapshots: %{customdata[2]}"
                               "<br>Proof: %{customdata[3]}<extra></extra>"),
            ))
        text = switch_text(e["timeline"]["summary"], product)
        if text:
            at = _month_start(e["timeline"]["summary"]["switch"]["window"][1])
            fig.add_trace(go.Scatter(x=[at], y=[row], mode="markers", showlegend=False,
                                     marker=dict(symbol="diamond", size=11, color="#0b0b0b",
                                                 line=dict(color="#ffffff", width=2)),
                                     hovertemplate=f"<b>Switch</b><br>{escape(text)}<extra></extra>"))
            fig.add_annotation(x=at, y=row, text=escape(text), showarrow=False, yshift=19,
                               xanchor="right", font=dict(size=11))
    checks = [e["timeline"]["live"]["checked_at"][:10] for e in entries if e["timeline"].get("live")]
    if checks:
        today = max(checks)
        fig.add_vline(x=pd.Timestamp(today).timestamp() * 1000, line_width=1, line_color="#898781")
        fig.add_annotation(x=pd.Timestamp(today), y=1, yref="paper", text="Last live check", showarrow=False,
                           xanchor="right", yanchor="bottom", font=dict(size=11, color="#898781"))
    fig.update_layout(
        barmode="overlay", height=90 + ROW_HEIGHT * len(rows), margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(type="date", showgrid=True, gridcolor="rgba(128,128,128,.2)", tickformat="%b %Y"),
        yaxis=dict(autorange="reversed", categoryorder="array", categoryarray=rows, showgrid=False),
        hoverlabel=dict(align="left"), bargap=0.5,
    )
    return fig


def legend_classes(entries: list[dict]) -> list[str]:
    """Classes that actually appear, in legend order."""
    present = {m["class"] for e in entries for m in e["timeline"]["months"]}
    return [c for c in stl.CLASSES if c in present]
