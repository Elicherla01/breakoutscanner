"""NIFTY 500 multi-timeframe breakout scanner — Streamlit UI."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from config import STRICT_ATR_MULT, STRICT_VOL_MULT, TIMEFRAMES, TIMEFRAME_ORDER, sort_timeframes, ensure_dirs
from data_loader import load_bars, load_universe_symbols, select_scan_universe
from results_store import (
    cached_scan_available,
    format_scanned_at,
    load_scan_results,
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
</style>
""",
    unsafe_allow_html=True,
)

_DIR_STYLE = {
    "bullish": ("🟢 Bullish", "#16a34a"),
    "bearish": ("🔴 Bearish", "#dc2626"),
}

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
    sample = meta.get("universe_sample", "")
    total = meta.get("universe_total")
    if sample == "even" and total:
        universe_txt = f"{n_sym} of {total} symbols (even sample)"
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


ensure_dirs()

st.markdown(
    """
<div style="background:linear-gradient(135deg,#1e3a5f 0%,#7c3aed 55%,#db2777 100%);
padding:1.2rem 1.5rem;border-radius:12px;margin-bottom:1rem;">
<h2 style="color:white;margin:0;">🚀 NIFTY 500 Breakout Scanner</h2>
<p style="color:#e2e8f0;margin:0.4rem 0 0;">
Donchian breakouts with volume confirmation on <strong>1 Hour</strong>, <strong>1 Day</strong>,
and <strong>1 Week</strong> timeframes.
</p></div>
""",
    unsafe_allow_html=True,
)

_render_disclaimer_banner()

universe = load_universe_symbols()

with st.sidebar:
    st.header("Scan Settings")
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
    max_symbols = st.slider(
        "Max symbols to scan",
        10,
        len(universe),
        len(universe),
        10,
        help="Use 500 for full NIFTY 500. Smaller values sample evenly across the index (A–Z).",
    )
    if max_symbols < len(universe):
        st.caption(
            f"Scanning **{max_symbols}** of **{len(universe)}** symbols "
            "(evenly spaced across the index — not just A/B names)."
        )
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

symbols = select_scan_universe(universe, max_symbols)
dir_filter = None if direction == "Both" else direction.lower()

cached_df, cached_meta = load_scan_results()

force_refresh = st.button("Force Refresh Scan", type="primary", help="Re-run scan and overwrite local CSV cache.")

if not force_refresh and cached_df is not None:
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
        "universe_total": len(universe),
        "universe_sample": "even" if max_symbols < len(universe) else "full",
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
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Breakouts", len(results))
        c2.metric("Bullish", bull)
        c3.metric("Bearish", bear)
        c4.metric("Symbols Scanned", n_sym)
        c5.metric("Last Scanned", scanned_label)
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

_render_disclaimer_footer()
