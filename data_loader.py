"""Price loading for NIFTY 500 breakout scanner (1H / 1D / 1W / 1M)."""

from __future__ import annotations

import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

from config import (
    CACHE_DAILY,
    CACHE_HOURLY,
    CPR_CACHE,
    DEFAULT_WATCHLIST,
    HOURLY_PERIOD,
    LOOKBACK_DAYS,
    MONTHLY_LOOKBACK_DAYS,
    NIFTY50_CACHE,
    NIFTY50_CACHE_SIBLING,
    NIFTY50_URL,
    NIFTY500_URL,
    STOCKDNA_UNIVERSE,
    UNIVERSE_CACHE,
    UNIVERSE_CHOICES,
    UNIVERSE_FNO,
    UNIVERSE_NIFTY10,
    UNIVERSE_NIFTY50,
    UNIVERSE_NIFTY500,
    YAHOO_TICKER_MAP,
    YFINANCE_SUFFIX,
    ensure_dirs,
)
from fno_loader import load_fno_symbols

_YF_LOCK = threading.Lock()


def yahoo_ticker(symbol: str) -> str:
    sym = symbol.upper().strip()
    return YAHOO_TICKER_MAP.get(sym, f"{sym}{YFINANCE_SUFFIX}")


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    df = df.loc[:, ~df.columns.duplicated()]
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    out = df[keep].copy()
    for col in ("open", "high", "low", "close", "volume"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out.index = pd.to_datetime(out.index).tz_localize(None)
    return out.sort_index().dropna(subset=["close"])


def load_universe_symbols() -> list[str]:
    """Load NIFTY 500 symbols from cache, sibling project, or NSE."""
    ensure_dirs()
    for path in (UNIVERSE_CACHE, STOCKDNA_UNIVERSE):
        if path.is_file():
            try:
                col = "symbol" if "symbol" in pd.read_csv(path, nrows=0).columns else None
                df = pd.read_csv(path)
                key = col or ("Symbol" if "Symbol" in df.columns else df.columns[0])
                symbols = df[key].dropna().astype(str).str.upper().str.strip().tolist()
                if symbols:
                    if path != UNIVERSE_CACHE:
                        pd.DataFrame({"symbol": symbols}).to_csv(UNIVERSE_CACHE, index=False)
                    return symbols
            except Exception:
                pass

    urls = [
        NIFTY500_URL,
        "https://www1.nseindia.com/content/indices/ind_nifty500list.csv",
        "https://raw.githubusercontent.com/Anmol-Verma/nifty500/master/ind_nifty500list.csv",
    ]
    for url in urls:
        try:
            df = pd.read_csv(url)
            col = "Symbol" if "Symbol" in df.columns else df.columns[0]
            symbols = df[col].dropna().astype(str).str.upper().str.strip().tolist()
            pd.DataFrame({"symbol": symbols}).to_csv(UNIVERSE_CACHE, index=False)
            return symbols
        except Exception:
            continue
    return DEFAULT_WATCHLIST.copy()


def _read_symbol_column(path: Path) -> list[str]:
    df = pd.read_csv(path)
    col = "symbol" if "symbol" in df.columns else ("Symbol" if "Symbol" in df.columns else df.columns[0])
    return df[col].dropna().astype(str).str.upper().str.strip().tolist()


def load_nifty50_symbols() -> list[str]:
    """Load NIFTY 50 constituents from cache, sibling project, or NSE."""
    ensure_dirs()
    for path in (NIFTY50_CACHE, NIFTY50_CACHE_SIBLING):
        if path.is_file():
            try:
                symbols = _read_symbol_column(path)
                if symbols:
                    if path != NIFTY50_CACHE:
                        pd.DataFrame({"symbol": symbols}).to_csv(NIFTY50_CACHE, index=False)
                    return sorted(set(symbols))
            except Exception:
                pass

    urls = [
        NIFTY50_URL,
        "https://www1.nseindia.com/content/indices/ind_nifty50list.csv",
    ]
    for url in urls:
        try:
            df = pd.read_csv(url)
            col = "Symbol" if "Symbol" in df.columns else df.columns[0]
            symbols = df[col].dropna().astype(str).str.upper().str.strip().tolist()
            if symbols:
                pd.DataFrame({"symbol": symbols}).to_csv(NIFTY50_CACHE, index=False)
                return sorted(set(symbols))
        except Exception:
            continue

    # Fallback: first 50 names from NIFTY 500 if NSE fetch fails
    nifty500 = load_universe_symbols()
    return select_scan_universe(nifty500, min(50, len(nifty500)))


def resolve_universe_symbols(
    choice: str,
    nifty500: list[str] | None = None,
    *,
    max_symbols: int | None = None,
) -> tuple[list[str], str, int]:
    """
    Resolve sidebar universe choice to a symbol list.

    Returns (symbols, sample_mode, universe_total) where sample_mode is
    'nifty50', 'fno', 'full', or 'even'.
    """
    choice = choice or UNIVERSE_NIFTY10
    if choice == UNIVERSE_NIFTY10:
        top_10 = ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "LT", "TCS", "ITC", "BHARTIARTL", "SBIN", "KOTAKBANK"]
        return top_10, "nifty10", 10

    if choice == UNIVERSE_NIFTY50:
        symbols = load_nifty50_symbols()
        return symbols, "nifty50", len(symbols)

    if choice == UNIVERSE_FNO:
        symbols = load_fno_symbols()
        return symbols, "fno", len(symbols)

    pool = nifty500 if nifty500 is not None else load_universe_symbols()
    total = len(pool)
    cap = max_symbols if max_symbols is not None else total
    symbols = select_scan_universe(pool, cap)
    mode = "full" if cap >= total else "even"
    return symbols, mode, total


def select_scan_universe(symbols: list[str], max_symbols: int) -> list[str]:
    """
    Choose symbols for a scan. When max_symbols < universe size, pick evenly
    across the sorted list so partial scans are not biased to NSE file order
    (which clusters many A/B names at the top).
    """
    unique = sorted({s.upper().strip() for s in symbols if s and str(s).strip()})
    n = len(unique)
    if n == 0:
        return []
    if max_symbols >= n:
        return unique
    step = n / max_symbols
    return [unique[min(int(i * step), n - 1)] for i in range(max_symbols)]


def _read_csv_cache(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"], index_col="date")
    return _normalize_ohlcv(df)


def _sibling_daily_cache(symbol: str) -> pd.DataFrame:
    path = CPR_CACHE / f"{symbol.upper()}.csv"
    if path.is_file():
        try:
            return _read_csv_cache(path)
        except Exception:
            pass
    return pd.DataFrame()


def fetch_daily(symbol: str, days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    ticker = yahoo_ticker(symbol)
    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=int(days * 1.6))
    try:
        with _YF_LOCK:
            df = yf.download(
                ticker,
                start=start.isoformat(),
                end=end.isoformat(),
                interval="1d",
                progress=False,
                auto_adjust=True,
                threads=False,
            )
        return _normalize_ohlcv(df)
    except Exception:
        return pd.DataFrame()


def fetch_hourly(symbol: str, period: str = HOURLY_PERIOD) -> pd.DataFrame:
    ticker = yahoo_ticker(symbol)
    try:
        with _YF_LOCK:
            df = yf.download(
                ticker,
                period=period,
                interval="1h",
                progress=False,
                auto_adjust=True,
                threads=False,
            )
        out = _normalize_ohlcv(df)
        # Keep regular session bars only (drop zero-volume stale rows)
        if "volume" in out.columns:
            out = out[out["volume"].fillna(0) >= 0]
        return out
    except Exception:
        return pd.DataFrame()


def fetch_daily_range(symbol: str, start: date, end: date) -> pd.DataFrame:
    ticker = yahoo_ticker(symbol)
    try:
        with _YF_LOCK:
            df = yf.download(
                ticker,
                start=start.isoformat(),
                end=end.isoformat(),
                interval="1d",
                progress=False,
                auto_adjust=True,
                threads=False,
            )
        return _normalize_ohlcv(df)
    except Exception:
        return pd.DataFrame()


def fetch_hourly_range(symbol: str, start: date, end: date) -> pd.DataFrame:
    ticker = yahoo_ticker(symbol)
    try:
        with _YF_LOCK:
            df = yf.download(
                ticker,
                start=start.isoformat(),
                end=end.isoformat(),
                interval="1h",
                progress=False,
                auto_adjust=True,
                threads=False,
            )
        out = _normalize_ohlcv(df)
        if "volume" in out.columns:
            out = out[out["volume"].fillna(0) >= 0]
        return out
    except Exception:
        return pd.DataFrame()


_OHLCV_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


def resample_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return daily
    weekly = daily.resample("W-FRI").agg(_OHLCV_AGG)
    return weekly.dropna(subset=["close"])


def resample_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return daily
    monthly = daily.resample("ME").agg(_OHLCV_AGG)
    monthly = monthly.dropna(subset=["close"])
    # Extrapolate the in-progress month's volume to a full-month estimate so
    # the volume-surge filter is comparable with completed months (a month has
    # ~21 trading sessions; without this, a mid-month scan can never fire).
    if len(monthly) >= 2 and "volume" in monthly.columns:
        last_start = monthly.index[-1].to_period("M").start_time
        elapsed = int((daily.index >= last_start).sum())
        if 0 < elapsed < 18:
            monthly["volume"] = monthly["volume"].astype(float)
            vol_col = monthly.columns.get_loc("volume")
            monthly.iloc[-1, vol_col] = monthly.iloc[-1, vol_col] * 21.0 / elapsed
    return monthly


def load_daily(symbol: str, days: int = LOOKBACK_DAYS, use_cache: bool = True) -> pd.DataFrame:
    sym = symbol.upper()
    path = CACHE_DAILY / f"{sym}.csv"
    min_rows = min(60, days // 3) if days <= 500 else int(days * 0.45)

    df_cached = pd.DataFrame()
    if use_cache and path.is_file():
        try:
            df_cached = _read_csv_cache(path)
            fresh = not df_cached.empty and df_cached.index[-1].date() >= date.today() - timedelta(days=3)
            if fresh and len(df_cached) >= min_rows:
                return df_cached
        except Exception:
            pass

    # Incremental update logic
    if not df_cached.empty:
        try:
            last_cached_date = df_cached.index[-1].date()
            if last_cached_date < date.today():
                start_fetch = last_cached_date - timedelta(days=5) # 5 days overlap for safety
                end_fetch = date.today() + timedelta(days=1)
                df_new = fetch_daily_range(sym, start_fetch, end_fetch)
                if not df_new.empty:
                    df_merged = pd.concat([df_cached, df_new])
                    df_merged = df_merged[~df_merged.index.duplicated(keep="last")].sort_index()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    df_merged.to_csv(path)
                    return df_merged
        except Exception:
            pass

    # Sibling daily cache or full download fallback
    df = _sibling_daily_cache(sym)
    if df.empty or len(df) < min_rows:
        df = fetch_daily(sym, days=days)
    if not df.empty and use_cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path)
    return df


def load_hourly(symbol: str, use_cache: bool = True) -> pd.DataFrame:
    sym = symbol.upper()
    path = CACHE_HOURLY / f"{sym}.csv"
    min_rows = 40

    df_cached = pd.DataFrame()
    if use_cache and path.is_file():
        try:
            df_cached = _read_csv_cache(path)
            fresh = not df_cached.empty and df_cached.index[-1].date() >= date.today() - timedelta(days=2)
            if fresh and len(df_cached) >= min_rows:
                return df_cached
        except Exception:
            pass

    # Incremental update logic
    if not df_cached.empty:
        try:
            last_cached_date = df_cached.index[-1].date()
            if last_cached_date < date.today():
                start_fetch = last_cached_date - timedelta(days=3)
                end_fetch = date.today() + timedelta(days=1)
                df_new = fetch_hourly_range(sym, start_fetch, end_fetch)
                if not df_new.empty:
                    df_merged = pd.concat([df_cached, df_new])
                    df_merged = df_merged[~df_merged.index.duplicated(keep="last")].sort_index()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    df_merged.to_csv(path)
                    return df_merged
        except Exception:
            pass

    df = fetch_hourly(sym)
    if not df.empty and use_cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path)
    return df


def load_bars(
    symbol: str,
    timeframe: str,
    *,
    use_cache: bool = True,
    days: int = LOOKBACK_DAYS,
) -> pd.DataFrame:
    """Return OHLCV for the requested timeframe key: 1H, 1D, 1W, 1M."""
    tf = timeframe.upper()
    if tf == "1H":
        return load_hourly(symbol, use_cache=use_cache)
    if tf == "1M":
        daily = load_daily(symbol, days=max(days, MONTHLY_LOOKBACK_DAYS), use_cache=use_cache)
        return resample_monthly(daily)
    daily = load_daily(symbol, days=days, use_cache=use_cache)
    if tf == "1W":
        return resample_weekly(daily)
    return daily
