"""Scan NIFTY 500 universe for multi-timeframe breakouts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import pandas as pd

from breakout import BreakoutDirection, BreakoutMode, detect_breakout, result_to_row
from config import TIMEFRAMES, sort_timeframes
from data_loader import load_bars


def scan_symbol(
    symbol: str,
    timeframe: str,
    bars: Optional[pd.DataFrame] = None,
    *,
    mode: BreakoutMode = "standard",
    use_cache: bool = True,
    vol_mult: Optional[float] = None,
    lookback: Optional[int] = None,
    atr_period: Optional[int] = None,
    atr_mult: Optional[float] = None,
    direction_filter: Optional[BreakoutDirection] = None,
) -> Optional[dict]:
    df = bars if bars is not None else load_bars(symbol, timeframe, use_cache=use_cache)
    result = detect_breakout(
        df,
        symbol,
        timeframe,
        mode=mode,
        vol_mult=vol_mult,
        lookback=lookback,
        atr_period=atr_period,
        atr_mult=atr_mult,
        direction_filter=direction_filter,
    )
    return result_to_row(result) if result else None


def scan_universe(
    symbols: list[str],
    timeframes: list[str],
    *,
    mode: BreakoutMode = "standard",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    use_cache: bool = True,
    vol_mult: Optional[float] = None,
    lookback: Optional[int] = None,
    atr_period: Optional[int] = None,
    atr_mult: Optional[float] = None,
    direction_filter: Optional[BreakoutDirection] = None,
    max_workers: int = 8,
) -> pd.DataFrame:
    """Scan symbols across one or more timeframes (1H, 1D, 1W, 1M)."""
    symbols = [s.upper() for s in symbols]
    timeframes = sort_timeframes(timeframes)
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
            row = scan_symbol(
                sym,
                tf,
                bar_cache.get((sym, tf)),
                mode=mode,
                use_cache=use_cache,
                vol_mult=vol_mult,
                lookback=lookback,
                atr_period=atr_period,
                atr_mult=atr_mult,
                direction_filter=direction_filter,
            )
            if row:
                rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    dir_order = {"bullish": 0, "bearish": 1}
    tf_order = {"1H": 0, "1D": 1, "1W": 2, "1M": 3}
    df["_dir"] = df["direction"].map(dir_order).fillna(9)
    df["_tf"] = df["timeframe"].map(tf_order).fillna(9)
    df = df.sort_values(
        ["_tf", "_dir", "volume_ratio", "breakout_pct"],
        ascending=[True, True, False, False],
    )
    return df.drop(columns=["_dir", "_tf"]).reset_index(drop=True)


def filter_results(
    df: pd.DataFrame,
    *,
    timeframes: Optional[list[str]] = None,
    directions: Optional[list[str]] = None,
    min_vol_ratio: float = 0.0,
    only_52w: bool = False,
) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if timeframes:
        out = out[out["timeframe"].isin([t.upper() for t in timeframes])]
    if directions:
        out = out[out["direction"].isin([d.lower() for d in directions])]
    if min_vol_ratio > 0 and "volume_ratio" in out.columns:
        out = out[out["volume_ratio"].fillna(0) >= min_vol_ratio]
    if only_52w and "is_52w_high" in out.columns:
        out = out[out["is_52w_high"]]
    return out.reset_index(drop=True)
