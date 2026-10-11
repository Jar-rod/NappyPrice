"""Price history chart."""
from __future__ import annotations

import plotly.graph_objects as go

# One fixed colour per store (light, dark), so a store keeps its colour on every
# item whichever other stores are present. Order matters: neighbours in this
# list stay distinguishable for colour-blind readers.
STORE_COLOURS = {
    "clicks":    ("#2a78d6", "#3987e5"),
    "dischem":   ("#eb6834", "#d95926"),
    "babycity":  ("#1baf7a", "#199e70"),
    "makro":     ("#eda100", "#c98500"),
    "pnp":       ("#e87ba4", "#d55181"),
    "takealot":  ("#008300", "#008300"),
    "checkers":  ("#6250d6", "#9085e9"),
    "babiesrus": ("#e34948", "#e66767"),
}
OTHER = ("#8a8984", "#8a8984")   # a ninth store (Amazon.co.za) takes neutral grey, never a ninth hue


def history_chart(points: list[dict], unit: str, target: float | None, dark: bool) -> go.Figure:
    ink = "#f0efec" if dark else "#1b3a57"
    muted = "#c3c2b7" if dark else "#52647a"
    grid = "rgba(255,255,255,0.10)" if dark else "rgba(27,58,87,0.10)"
    surface = "#1a1a19" if dark else "#ffffff"

    series: dict[str, list[dict]] = {}
    for point in points:
        series.setdefault(point["series"], []).append(point)

    fig = go.Figure()
    for name, rows in series.items():
        colour = STORE_COLOURS.get(rows[0]["store_id"], OTHER)[1 if dark else 0]
        # A marker on every point when there are few, else only on the latest reading.
        sizes = [7] * len(rows) if len(rows) <= 14 else [0] * (len(rows) - 1) + [8]
        fig.add_trace(go.Scatter(
            x=[r["at"] for r in rows], y=[r["unit_price"] for r in rows], name=name, mode="lines+markers",
            line=dict(color=colour, width=2, shape="hv"),
            marker=dict(size=sizes, color=colour, line=dict(color=surface, width=2)),
            customdata=[[r["price"], r["units"], " · on special" if r["on_special"] else ""] for r in rows],
            hovertemplate="R%{y:.2f} per " + unit + " · R%{customdata[0]:.2f} for %{customdata[1]}%{customdata[2]}"
                          "<extra>%{fullData.name}</extra>",
        ))
    # With only a few days of readings, tick once per day so labels do not repeat.
    times = [p["at"] for p in points]
    few_days = bool(times) and (max(times) - min(times)).days < 5
    if target:
        fig.add_hline(y=target, line=dict(color=muted, width=1, dash="dash"),
                      annotation_text=f"Target R{target:.2f}", annotation_position="bottom right",
                      annotation_font=dict(color=muted, size=11))
    fig.update_layout(
        height=340, margin=dict(l=48, r=8, t=8, b=32), hovermode="x unified", showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=muted, size=12), title=None),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color=ink),
        hoverlabel=dict(bgcolor=surface, font=dict(color=ink)),
        xaxis=dict(showgrid=False, tickfont=dict(color=muted, size=11), linecolor=grid, hoverformat="%a %d %b",
                   tickformat="%d %b", nticks=5, automargin=True,
                   **({"dtick": 86400000} if few_days else {})),
        yaxis=dict(gridcolor=grid, zeroline=False, tickprefix="R", tickformat=".2f", tickfont=dict(color=muted, size=11),
                   title=None, fixedrange=True, automargin=True, nticks=6),
    )
    return fig
