"""Configuration for NIFTY 500 multi-timeframe breakout scanner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data_cache"
CACHE_DAILY = DATA_DIR / "prices_daily"
CACHE_HOURLY = DATA_DIR / "prices_hourly"

# Optional sibling caches (107-CPRScanner / 105-stockdna)
CPR_CACHE = ROOT_DIR.parent / "107-CPRScanner" / "data_cache" / "prices"
STOCKDNA_UNIVERSE = ROOT_DIR.parent / "105-stockdna" / "data_cache" / "nifty500_symbols.csv"

YFINANCE_SUFFIX = ".NS"
NIFTY500_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
UNIVERSE_CACHE = DATA_DIR / "nifty500_symbols.csv"
SCAN_RESULTS_CSV = DATA_DIR / "scan_results.csv"
SCAN_INFO_CSV = DATA_DIR / "scan_info.csv"
SCAN_META_JSON = DATA_DIR / "scan_meta.json"

LOOKBACK_DAYS = 400
HOURLY_PERIOD = "60d"
BATCH_SIZE = 25

YAHOO_TICKER_MAP = {
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
}

DEFAULT_WATCHLIST = [
    "RELIANCE",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "TCS",
    "INFY",
    "BHARTIARTL",
    "ITC",
    "KOTAKBANK",
    "LT",
    "AXISBANK",
    "BAJFINANCE",
    "MARUTI",
    "TITAN",
    "HINDUNILVR",
    "ASIANPAINT",
    "SUNPHARMA",
    "WIPRO",
    "ULTRACEMCO",
    "NTPC",
]


@dataclass(frozen=True)
class TimeframeConfig:
    label: str
    lookback: int
    vol_lookback: int
    min_bars: int
    vol_mult: float = 1.25
    strong_close_pct: float = 0.60
    atr_period: int = 14
    atr_mult: float = 1.2


# Strict mode defaults (Donchian + 1.5× vol + TR > ATR expansion + strong close)
STRICT_VOL_MULT = 1.5
STRICT_ATR_MULT = 1.2
STRICT_ATR_PERIOD = 14

TIMEFRAMES: dict[str, TimeframeConfig] = {
    "1H": TimeframeConfig(
        label="1 Hour",
        lookback=20,
        vol_lookback=20,
        min_bars=80,
        vol_mult=1.20,
        strong_close_pct=0.55,
        atr_period=14,
        atr_mult=1.0,
    ),
    "1D": TimeframeConfig(
        label="1 Day",
        lookback=20,
        vol_lookback=20,
        min_bars=60,
        vol_mult=1.25,
        strong_close_pct=0.60,
        atr_period=14,
        atr_mult=1.2,
    ),
    "1W": TimeframeConfig(
        label="1 Week",
        lookback=10,
        vol_lookback=10,
        min_bars=30,
        vol_mult=1.15,
        strong_close_pct=0.55,
        atr_period=14,
        atr_mult=1.2,
    ),
}


# Canonical display / scan order
TIMEFRAME_ORDER: tuple[str, ...] = ("1H", "1D", "1W")


def sort_timeframes(timeframes: list[str] | tuple[str, ...]) -> list[str]:
    rank = {tf: i for i, tf in enumerate(TIMEFRAME_ORDER)}
    return sorted(
        [tf.upper() for tf in timeframes if tf.upper() in TIMEFRAMES],
        key=lambda tf: rank.get(tf, 99),
    )


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DAILY.mkdir(parents=True, exist_ok=True)
    CACHE_HOURLY.mkdir(parents=True, exist_ok=True)
