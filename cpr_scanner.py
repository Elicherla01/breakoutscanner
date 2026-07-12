"""Virgin CPR scanner engine."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import pandas as pd

from config import (
    CPR_LOOKBACK_DAYS,
    CPR_WEEKLY_LOOKBACK_DAYS,
    NARROW_CPR_PCT,
    NARROW_PERCENTILE,
    WIDE_CPR_PCT,
    WIDE_PERCENTILE,
)
from cpr import VirginCPRResult, scan_today_cpr
from data_loader import load_daily


def _cpr_load_days(timeframe: str) -> int:
    return CPR_WEEKLY_LOOKBACK_DAYS if timeframe == "Weekly" else CPR_LOOKBACK_DAYS


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
    days = _cpr_load_days(timeframe)
    df = daily if daily is not None else load_daily(sym, days=days, use_cache=use_cache)
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
    if timeframe == "Daily":
        try:
            from cpr_ml_engine import predict_cpr_trending_confidence
            result.ml_trend_confidence = predict_cpr_trending_confidence(sym, df)
        except Exception:
            pass
    return result


def _result_to_row(result: VirginCPRResult, *, timeframe: str = "Daily") -> dict:
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
        "timeframe": timeframe,
        "is_virgin": result.is_virgin,
        "is_narrow": result.width_class == "narrow",
        "ml_trend_confidence": result.ml_trend_confidence,
    }


def apply_narrow_percentile(
    df: pd.DataFrame,
    narrow_percentile: float,
    wide_percentile: float = WIDE_PERCENTILE,
) -> pd.DataFrame:
    """Re-tag narrow/wide using CPR width % thresholds (prev session CPR only)."""
    narrow_thr = float(narrow_percentile)
    wide_thr = float(wide_percentile)
    if df.empty:
        out = df.copy()
        if not out.empty and "is_narrow" not in out.columns:
            out["is_narrow"] = False
        return out

    out = df.copy()
    out["is_narrow"] = out["width_pct"] <= narrow_thr
    is_wide = out["width_pct"] >= wide_thr

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
    out["narrow_threshold_pct"] = narrow_thr
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
        return sym, load_daily(sym, days=_cpr_load_days(timeframe), use_cache=use_cache)

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
        rows.append(_result_to_row(result, timeframe=timeframe))

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    type_order = {"V+W": 0, "V+N": 1, "V": 2, "WIDE": 3, "NARROW": 4, "TOUCHED": 5, "—": 6}
    df["_sort"] = df["type"].map(type_order).fillna(9)
    df = df.sort_values(
        ["is_virgin", "is_narrow", "_sort", "width_pct"],
        ascending=[False, False, True, True],
    )
    df = df.drop(columns=["_sort"]).reset_index(drop=True)
    df["timeframe"] = timeframe
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
