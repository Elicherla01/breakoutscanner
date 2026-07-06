"""NIFTY 500 multi-timeframe breakout scanner — Streamlit UI."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from config import (
    NARROW_PERCENTILE,
    NARROW_PERCENTILE_MAX,
    NARROW_PERCENTILE_MIN,
    NARROW_PERCENTILE_PRESETS,
    STRICT_ATR_MULT,
    STRICT_VOL_MULT,
    TIMEFRAMES,
    TIMEFRAME_ORDER,
    UNIVERSE_CHOICES,
    UNIVERSE_FNO,
    UNIVERSE_NIFTY500,
    ensure_dirs,
    sort_timeframes,
)
from cpr import levels_for_chart
from cpr_scanner import apply_narrow_percentile, filter_results as filter_cpr_results, scan_universe as scan_cpr_universe
from data_loader import load_bars, load_daily, load_universe_symbols, resolve_universe_symbols
from fno_loader import fno_symbol_set, load_fno_symbols
from results_store import (
    cached_cpr_scan_available,
    cached_scan_available,
    format_scanned_at,
    load_cpr_results,
    load_scan_results,
    save_cpr_results,
    save_scan_results,
)
from scanner import filter_results, scan_universe

DISCLAIMER_URL = "https://github.com/Elicherla01/breakoutscanner/blob/main/DISCLAIMER.md"

st.set_page_config(
    page_title="NIFTY 500 Breakout Scanner",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
.breakout-card {
    padding: 0.9rem 1rem;
    border-radius: 12px;
    margin-bottom: 0.75rem;
    border: 1px solid rgba(255,255,255,0.1);
    box-shadow: 0 4px 16px rgba(0,0,0,0.35);
    min-height: 130px;
}
.breakout-card.bullish {
    background: linear-gradient(145deg, #0d2818 0%, #1b4332 45%, #2d6a4f 100%);
    border-left: 5px solid #52b788;
}
.breakout-card.bearish {
    background: linear-gradient(145deg, #3b0a0a 0%, #6b1515 45%, #9b2226 100%);
    border-left: 5px solid #f4845f;
}
.card-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.5rem;
    margin-bottom: 0.55rem;
    flex-wrap: wrap;
}
.card-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    justify-content: flex-end;
}
.card-symbol {
    font-size: 1.15rem;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 0.02em;
}
.card-badges span {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 700;
    padding: 0.18rem 0.5rem;
    border-radius: 999px;
    background: rgba(255,255,255,0.14);
    color: #f8fafc;
}
.card-pill {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 700;
    padding: 0.18rem 0.5rem;
    border-radius: 999px;
    background: rgba(255,255,255,0.14);
    color: #f8fafc;
    margin-left: 0.25rem;
}
.card-badges .high52,
.card-pill.high52 {
    background: rgba(251, 191, 36, 0.25);
    color: #fde68a;
}
.card-stat-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem 0.75rem;
    margin-bottom: 0.45rem;
}
.card-stat {
    font-size: 0.82rem;
    color: #e2e8f0;
}
.card-stat b {
    color: #ffffff;
    font-weight: 700;
}
.card-foot {
    font-size: 0.74rem;
    color: #cbd5e1;
    opacity: 0.92;
}
.summary-metrics {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
}
.summary-metric {
    flex: 1 1 120px;
    min-width: 110px;
    padding: 0.5rem 0.65rem;
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.08);
}
.summary-metric .sm-label {
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 0.15rem;
    opacity: 0.9;
}
.summary-metric .sm-value {
    font-size: 0.95rem;
    font-weight: 700;
    line-height: 1.25;
    word-break: break-word;
}
.summary-metric.breakouts {
    background: linear-gradient(145deg, #1e1b4b 0%, #312e81 100%);
    border-left: 3px solid #a78bfa;
}
.summary-metric.breakouts .sm-label { color: #c4b5fd; }
.summary-metric.breakouts .sm-value { color: #ede9fe; }
.summary-metric.bullish {
    background: linear-gradient(145deg, #052e16 0%, #14532d 100%);
    border-left: 3px solid #4ade80;
}
.summary-metric.bullish .sm-label { color: #86efac; }
.summary-metric.bullish .sm-value { color: #dcfce7; }
.summary-metric.bearish {
    background: linear-gradient(145deg, #450a0a 0%, #7f1d1d 100%);
    border-left: 3px solid #f87171;
}
.summary-metric.bearish .sm-label { color: #fca5a5; }
.summary-metric.bearish .sm-value { color: #fee2e2; }
.summary-metric.symbols {
    background: linear-gradient(145deg, #0c4a6e 0%, #075985 100%);
    border-left: 3px solid #38bdf8;
}
.summary-metric.symbols .sm-label { color: #7dd3fc; }
.summary-metric.symbols .sm-value { color: #e0f2fe; }
.summary-metric.scanned {
    background: linear-gradient(145deg, #451a03 0%, #78350f 100%);
    border-left: 3px solid #fbbf24;
}
.summary-metric.scanned .sm-label { color: #fcd34d; }
.summary-metric.scanned .sm-value { color: #fef3c7; font-size: 0.82rem; font-weight: 600; }
.cpr-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 1rem;
}
.cpr-legend-item {
    font-size: 0.78rem;
    padding: 0.35rem 0.65rem;
    border-radius: 8px;
    font-weight: 600;
    border: 1px solid rgba(255,255,255,0.12);
}
.cpr-legend-item.vw { background: rgba(124,58,237,0.35); color: #ddd6fe; }
.cpr-legend-item.vn { background: rgba(37,99,235,0.35); color: #bfdbfe; }
.cpr-legend-item.wide { background: rgba(220,38,38,0.35); color: #fecaca; }
.cpr-legend-item.virgin { background: rgba(22,163,74,0.25); color: #86efac; }
.cpr-legend-item.touched { background: rgba(220,38,38,0.25); color: #fca5a5; }
</style>
""",
    unsafe_allow_html=True,
)

_DIR_STYLE = {
    "bullish": ("🟢 Bullish", "#16a34a"),
    "bearish": ("🔴 Bearish", "#dc2626"),
}

_CPR_TYPE_COLORS = {
    "V+W": "#7c3aed",
    "V+N": "#2563eb",
    "V": "#16a34a",
    "WIDE": "#dc2626",
    "NARROW": "#f59e0b",
    "TOUCHED": "#6b7280",
}

_CPR_TREND_ICONS = {"above": "🟢 ↑", "below": "🔴 ↓", "inside": "🟡 •"}

_INDEX_SYMBOLS = frozenset({"VIX", "INDIAVIX", "NIFTY", "BANKNIFTY", "SENSEX"})

_DISCLAIMER_SIDEBAR = """
**Not financial advice.** For informational, educational, and research use only.

- Scan results are **algorithmic outputs** — not buy/sell recommendations  
- Trading securities involves **substantial risk of loss**  
- Market data may be **delayed, incomplete, or inaccurate**  
- Past breakouts do **not** guarantee future performance  
- Authors are **not** SEBI-registered investment advisers  
- Consult a **qualified financial adviser** before trading  

[Full disclaimer]({url})
""".format(
    url=DISCLAIMER_URL
)


def _render_disclaimer_banner() -> None:
    st.markdown(
        f"""
<div style="background:rgba(251,191,36,0.12);border:1px solid rgba(251,191,36,0.35);
border-radius:10px;padding:0.75rem 1rem;margin-bottom:1rem;">
<p style="color:#fde68a;margin:0;font-size:0.88rem;line-height:1.5;">
<strong>⚠️ Disclaimer:</strong> This app is for <strong>research and education only</strong> — not investment advice.
Breakout signals are not recommendations to trade. You may lose capital. Data from third-party sources
may be delayed or wrong.
<a href="{DISCLAIMER_URL}" target="_blank" rel="noopener" style="color:#fcd34d;">Read full disclaimer</a>
</p></div>
""",
        unsafe_allow_html=True,
    )


def _render_disclaimer_sidebar() -> None:
    st.divider()
    st.markdown("#### ⚖️ Legal disclaimer")
    st.markdown(_DISCLAIMER_SIDEBAR)


def _render_summary_metrics(
    *,
    breakouts: int,
    bullish: int,
    bearish: int,
    symbols_scanned: int | str,
    scanned_label: str,
) -> None:
    html = f"""
<div class="summary-metrics">
  <div class="summary-metric breakouts">
    <div class="sm-label">Breakouts</div>
    <div class="sm-value">{breakouts}</div>
  </div>
  <div class="summary-metric bullish">
    <div class="sm-label">Bullish</div>
    <div class="sm-value">{bullish}</div>
  </div>
  <div class="summary-metric bearish">
    <div class="sm-label">Bearish</div>
    <div class="sm-value">{bearish}</div>
  </div>
  <div class="summary-metric symbols">
    <div class="sm-label">Symbols Scanned</div>
    <div class="sm-value">{symbols_scanned}</div>
  </div>
  <div class="summary-metric scanned">
    <div class="sm-label">Last Scanned</div>
    <div class="sm-value">{scanned_label}</div>
  </div>
</div>
"""
    _render_card_html(html)


def _render_last_scan_panel(meta: dict, results: pd.DataFrame | None = None) -> None:
    scanned_at = meta.get("scanned_at_display") or format_scanned_at(meta.get("scanned_at") or meta.get("saved_at"))
    if not scanned_at or scanned_at == "—":
        return

    n_breakouts = int(meta.get("breakout_count", len(results) if results is not None else 0))
    n_sym = meta.get("symbols_scanned", meta.get("symbols", "—"))
    timeframes = meta.get("timeframes", "")
    if isinstance(timeframes, list):
        timeframes = ", ".join(timeframes)
    mode = meta.get("mode", meta.get("breakout_mode", "—"))
    universe_label = meta.get("universe_choice", "")
    sample = meta.get("universe_sample", "")
    total = meta.get("universe_total")
    if sample == "even" and total:
        universe_txt = f"{n_sym} of {total} NIFTY 500 (even sample)"
    elif universe_label:
        universe_txt = f"{n_sym} symbols · {universe_label}"
    else:
        universe_txt = f"{n_sym} symbols"

    st.markdown(
        f"""
<div style="background:rgba(59,130,246,0.10);border:1px solid rgba(59,130,246,0.35);
border-radius:10px;padding:0.85rem 1.1rem;margin-bottom:0.85rem;">
<p style="color:#93c5fd;margin:0 0 0.35rem;font-size:0.95rem;font-weight:700;">
🕒 Last scanned: {scanned_at}
</p>
<p style="color:#cbd5e1;margin:0;font-size:0.84rem;line-height:1.55;">
<strong>{n_breakouts}</strong> breakouts · <strong>{universe_txt}</strong> ·
<strong>{timeframes or "—"}</strong> · <strong>{mode}</strong>
</p>
<p style="color:#94a3b8;margin:0.35rem 0 0;font-size:0.76rem;">
Cached locally in <code>data_cache/scan_results.csv</code> and <code>data_cache/scan_info.csv</code>
</p>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_disclaimer_footer() -> None:
    st.markdown(
        f"""
---
<p style="font-size:0.75rem;color:#94a3b8;line-height:1.55;margin-top:1.5rem;">
<strong>Disclaimer:</strong> The NIFTY 500 Breakout Scanner is provided for informational and educational
purposes only. It does not constitute investment, trading, tax, or legal advice and does not create an
adviser–client relationship. Trading in securities involves substantial risk of loss. Algorithmic scan
outputs are based on historical data and may be inaccurate. Past performance is not indicative of future
results. Use at your own risk.
<a href="{DISCLAIMER_URL}" target="_blank" rel="noopener" style="color:#94a3b8;">Full disclaimer</a>
·
<a href="https://breakoutscanner.streamlit.app/" style="color:#94a3b8;">Live app</a>
</p>
""",
        unsafe_allow_html=True,
    )


def _breakout_card_html(row: pd.Series) -> str:
    direction = str(row.get("direction", "")).lower()
    cls = "bullish" if direction == "bullish" else "bearish"
    dir_label = _DIR_STYLE.get(direction, ("—", ""))[0]
    tf = row.get("timeframe", "")
    tf_label = TIMEFRAMES[tf].label if tf in TIMEFRAMES else tf
    high52 = row.get("is_52w_high", False)
    if not isinstance(high52, bool):
        high52 = str(high52).strip().lower() in {"1", "true", "yes", "t"}
    break_pct = float(row.get("breakout_pct", 0))
    sign = "+" if break_pct >= 0 else ""
    vol = row.get("volume_ratio")
    vol_txt = f"{float(vol):.2f}×" if vol is not None and pd.notna(vol) else "—"
    tr_atr = row.get("tr_atr_ratio")
    bar_time = row.get("bar_time", "")
    is_strict = str(row.get("mode", "")).lower() == "strict"

    badges = [
        f'<span class="card-pill">{tf_label}</span>',
        f'<span class="card-pill">{dir_label}</span>',
    ]
    if high52:
        badges.append('<span class="card-pill high52">52W High</span>')
    if is_strict:
        badges.append('<span class="card-pill high52">Strict</span>')

    stats_row1 = [
        f'<span class="card-stat">Close <b>₹{float(row["close"]):,.2f}</b></span>',
        f'<span class="card-stat">Break <b>{sign}{break_pct:.2f}%</b></span>',
        f'<span class="card-stat">Vol <b>{vol_txt}</b></span>',
    ]
    if tr_atr is not None and pd.notna(tr_atr):
        stats_row1.append(f'<span class="card-stat">TR/ATR <b>{float(tr_atr):.2f}×</b></span>')

    stats_row2 = [
        f'<span class="card-stat">Level <b>₹{float(row["level"]):,.2f}</b></span>',
        (
            f'<span class="card-stat">Prior H/L '
            f'<b>₹{float(row["prior_high"]):,.0f}</b> / <b>₹{float(row["prior_low"]):,.0f}</b></span>'
        ),
    ]

    return (
        f'<div class="breakout-card {cls}">'
        f'<div class="card-top">'
        f'<span class="card-symbol">{row["symbol"]}</span>'
        f'<span class="card-badges">{"".join(badges)}</span>'
        f"</div>"
        f'<div class="card-stat-row">{"".join(stats_row1)}</div>'
        f'<div class="card-stat-row">{"".join(stats_row2)}</div>'
        f'<span class="card-foot">Bar {bar_time} · Lookback {int(row.get("lookback", 0))} bars</span>'
        f"</div>"
    )


def _render_card_html(html: str) -> None:
    if hasattr(st, "html"):
        st.html(html)
    else:
        st.markdown(html, unsafe_allow_html=True)


def render_breakout_cards(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No breakouts in this view.")
        return

    cols_per_row = 3
    for i in range(0, len(df), cols_per_row):
        chunk = df.iloc[i : i + cols_per_row]
        cols = st.columns(cols_per_row)
        for c_idx, (_, row) in enumerate(chunk.iterrows()):
            with cols[c_idx]:
                _render_card_html(_breakout_card_html(row))


def _style_results(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["direction"] = out["direction"].map(lambda d: _DIR_STYLE.get(d, ("—", ""))[0])
    out["timeframe"] = out["timeframe"].map(lambda t: TIMEFRAMES[t].label if t in TIMEFRAMES else t)
    out["is_52w_high"] = out["is_52w_high"].map(lambda x: "Yes" if x else "No")
    if "mode" in out.columns:
        out["mode"] = out["mode"].map(lambda m: "Strict (ATR)" if m == "strict" else "Standard")
    rename = {
        "symbol": "Symbol",
        "timeframe": "Timeframe",
        "direction": "Direction",
        "mode": "Mode",
        "close": "Close",
        "level": "Break Level",
        "breakout_pct": "Break %",
        "volume_ratio": "Vol Ratio",
        "tr_atr_ratio": "TR/ATR",
        "true_range": "True Range",
        "atr": "ATR(14)",
        "prior_high": "Prior High",
        "prior_low": "Prior Low",
        "bar_time": "Bar Date",
        "lookback": "Lookback",
        "is_52w_high": "52W High?",
    }
    return out.rename(columns={k: v for k, v in rename.items() if k in out.columns})


def _chart(symbol: str, timeframe: str, level: float) -> go.Figure:
    df = load_bars(symbol, timeframe, use_cache=True)
    if df.empty:
        fig = go.Figure()
        fig.update_layout(title=f"{symbol} — no data")
        return fig

    tail_n = {"1H": 120, "1D": 120, "1W": 52}.get(timeframe.upper(), 100)
    tail = df.tail(tail_n)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.04)

    fig.add_trace(
        go.Candlestick(
            x=tail.index,
            open=tail["open"],
            high=tail["high"],
            low=tail["low"],
            close=tail["close"],
            name=symbol,
        ),
        row=1,
        col=1,
    )
    fig.add_hline(y=level, line_dash="dash", line_color="#f59e0b", annotation_text="Break level", row=1, col=1)

    if "volume" in tail.columns:
        colors = ["#16a34a" if c >= o else "#dc2626" for c, o in zip(tail["close"], tail["open"])]
        fig.add_trace(
            go.Bar(x=tail.index, y=tail["volume"], marker_color=colors, name="Volume", showlegend=False),
            row=2,
            col=1,
        )

    tf_label = TIMEFRAMES.get(timeframe.upper())
    title = f"{symbol} — {tf_label.label if tf_label else timeframe} breakout"
    fig.update_layout(
        title=title,
        height=480,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        paper_bgcolor="#0e1117",
        plot_bgcolor="#1a1d24",
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    return fig


def _cpr_status_rate(row: pd.Series) -> str:
    """Status/Rate column: index LTP or type badge (V + W, WIDE, etc.)."""
    sym = str(row.get("symbol", "")).upper()
    if sym in _INDEX_SYMBOLS:
        ltp = row.get("ltp")
        return f"{float(ltp):,.2f}" if ltp is not None and pd.notna(ltp) else "—"
    cpr_type = str(row.get("type", "—"))
    return cpr_type.replace("+", " + ")


def _normalize_cpr_results(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure CPR scan frames have expected columns after CSV round-trip."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    for col in ("is_virgin", "is_narrow"):
        if col in out.columns:
            out[col] = out[col].map(_parse_bool_value)
    for col in ("distance_pct", "width_pct", "width_percentile", "ltp", "tc", "bc", "pivot"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "is_narrow" not in out.columns:
        out["is_narrow"] = False
    if "type" not in out.columns:
        out["type"] = "—"
    return out


def _parse_bool_value(val: object) -> bool:
    if isinstance(val, bool):
        return val
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    return str(val).strip().lower() in {"1", "true", "yes", "t"}


def _cpr_metric_count(df: pd.DataFrame, col: str, *, match: str | None = None) -> int:
    if df.empty or col not in df.columns:
        return 0
    if match is None:
        return int(df[col].sum())
    return int((df[col] == match).sum())


def _style_cpr_results(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    display = df.copy()
    display["status_rate"] = display.apply(_cpr_status_rate, axis=1)
    if "is_virgin" in display.columns:
        display["virgin_status"] = display["is_virgin"].map(lambda x: "VIRGIN" if x else "TOUCHED")
    else:
        display["virgin_status"] = "—"
    if "distance_pct" in display.columns:
        display["distance"] = display["distance_pct"].map(
            lambda x: f"{x:+.2f}%" if pd.notna(x) else "—"
        )
    else:
        display["distance"] = "—"
    if "trend" in display.columns:
        display["trend_icon"] = display["trend"].map(_CPR_TREND_ICONS).fillna("—")
    else:
        display["trend_icon"] = "—"
    display = display.drop(columns=["type"], errors="ignore")
    return display.rename(
        columns={
            "symbol": "Symbol",
            "status_rate": "Status / Rate",
            "virgin_status": "Type",
            "distance": "Distance",
            "trend_icon": "Trend",
            "ltp": "LTP",
            "tc": "TC",
            "bc": "BC",
            "pivot": "Pivot",
            "width_pct": "CPR Width %",
            "width_percentile": "Width %ile",
            "days_virgin": "Days Virgin",
            "source_date": "CPR From",
            "session_date": "Session",
        }
    )


def _cpr_chart(symbol: str, timeframe: str = "Daily") -> go.Figure:
    daily = load_daily(symbol, use_cache=True)
    fig = go.Figure()
    if daily.empty:
        fig.update_layout(title=f"{symbol} — no data")
        return fig

    tail = daily.tail(60)
    fig.add_trace(
        go.Candlestick(
            x=tail.index,
            open=tail["open"],
            high=tail["high"],
            low=tail["low"],
            close=tail["close"],
            name=symbol,
        )
    )

    levels = levels_for_chart(daily, timeframe=timeframe)
    colors = {
        "CPR HIGH (TC)": "#ef4444",
        "CPR TC": "#f97316",
        "CPR PIVOT": "#a855f7",
        "CPR BC": "#3b82f6",
        "CPR LOW (BC)": "#22c55e",
        "R1": "#eab308",
        "S1": "#14b8a6",
    }
    for label, price in levels.items():
        fig.add_hline(
            y=price,
            line_dash="dot" if "BC" in label or "TC" in label else "dash",
            line_color=colors.get(label, "#94a3b8"),
            annotation_text=f"{label} {price:.2f}",
        )

    fig.update_layout(
        title=f"{symbol} — {timeframe} CPR levels",
        xaxis_rangeslider_visible=False,
        height=480,
        template="plotly_dark",
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig


def _render_cpr_legend() -> None:
    html = """
<div class="cpr-legend">
  <span class="cpr-legend-item vw">V + W — Virgin + Wide (high probability)</span>
  <span class="cpr-legend-item vn">V + N — Virgin + Narrow (trend continuation)</span>
  <span class="cpr-legend-item wide">WIDE — Wide CPR (move may expand)</span>
  <span class="cpr-legend-item virgin">VIRGIN — Untouched CPR</span>
  <span class="cpr-legend-item touched">TOUCHED — CPR already touched</span>
</div>
"""
    _render_card_html(html)


def _render_narrow_cpr_controls(cached_meta: dict) -> float:
    """Narrow CPR preset selector with optional custom percentile."""
    saved = cached_meta.get("narrow_percentile")
    default_pct = float(saved) if saved not in (None, "") else NARROW_PERCENTILE
    preset_labels = [f"{int(p)}%" for p in NARROW_PERCENTILE_PRESETS] + ["Custom"]
    default_preset = (
        f"{int(default_pct)}%"
        if default_pct in NARROW_PERCENTILE_PRESETS
        else "Custom"
    )

    st.markdown("##### Narrow CPR threshold")
    preset = st.selectbox(
        "Bottom percentile (narrowest widths)",
        preset_labels,
        index=preset_labels.index(default_preset) if default_preset in preset_labels else len(preset_labels) - 1,
        key="cpr_narrow_preset",
        help=(
            "Compare today's CPR width to each symbol's last 1-year history. "
            "**Narrow** when width ranks in the bottom X% (e.g. 5% = narrowest 5% of past widths)."
        ),
    )

    if preset == "Custom":
        st.session_state["cpr_narrow_custom_enabled"] = True
        custom_default = int(default_pct) if default_pct not in NARROW_PERCENTILE_PRESETS else int(NARROW_PERCENTILE)
        custom_pct = st.slider(
            "Custom bottom percentile (%)",
            int(NARROW_PERCENTILE_MIN),
            int(NARROW_PERCENTILE_MAX),
            min(max(custom_default, int(NARROW_PERCENTILE_MIN)), int(NARROW_PERCENTILE_MAX)),
            1,
            key="cpr_narrow_custom_pct",
        )
        narrow_pct = float(custom_pct)
    else:
        st.session_state["cpr_narrow_custom_enabled"] = False
        narrow_pct = float(preset.rstrip("%"))

    st.caption(
        f"Stocks with CPR width in the **bottom {narrow_pct:g}%** of their own 1-year history "
        f"are tagged **Narrow** (V + N when also Virgin)."
    )
    return narrow_pct


def _render_cpr_table(display: pd.DataFrame) -> None:
    table_cols = [
        c
        for c in [
            "Symbol",
            "Status / Rate",
            "Type",
            "Distance",
            "Trend",
            "LTP",
            "CPR Width %",
            "Width %ile",
            "TC",
            "BC",
            "Pivot",
            "Days Virgin",
            "CPR From",
            "Session",
        ]
        if c in display.columns
    ]
    if display.empty or not table_cols:
        st.info("No CPR rows match the current filters.")
        return

    def _color_type(val: str) -> str:
        if val == "VIRGIN":
            return "color: #4ade80; font-weight: 700"
        if val == "TOUCHED":
            return "color: #f87171; font-weight: 700"
        return ""

    def _color_status(val: str) -> str:
        key = str(val).replace(" ", "")
        if key == "V+W":
            return "background-color: rgba(124,58,237,0.35); color: #ddd6fe; font-weight: 700"
        if key == "V+N":
            return "background-color: rgba(37,99,235,0.35); color: #bfdbfe; font-weight: 700"
        if val == "WIDE":
            return "background-color: rgba(220,38,38,0.35); color: #fecaca; font-weight: 700"
        return ""

    subset = display[table_cols]
    try:
        styler = subset.style
        map_fn = getattr(styler, "map", styler.applymap)
        styled = map_fn(_color_status, subset=["Status / Rate"])
        map_fn2 = getattr(styled, "map", styled.applymap)
        styled = map_fn2(_color_type, subset=["Type"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
    except Exception:
        st.dataframe(subset, use_container_width=True, hide_index=True)


def render_cpr_tab(
    scan_symbols: list[str],
    *,
    universe_choice: str,
    universe_total: int,
    universe_sample: str,
) -> None:
    st.markdown(
        """
<div style="background:linear-gradient(135deg,#1e1b4b 0%,#312e81 55%,#1e3a5f 100%);
padding:1rem 1.25rem;border-radius:12px;margin-bottom:1rem;">
<h3 style="color:white;margin:0;">📊 Virgin CPR Scanner</h3>
<p style="color:#c7d2fe;margin:0.35rem 0 0;font-size:0.9rem;">
Today's CPR from yesterday's OHLC. <strong>Virgin</strong> = price has not touched the CPR zone [BC, TC] today.
</p></div>
""",
        unsafe_allow_html=True,
    )

    _render_cpr_legend()

    cached_cpr_df, cached_cpr_meta = load_cpr_results()
    cpr_meta = cached_cpr_meta or {}

    c1, c2 = st.columns(2)
    with c1:
        cpr_timeframe = st.radio(
            "CPR timeframe",
            ["Daily", "Weekly"],
            horizontal=True,
            key="cpr_timeframe",
        )
    with c2:
        st.metric("Symbols in scan", len(scan_symbols))

    narrow_pct = _render_narrow_cpr_controls(cpr_meta)

    f1, f2, f3, f4 = st.columns(4)
    with f1:
        virgin_only = st.checkbox("Virgin only", value=False, key="cpr_virgin_only")
    with f2:
        narrow_only = st.checkbox(
            "Narrow only",
            value=False,
            key="cpr_narrow_only",
            help=f"Show only symbols in the bottom {narrow_pct:g}% narrow CPR bucket.",
        )
    with f3:
        type_filter = st.multiselect(
            "Type filter",
            ["V+W", "V+N", "V", "WIDE", "NARROW", "TOUCHED"],
            default=["V+W", "V+N", "V", "WIDE", "NARROW", "TOUCHED"],
            key="cpr_type_filter",
        )
    with f4:
        trend_filter = st.selectbox("Trend", ["All", "above", "below", "inside"], key="cpr_trend_filter")

    use_cache = st.checkbox("Use price cache", value=True, key="cpr_use_cache")
    force_cpr = st.button("🔍 Scan CPR", type="primary", key="cpr_force_scan")

    if not force_cpr and cached_cpr_df is not None and "cpr_results" not in st.session_state:
        st.session_state["cpr_results"] = _normalize_cpr_results(cached_cpr_df)
        st.session_state["cpr_scan_meta"] = cached_cpr_meta

    if force_cpr:
        progress = st.progress(0.0, text="Scanning CPR…")
        status = st.empty()

        def on_cpr_progress(done: int, total: int, label: str) -> None:
            progress.progress(done / max(total, 1), text=f"CPR scan {label} ({done}/{total})…")

        with st.spinner("Computing Virgin CPR…"):
            raw = scan_cpr_universe(
                scan_symbols,
                progress_callback=on_cpr_progress,
                use_cache=use_cache,
                narrow_percentile=float(narrow_pct),
                timeframe=cpr_timeframe,
            )
        progress.progress(1.0, text="Done")
        status.empty()

        scan_meta = {
            "symbols": len(scan_symbols),
            "universe_total": universe_total,
            "universe_sample": universe_sample,
            "universe_choice": universe_choice,
            "timeframe": cpr_timeframe,
            "narrow_percentile": narrow_pct,
        }
        save_cpr_results(raw, scan_meta)
        _, saved_meta = load_cpr_results()
        st.session_state["cpr_results"] = _normalize_cpr_results(raw)
        st.session_state["cpr_scan_meta"] = saved_meta or scan_meta
        st.session_state["cpr_scan_timeframe"] = cpr_timeframe
        if chart_symbols := raw["symbol"].astype(str).tolist() if "symbol" in raw.columns else []:
            prev_pick = st.session_state.get("cpr_chart_pick")
            if prev_pick not in chart_symbols:
                st.session_state["cpr_chart_pick"] = chart_symbols[0]
        st.success(f"CPR scan complete — {len(raw)} symbols")

    results = st.session_state.get("cpr_results")
    if results is None or (isinstance(results, pd.DataFrame) and results.empty):
        if cached_cpr_scan_available():
            st.info("Cached CPR results available. Click **Scan CPR** to refresh, or load from cache on next visit.")
        else:
            st.info("Click **Scan CPR** to build the Virgin CPR screener.")
        return

    scan_tf = st.session_state.get("cpr_scan_timeframe", cached_cpr_meta.get("timeframe", "Daily"))
    if scan_tf != cpr_timeframe:
        st.warning(
            f"Selected timeframe ({cpr_timeframe}) differs from cached scan ({scan_tf}). "
            "Click **Scan CPR** to refresh."
        )

    meta = st.session_state.get("cpr_scan_meta", cached_cpr_meta or {})
    results = _normalize_cpr_results(results)

    results = apply_narrow_percentile(results, float(narrow_pct))
    scan_narrow_raw = meta.get("narrow_percentile")
    try:
        scan_narrow = float(scan_narrow_raw) if scan_narrow_raw not in (None, "") else float(narrow_pct)
    except (TypeError, ValueError):
        scan_narrow = float(narrow_pct)
    if abs(scan_narrow - narrow_pct) > 0.01:
        st.info(
            f"Narrow threshold changed to **bottom {narrow_pct:g}%** — "
            "types updated instantly from cached width percentiles (no rescan needed)."
        )
    filtered = filter_cpr_results(
        results,
        virgin_only=virgin_only,
        narrow_only=narrow_only,
        types=type_filter or None,
        trend=trend_filter,
    )

    scanned_label = meta.get("scanned_at_display") or format_scanned_at(
        meta.get("scanned_at"), short=True
    )
    session_date = (
        filtered["session_date"].iloc[0]
        if not filtered.empty and "session_date" in filtered.columns
        else results["session_date"].iloc[0] if "session_date" in results.columns else "—"
    )

    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    m1.metric("Total", len(filtered))
    m2.metric("Virgin", _cpr_metric_count(filtered, "is_virgin"))
    m3.metric("V + W", _cpr_metric_count(filtered, "type", match="V+W"))
    m4.metric("V + N", _cpr_metric_count(filtered, "type", match="V+N"))
    m5.metric("Narrow", _cpr_metric_count(filtered, "is_narrow"))
    m6.metric("Narrow cutoff", f"≤{narrow_pct:g}%")
    m7.metric("Last scan", scanned_label or "—")

    st.caption(
        f"Session **{session_date}** · {scan_tf} CPR · **{universe_choice}** · "
        f"narrow = bottom **{narrow_pct:g}%** of 1Y width history · "
        f"cached in `data_cache/cpr_scan_results.csv`"
    )

    display = _style_cpr_results(filtered)
    _render_cpr_table(display)

    chart_symbols = (
        filtered["symbol"].astype(str).tolist()
        if not filtered.empty and "symbol" in filtered.columns
        else results["symbol"].astype(str).tolist() if "symbol" in results.columns else []
    )
    if chart_symbols:
        prev_pick = st.session_state.get("cpr_chart_pick")
        if prev_pick not in chart_symbols:
            st.session_state["cpr_chart_pick"] = chart_symbols[0]
        pick = st.selectbox("Chart symbol", chart_symbols, key="cpr_chart_pick")
        st.plotly_chart(_cpr_chart(pick, timeframe=scan_tf), use_container_width=True, key="cpr_plotly_chart")
        row = filtered[filtered["symbol"].astype(str) == pick] if "symbol" in filtered.columns else pd.DataFrame()
        if row.empty and "symbol" in results.columns:
            row = results[results["symbol"].astype(str) == pick]
        if not row.empty:
            r = row.iloc[0]
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("CPR Type", r.get("type", "—"))
            c2.metric("Virgin?", "Yes" if r.get("is_virgin") else "Touched")
            width_pctile = r.get("width_percentile")
            c3.metric("Width %ile", f"{float(width_pctile):.1f}" if pd.notna(width_pctile) else "—")
            c4.metric("TC / BC", f"{r.get('tc', '—')} / {r.get('bc', '—')}")
            dist = r.get("distance_pct")
            c5.metric("Distance", f"{float(dist):+.2f}%" if pd.notna(dist) else "—")

        st.download_button(
            "Download CPR CSV",
            filtered.to_csv(index=False),
            file_name="cpr_scan.csv",
            mime="text/csv",
            key="cpr_download",
        )


def render_breakout_tab(
    scan_symbols: list[str],
    *,
    universe_choice: str,
    universe_total: int,
    universe_sample: str,
) -> None:
    symbols = scan_symbols
    dir_filter = None if direction == "Both" else direction.lower()

    cached_df, cached_meta = load_scan_results()

    force_refresh = st.button(
        "Force Refresh Scan",
        type="primary",
        help="Re-run scan and overwrite local CSV cache.",
        key="breakout_force_refresh",
    )

    if not force_refresh and cached_df is not None and "breakout_results" not in st.session_state:
        st.session_state["breakout_results"] = cached_df
        st.session_state["breakout_scan_meta"] = cached_meta

    if force_refresh:
        progress = st.progress(0.0, text="Loading prices…")
        status = st.empty()

        def on_progress(done: int, total: int, label: str) -> None:
            progress.progress(done / max(total, 1), text=f"Loading {label} ({done}/{total})…")
            status.caption(label)

        with st.spinner("Scanning breakouts…"):
            raw = scan_universe(
                symbols,
                selected_tfs or ["1D"],
                mode=breakout_mode,
                progress_callback=on_progress,
                use_cache=use_cache,
                vol_mult=vol_mult,
                lookback=lookback,
                atr_mult=atr_mult if breakout_mode == "strict" else None,
                direction_filter=dir_filter,
            )
            filtered = filter_results(
                raw,
                timeframes=selected_tfs,
                directions=[dir_filter] if dir_filter else None,
                min_vol_ratio=vol_mult,
                only_52w=only_52w,
            )

        progress.progress(1.0, text="Done")
        status.empty()

        scan_meta = {
            "symbols": len(symbols),
            "universe_total": universe_total,
            "universe_sample": universe_sample,
            "universe_choice": universe_choice,
            "timeframes": sort_timeframes(selected_tfs or ["1D"]),
            "mode": breakout_mode_label,
            "breakout_mode": breakout_mode,
            "direction": direction,
            "vol_mult": vol_mult,
            "lookback": lookback,
            "atr_mult": atr_mult if breakout_mode == "strict" else None,
            "only_52w": only_52w,
            "max_symbols": max_symbols,
        }
        save_scan_results(filtered, scan_meta)
        _, saved_meta = load_scan_results()
        st.session_state["breakout_results"] = filtered
        st.session_state["breakout_scan_meta"] = saved_meta or scan_meta
        scanned_display = format_scanned_at(
            st.session_state.get("breakout_scan_meta", {}).get("scanned_at")
        )
        st.success(
            f"Scan complete — {len(filtered)} breakouts saved at **{scanned_display}** "
            f"to `data_cache/scan_results.csv`."
        )

    panel_meta = st.session_state.get("breakout_scan_meta") or cached_meta
    panel_results = st.session_state.get("breakout_results", cached_df)
    if panel_meta and panel_results is not None:
        _render_last_scan_panel(panel_meta, panel_results)

    if "breakout_results" in st.session_state:
        results = st.session_state["breakout_results"]
        meta = st.session_state.get("breakout_scan_meta", {})
        n_sym = meta.get("symbols_scanned", meta.get("symbols", len(symbols)))

        cached_tfs_raw = meta.get("timeframes") or results["timeframe"].unique().tolist()
        if isinstance(cached_tfs_raw, str):
            cached_tfs = sort_timeframes([t.strip() for t in cached_tfs_raw.split(",") if t.strip()])
        else:
            cached_tfs = sort_timeframes(cached_tfs_raw)
        display_tfs = [t for t in cached_tfs if t in TIMEFRAMES]
        if selected_tfs and set(selected_tfs) != set(cached_tfs):
            st.info("Sidebar filters changed. Results below are from the last saved scan until you force refresh.")

        if results.empty:
            st.warning(f"No breakouts found across {n_sym} symbols on selected filters.")
        else:
            bull = int((results["direction"] == "bullish").sum())
            bear = int((results["direction"] == "bearish").sum())
            scanned_label = meta.get("scanned_at_display") or format_scanned_at(
                meta.get("scanned_at") or meta.get("saved_at"),
                short=True,
            )
            _render_summary_metrics(
                breakouts=len(results),
                bullish=bull,
                bearish=bear,
                symbols_scanned=n_sym,
                scanned_label=scanned_label,
            )
            if meta.get("mode"):
                st.caption(f"Mode: **{meta['mode']}** · cached results — use **Force Refresh Scan** to update")

            tf_tabs = st.tabs(["All"] + [TIMEFRAMES[t].label for t in display_tfs])

            def _show(df: pd.DataFrame, key: str) -> None:
                view = st.radio(
                    "View",
                    ["Cards", "Table"],
                    horizontal=True,
                    key=f"view_{key}",
                    label_visibility="collapsed",
                )

                if view == "Cards":
                    render_breakout_cards(df)
                else:
                    styled = _style_results(df)
                    st.dataframe(styled, use_container_width=True, hide_index=True, key=f"df_{key}")

                if not df.empty:
                    pick = st.selectbox(
                        "Chart symbol",
                        df["symbol"].tolist(),
                        key=f"chart_pick_{key}",
                    )
                    row = df[df["symbol"] == pick].iloc[0]
                    st.plotly_chart(
                        _chart(pick, row["timeframe"], float(row["level"])),
                        use_container_width=True,
                        key=f"plotly_{key}_{pick}",
                    )
                    st.download_button(
                        "Download CSV",
                        df.to_csv(index=False),
                        file_name=f"breakouts_{key}.csv",
                        mime="text/csv",
                        key=f"dl_{key}",
                    )

            with tf_tabs[0]:
                _show(results, "all")
            for i, tf in enumerate(display_tfs, start=1):
                with tf_tabs[i]:
                    _show(results[results["timeframe"] == tf], tf.lower())

    elif not cached_scan_available():
        st.info("No cached scan yet. Configure settings and click **Force Refresh Scan**.")


ensure_dirs()

st.markdown(
    """
<div style="background:linear-gradient(135deg,#1e3a5f 0%,#7c3aed 55%,#db2777 100%);
padding:1.2rem 1.5rem;border-radius:12px;margin-bottom:1rem;">
<h2 style="color:white;margin:0;">🚀 NIFTY 500 Breakout Scanner</h2>
<p style="color:#e2e8f0;margin:0.4rem 0 0;">
Donchian breakouts with volume confirmation on <strong>1 Hour</strong>, <strong>1 Day</strong>,
and <strong>1 Week</strong> timeframes — plus <strong>Virgin CPR</strong> screening.
</p></div>
""",
    unsafe_allow_html=True,
)

_render_disclaimer_banner()

universe = load_universe_symbols()

with st.sidebar:
    st.header("Universe")
    universe_choice = st.selectbox(
        "Symbol universe",
        list(UNIVERSE_CHOICES),
        index=list(UNIVERSE_CHOICES).index(UNIVERSE_NIFTY500),
        help="Applies to both Breakout and CPR scanners.",
    )
    max_symbols = st.slider(
        "Max symbols (NIFTY 500 only)",
        10,
        len(universe),
        len(universe),
        10,
        disabled=universe_choice != UNIVERSE_NIFTY500,
        help="Evenly sample across NIFTY 500 when less than full index.",
    )
    if universe_choice == UNIVERSE_FNO:
        if "fno_symbols" not in st.session_state:
            st.session_state.fno_symbols = fno_symbol_set()
        fno_count = len(st.session_state.fno_symbols)
        if st.button("Refresh F&O list from NSE", use_container_width=True):
            st.session_state.fno_symbols = fno_symbol_set(refresh=True)
            st.rerun()
        st.caption(f"**{fno_count}** F&O equity symbols (indices excluded).")
    elif universe_choice == UNIVERSE_NIFTY500 and max_symbols < len(universe):
        st.caption(
            f"Scanning **{max_symbols}** of **{len(universe)}** NIFTY 500 symbols "
            "(evenly spaced across the index)."
        )

    scan_symbols, universe_sample, universe_total = resolve_universe_symbols(
        universe_choice,
        universe,
        max_symbols=max_symbols if universe_choice == UNIVERSE_NIFTY500 else None,
    )
    st.metric("Symbols to scan", len(scan_symbols))

    st.divider()
    st.header("Breakout Scan Settings")
    breakout_mode_label = st.selectbox(
        "Breakout mode",
        ["Standard", "Strict (ATR)"],
        index=0,
        help=(
            "Standard: Donchian + volume + strong close. "
            "Strict: adds true range > ATR multiplier × ATR(14); default 1.5× volume on 1D."
        ),
    )
    breakout_mode = "strict" if breakout_mode_label == "Strict (ATR)" else "standard"
    selected_tfs = st.multiselect(
        "Timeframes",
        options=list(TIMEFRAME_ORDER),
        default=["1H", "1D", "1W"],
        format_func=lambda k: TIMEFRAMES[k].label,
    )
    selected_tfs = sort_timeframes(selected_tfs)
    direction = st.selectbox("Direction", ["Both", "Bullish", "Bearish"], index=0)
    vol_default = STRICT_VOL_MULT if breakout_mode == "strict" else 1.25
    vol_mult = st.slider("Min volume ratio", 1.0, 3.0, vol_default, 0.05)
    lookback = st.slider("Donchian lookback (bars)", 5, 60, 20, 1)
    atr_mult = st.slider(
        "Min TR / ATR(14) ratio",
        0.8,
        2.0,
        STRICT_ATR_MULT,
        0.05,
        disabled=breakout_mode != "strict",
        help="Breakout bar true range must exceed this multiple of 14-bar ATR.",
    )
    only_52w = st.checkbox("52-week high breakouts only (1D/1W)", value=False)
    use_cache = st.checkbox("Use price cache", value=True)
    if breakout_mode == "strict":
        st.caption(
            "Strict: close > prior N-bar high/low · volume > threshold × 20-bar avg · "
            "true range > ATR mult × ATR(14) · strong close."
        )
    else:
        st.caption(
            "Standard: close > prior N-bar high/low + volume surge + strong close. "
            "Weekly bars from daily data (Fri close)."
        )

    _render_disclaimer_sidebar()

tab_breakout, tab_cpr = st.tabs(["Breakout Scanner", "CPR Scanner"])

with tab_breakout:
    render_breakout_tab(
        scan_symbols,
        universe_choice=universe_choice,
        universe_total=universe_total,
        universe_sample=universe_sample,
    )

with tab_cpr:
    render_cpr_tab(
        scan_symbols,
        universe_choice=universe_choice,
        universe_total=universe_total,
        universe_sample=universe_sample,
    )

_render_disclaimer_footer()
