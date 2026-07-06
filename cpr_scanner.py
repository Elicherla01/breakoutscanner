"""Virgin CPR scanner engine."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import pandas as pd

from config import LOOKBACK_DAYS, NARROW_PERCENTILE, WIDE_PERCENTILE
from cpr import VirginCPRResult, scan_today_cpr
from data_loader import load_daily


def scan_symbol(
    symbol: str,
    daily: Optional[pd.DataFrame] = None,
    narrow_percentile: float = NARROW_PERCENTILE,
    wide_percentile: float = WIDE_PERCENTILE,
    timeframe: str = "Daily",
    *,
    use_cache: bool = True,
) -> Optional[VirginCPRResult]:
    """Scan one symbol for today's CPR."""
    sym = symbol.upper()
    df = daily if daily is not None else load_daily(sym, days=LOOKBACK_DAYS, use_cache=use_cache)
    if df is None or df.empty:
        return None
    result = scan_today_cpr(
        df,
        narrow_percentile=narrow_percentile,
        wide_percentile=wide_percentile,
        timeframe=timeframe,
    )
    if result is None:
        return None
    result.symbol = sym
    return result


def _result_to_row(result: VirginCPRResult) -> dict:
    return {
        "symbol": result.symbol,
        "status": result.status,
        "type": result.cpr_type,
        "distance_pct": result.distance_pct,
        "trend": result.trend,
        "ltp": result.ltp,
        "virgin_level": result.virgin_level,
        "pivot": result.pivot,
        "tc": result.tc,
        "bc": result.bc,
        "width_pct": result.width_pct,
        "width_percentile": result.width_percentile,
        "narrow_threshold_pct": result.narrow_threshold_pct,
        "days_virgin": result.days_virgin,
        "source_date": result.source_date,
        "session_date": result.session_date,
        "is_virgin": result.is_virgin,
        "is_narrow": result.width_class == "narrow",
    }


def apply_narrow_percentile(
    df: pd.DataFrame,
    narrow_percentile: float,
    wide_percentile: float = WIDE_PERCENTILE,
) -> pd.DataFrame:
    """Reclassify narrow/wide types when the user changes the percentile slider."""
    if df.empty or "width_percentile" not in df.columns:
        out = df.copy()
        if not out.empty and "is_narrow" not in out.columns:
            out["is_narrow"] = False
        return out

    out = df.copy()
    out["is_narrow"] = out["width_percentile"] <= narrow_percentile
    is_wide = out["width_percentile"] >= wide_percentile

    def _type(row: pd.Series) -> str:
        if row["is_virgin"]:
            if row["is_narrow"]:
                return "V+N"
            if is_wide.loc[row.name]:
                return "V+W"
            return "V"
        if row["is_narrow"]:
            return "NARROW"
        if is_wide.loc[row.name]:
            return "WIDE"
        return "TOUCHED"

    out["type"] = out.apply(_type, axis=1)
    out["narrow_percentile_used"] = narrow_percentile
    return out


def scan_universe(
    symbols: list[str],
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    use_cache: bool = True,
    narrow_percentile: float = NARROW_PERCENTILE,
    wide_percentile: float = WIDE_PERCENTILE,
    timeframe: str = "Daily",
) -> pd.DataFrame:
    """Scan all symbols for today's CPR and return sorted results."""
    rows: list[dict] = []
    total = len(symbols)

    def _load(sym: str) -> tuple[str, pd.DataFrame]:
        return sym, load_daily(sym, days=LOOKBACK_DAYS, use_cache=use_cache)

    data: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_load, s): s for s in symbols}
        done = 0
        for fut in as_completed(futures):
            sym, df = fut.result()
            data[sym.upper()] = df
            done += 1
            if progress_callback:
                progress_callback(done, total, sym)

    for sym in symbols:
        sym = sym.upper()
        result = scan_symbol(
            sym,
            data.get(sym),
            narrow_percentile=narrow_percentile,
            wide_percentile=wide_percentile,
            timeframe=timeframe,
            use_cache=use_cache,
        )
        if result is None:
            continue
        rows.append(_result_to_row(result))

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    type_order = {"V+W": 0, "V+N": 1, "V": 2, "WIDE": 3, "NARROW": 4, "TOUCHED": 5, "—": 6}
    df["_sort"] = df["type"].map(type_order).fillna(9)
    df = df.sort_values(
        ["is_virgin", "is_narrow", "_sort", "width_percentile"],
        ascending=[False, False, True, True],
    )
    df = df.drop(columns=["_sort"]).reset_index(drop=True)
    df["narrow_percentile_used"] = narrow_percentile
    return df


def filter_results(
    df: pd.DataFrame,
    virgin_only: bool = False,
    narrow_only: bool = False,
    types: Optional[list[str]] = None,
    trend: Optional[str] = None,
) -> pd.DataFrame:
    """Apply UI filters to scan results."""
    if df.empty:
        return df
    out = df.copy()
    if virgin_only:
        out = out[out["is_virgin"]]
    if narrow_only:
        out = out[out["is_narrow"]]
    if types:
        out = out[out["type"].isin(types)]
    if trend and trend != "All":
        out = out[out["trend"] == trend.lower()]
    return out.reset_index(drop=True)
