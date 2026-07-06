"""Price loading for NIFTY 500 breakout scanner (1H / 1D / 1W)."""

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
    NIFTY500_URL,
    STOCKDNA_UNIVERSE,
    UNIVERSE_CACHE,
    YAHOO_TICKER_MAP,
    YFINANCE_SUFFIX,
    ensure_dirs,
)

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


def resample_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return daily
    weekly = daily.resample("W-FRI").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return weekly.dropna(subset=["close"])


def load_daily(symbol: str, days: int = LOOKBACK_DAYS, use_cache: bool = True) -> pd.DataFrame:
    sym = symbol.upper()
    path = CACHE_DAILY / f"{sym}.csv"
    min_rows = min(60, days // 3)

    if use_cache and path.is_file():
        try:
            df = _read_csv_cache(path)
            fresh = not df.empty and df.index[-1].date() >= date.today() - timedelta(days=3)
            if fresh and len(df) >= min_rows:
                return df
        except Exception:
            pass

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

    if use_cache and path.is_file():
        try:
            df = _read_csv_cache(path)
            fresh = not df.empty and df.index[-1].date() >= date.today() - timedelta(days=2)
            if fresh and len(df) >= min_rows:
                return df
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
    """Return OHLCV for the requested timeframe key: 1H, 1D, 1W."""
    tf = timeframe.upper()
    if tf == "1H":
        return load_hourly(symbol, use_cache=use_cache)
    daily = load_daily(symbol, days=days, use_cache=use_cache)
    if tf == "1W":
        return resample_weekly(daily)
    return daily
