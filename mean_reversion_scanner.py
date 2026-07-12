"""Mean Reversion scanner engine — scans NIFTY universe for EMA-compression setups."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import pandas as pd

from config import (
    MR_COMPRESSION_THRESHOLD,
    MR_MIN_BARS,
    MR_MIN_BARS_BY_TF,
    MR_MIN_SPREAD_PCT,
)
from data_loader import load_bars
from mean_reversion import MeanReversionResult, result_to_row, scan_mean_reversion


def _min_bars_for_tf(tf: str) -> int:
    """Return the minimum compression bars for a given timeframe."""
    return MR_MIN_BARS_BY_TF.get(tf.upper(), MR_MIN_BARS)


def scan_symbol(
    symbol: str,
    timeframe: str,
    bars: Optional[pd.DataFrame] = None,
    *,
    use_cache: bool = True,
    compression_threshold: float = MR_COMPRESSION_THRESHOLD,
    min_bars: Optional[int] = None,
    min_spread_pct: float = MR_MIN_SPREAD_PCT,
) -> Optional[MeanReversionResult]:
    """Scan one symbol for mean reversion setup."""
    sym = symbol.upper()
    tf = timeframe.upper()
    mb = min_bars if min_bars is not None else _min_bars_for_tf(tf)
    df = bars if bars is not None else load_bars(sym, tf, use_cache=use_cache)
    result = scan_mean_reversion(
        df,
        sym,
        tf,
        compression_threshold=compression_threshold,
        min_bars=mb,
        min_spread_pct=min_spread_pct,
    )
    return result


def scan_universe(
    symbols: list[str],
    timeframes: list[str],
    *,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    use_cache: bool = True,
    compression_threshold: float = MR_COMPRESSION_THRESHOLD,
    min_bars: Optional[int] = None,
    min_spread_pct: float = MR_MIN_SPREAD_PCT,
    max_workers: int = 8,
) -> pd.DataFrame:
    """Scan all symbols across one or more timeframes for mean reversion setups."""
    symbols = [s.upper() for s in symbols]
    timeframes = [tf.upper() for tf in timeframes]
    rows: list[dict] = []
    total = len(symbols) * len(timeframes)
    done = 0

    bar_cache: dict[tuple[str, str], pd.DataFrame] = {}

    def _load(sym: str, tf: str) -> tuple[str, str, pd.DataFrame]:
        return sym, tf, load_bars(sym, tf, use_cache=use_cache)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_load, sym, tf) for sym in symbols for tf in timeframes]
        for fut in as_completed(futures):
            sym, tf, df = fut.result()
            bar_cache[(sym, tf)] = df
            done += 1
            if progress_callback:
                progress_callback(done, total, f"{sym} ({tf})")

    for sym in symbols:
        for tf in timeframes:
            result = scan_symbol(
                sym,
                tf,
                bar_cache.get((sym, tf)),
                use_cache=use_cache,
                compression_threshold=compression_threshold,
                min_bars=min_bars,
                min_spread_pct=min_spread_pct,
            )
            if result is not None:
                rows.append(result_to_row(result))

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Sort: event_long first, then event_short, then location; within each, by ema_spread desc
    status_order = {"event_long": 0, "event_short": 1, "location": 2}
    direction_order = {"long": 0, "short": 1}
    tf_order = {"1H": 0, "1D": 1, "1W": 2}
    df["_status"] = df["status"].map(status_order).fillna(9)
    df["_dir"] = df["direction"].map(direction_order).fillna(9)
    df["_tf"] = df["timeframe"].map(tf_order).fillna(9)
    df = df.sort_values(
        ["_status", "_dir", "_tf", "ema_spread_pct"],
        ascending=[True, True, True, False],
    )
    df = df.drop(columns=["_status", "_dir", "_tf"]).reset_index(drop=True)
    return df


def filter_results(
    df: pd.DataFrame,
    *,
    directions: Optional[list[str]] = None,
    statuses: Optional[list[str]] = None,
    setup_types: Optional[list[str]] = None,
    timeframes: Optional[list[str]] = None,
    alignment_only: bool = False,
) -> pd.DataFrame:
    """Apply UI filters to scan results."""
    if df.empty:
        return df
    out = df.copy()
    if directions:
        out = out[out["direction"].isin([d.lower() for d in directions])]
    if statuses:
        out = out[out["status"].isin(statuses)]
    if setup_types:
        out = out[out["setup_type"].isin(setup_types)]
    if timeframes:
        out = out[out["timeframe"].isin([t.upper() for t in timeframes])]
    if alignment_only:
        out = out[out["alignment_ok"]]
    return out.reset_index(drop=True)
