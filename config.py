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
NIFTY50_URL = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
UNIVERSE_CACHE = DATA_DIR / "nifty500_symbols.csv"
NIFTY50_CACHE = DATA_DIR / "nifty50_symbols.csv"
FNO_CACHE = DATA_DIR / "fno_symbols.csv"
FNO_CACHE_SIBLING = ROOT_DIR.parent / "107-CPRScanner" / "data_cache" / "fno_symbols.csv"
NIFTY50_CACHE_SIBLING = ROOT_DIR.parent / "015-NIFTY" / "nifty50_stocks_latest.csv"

UNIVERSE_NIFTY50 = "NIFTY 50"
UNIVERSE_FNO = "F&O stocks"
UNIVERSE_NIFTY500 = "NIFTY 500"
UNIVERSE_CHOICES: tuple[str, ...] = (UNIVERSE_NIFTY50, UNIVERSE_FNO, UNIVERSE_NIFTY500)
SCAN_RESULTS_CSV = DATA_DIR / "scan_results.csv"
SCAN_INFO_CSV = DATA_DIR / "scan_info.csv"
SCAN_META_JSON = DATA_DIR / "scan_meta.json"
CPR_SCAN_RESULTS_CSV = DATA_DIR / "cpr_scan_results.csv"
CPR_SCAN_INFO_CSV = DATA_DIR / "cpr_scan_info.csv"
CPR_SCAN_META_JSON = DATA_DIR / "cpr_scan_meta.json"
CPR_TIMEFRAMES: tuple[str, ...] = ("Daily", "Weekly")


def cpr_scan_paths(timeframe: str) -> tuple[Path, Path, Path]:
    """Per-timeframe CPR cache paths: results CSV, info CSV, meta JSON."""
    slug = timeframe.strip().lower()
    return (
        DATA_DIR / f"cpr_scan_results_{slug}.csv",
        DATA_DIR / f"cpr_scan_info_{slug}.csv",
        DATA_DIR / f"cpr_scan_meta_{slug}.json",
    )

LOOKBACK_DAYS = 400

# CPR width — relative to each instrument's own 1-year history
WIDTH_HISTORY_DAYS = 365
NARROW_PERCENTILE = 5.0
WIDE_PERCENTILE = 97.0
NARROW_CPR_PCT = 0.35
WIDE_CPR_PCT = 0.60
NARROW_PERCENTILE_PRESETS = (3.0, 5.0, 7.0, 10.0, 15.0)
NARROW_PERCENTILE_MIN = 1.0
NARROW_PERCENTILE_MAX = 20.0

CPR_DEFAULT_SYMBOLS = [
    "NIFTY",
    "BANKNIFTY",
    "VIX",
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
]
HOURLY_PERIOD = "60d"
BATCH_SIZE = 25

YAHOO_TICKER_MAP = {
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "VIX": "^INDIAVIX",
    "INDIAVIX": "^INDIAVIX",
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
