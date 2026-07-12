"""Mean Reversion & EMA Alignment scanner logic.

Gate Chronology:
  Pre-condition  → EMAs fanned out (20 > 50 > 100 > 200)
  Location       → EMAs compress into a tight band during consolidation
  Event          → Price breaks above consolidation high (long) or below low (short)

Two setup types:
  Fresh        – first compression after a fresh fanned-out trend
  Continuation – smaller (e.g. 1H) compression after a higher-TF breakout
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# EMA periods used throughout
# ---------------------------------------------------------------------------
EMA_PERIODS: tuple[int, ...] = (20, 50, 100, 200)

SetupType = Literal["fresh", "continuation"]
Direction = Literal["long", "short"]
SetupStatus = Literal[
    "location",       # in compression, waiting for event
    "event_long",     # broke above consolidation high
    "event_short",    # broke below consolidation low
]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class MeanReversionResult:
    """Single-symbol scan result."""

    symbol: str
    timeframe: str
    direction: Direction
    setup_type: SetupType
    status: SetupStatus

    close: float
    ema20: float
    ema50: float
    ema100: float
    ema200: float

    ema_spread_pct: float        # (ema20 - ema200) / ema200 * 100
    compression_pct: float       # (max - min) / min * 100
    alignment_ok: bool           # True if 20>50>100>200 at check-bar
    bars_in_compression: int     # how many bars compression held

    consolidation_high: float
    consolidation_low: float

    session_date: date
    event_price: Optional[float] = None  # close on event bar


# ---------------------------------------------------------------------------
# EMA helpers
# ---------------------------------------------------------------------------

def compute_emas(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of *df* with columns ema20/50/100/200 appended."""
    out = df.copy()
    out.columns = [c.lower() for c in out.columns]
    for period in EMA_PERIODS:
        out[f"ema{period}"] = out["close"].ewm(span=period, adjust=False).mean()
    return out


def _ema_spread_pct(ema_fast: float, ema_slow: float) -> float:
    """Percentage spread between two EMAs (positive when fast > slow)."""
    if ema_slow == 0:
        return 0.0
    return (ema_fast - ema_slow) / ema_slow * 100.0


def _compression_pct(ema_values: np.ndarray) -> float:
    """Percentage band width of the EMA cluster."""
    mn, mx = float(np.min(ema_values)), float(np.max(ema_values))
    if mn == 0:
        return 0.0
    return (mx - mn) / mn * 100.0


def is_aligned_bullish(ema20: float, ema50: float, ema100: float, ema200: float) -> bool:
    """True when 20 > 50 > 100 > 200."""
    return ema20 > ema50 > ema100 > ema200


def is_aligned_bearish(ema20: float, ema50: float, ema100: float, ema200: float) -> bool:
    """True when 200 > 100 > 50 > 20."""
    return ema200 > ema100 > ema50 > ema20


# ---------------------------------------------------------------------------
# Pre-condition: detect if EMAs were ever fanned out
# ---------------------------------------------------------------------------

def detect_fanned_out(
    ema_df: pd.DataFrame,
    min_spread_pct: float = 5.0,
    lookback: int = 200,
) -> bool:
    """Check if EMAs were fanned out (20 significantly above 200) in the recent past.

    We look at the *lookback* bars and check whether the 20-EMA was ever at
    least *min_spread_pct* above the 200-EMA. This confirms the pre-condition
    that a prior uptrend existed before compression.
    """
    if len(ema_df) < 3:
        return False

    window = ema_df.tail(lookback) if len(ema_df) > lookback else ema_df
    if window.empty:
        return False

    spread = _ema_spread_pct_series(window)
    return bool((spread >= min_spread_pct).any())


def _ema_spread_pct_series(window: pd.DataFrame) -> pd.Series:
    """Series of (ema20 - ema200) / ema200 * 100 over *window*."""
    ema20 = window["ema20"].astype(float)
    ema200 = window["ema200"].astype(float)
    return (ema20 - ema200) / ema200 * 100.0


# ---------------------------------------------------------------------------
# Compression detection
# ---------------------------------------------------------------------------

def find_compression_zone(
    ema_df: pd.DataFrame,
    compression_threshold: float = 5.0,
    min_bars: int = 1,
) -> tuple[int, int, int] | None:
    """Find the contiguous compression zone at the tail of *ema_df*.

    Scans backwards from the second-to-last bar and finds how many consecutive
    bars have compression_pct <= *compression_threshold*.

    Returns (start_idx, end_idx, bar_count) or None if no compression.
    The end_idx is the last bar of compression (inclusive).
    """
    if len(ema_df) < 3:
        return None

    cols = ["ema20", "ema50", "ema100", "ema200"]
    n = len(ema_df)
    # scan from second-last bar backwards
    end = n - 2  # the event bar is the last bar; compression is before it
    start = end

    while start >= 0:
        row = ema_df.iloc[start]
        vals = np.array([float(row[c]) for c in cols])
        if _compression_pct(vals) > compression_threshold:
            break
        start -= 1

    start += 1  # first bar within compression
    bar_count = end - start + 1

    if bar_count < min_bars:
        return None

    return start, end, bar_count


def find_compression_zone_full(
    ema_df: pd.DataFrame,
    compression_threshold: float = 5.0,
    min_bars: int = 1,
) -> tuple[int, int, int] | None:
    """Find the contiguous compression zone including the latest bar.

    Used when the current bar is *still* in compression (Location status).
    Returns (start_idx, end_idx, bar_count) or None.
    """
    if len(ema_df) < 2:
        return None

    cols = ["ema20", "ema50", "ema100", "ema200"]
    n = len(ema_df)
    end = n - 1
    start = end

    while start >= 0:
        row = ema_df.iloc[start]
        vals = np.array([float(row[c]) for c in cols])
        if _compression_pct(vals) > compression_threshold:
            break
        start -= 1

    start += 1  # first bar within compression
    bar_count = end - start + 1

    if bar_count < min_bars:
        return None

    return start, end, bar_count


# ---------------------------------------------------------------------------
# Alignment check within compression
# ---------------------------------------------------------------------------

def alignment_in_compression(
    ema_df: pd.DataFrame,
    start: int,
    end: int,
) -> bool:
    """Check whether EMA alignment is visible in the recent compression bars.

    We check the last 5 bars of compression (up to and including the current
    bar if still compressed). If at least 3 of the last 5 bars show proper
    bullish or bearish alignment, we consider it a high-probability signal.
    """
    if end < start:
        return False

    cols = ["ema20", "ema50", "ema100", "ema200"]

    check_start = max(start, end - 4)
    aligned_count = 0
    total = 0
    for i in range(check_start, end + 1):
        row = ema_df.iloc[i]
        vals = [float(row[c]) for c in cols]
        if is_aligned_bullish(*vals) or is_aligned_bearish(*vals):
            aligned_count += 1
        total += 1

    # At least 3 of last 5 bars should be aligned
    return aligned_count >= min(3, total)


def detect_direction_in_compression(
    ema_df: pd.DataFrame,
    start: int,
    end: int,
) -> Optional[Direction]:
    """Return 'long' or 'short' based on EMA order at end of compression."""
    if end < start:
        return None
    last_row = ema_df.iloc[end]
    ema20 = float(last_row["ema20"])
    ema50 = float(last_row["ema50"])
    ema100 = float(last_row["ema100"])
    ema200 = float(last_row["ema200"])

    if is_aligned_bullish(ema20, ema50, ema100, ema200):
        return "long"
    if is_aligned_bearish(ema20, ema50, ema100, ema200):
        return "short"
    return None


# ---------------------------------------------------------------------------
# Consolidation high / low
# ---------------------------------------------------------------------------

def consolidation_range(
    df: pd.DataFrame,
    start: int,
    end: int,
) -> tuple[float, float]:
    """Highest high and lowest low across the compression zone."""
    zone = df.iloc[start : end + 1]
    return float(zone["high"].max()), float(zone["low"].min())


# ---------------------------------------------------------------------------
# Main scan function
# ---------------------------------------------------------------------------

def scan_mean_reversion(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    *,
    compression_threshold: float = 6.0,
    min_bars: int = 1,
    min_spread_pct: float = 5.0,
) -> Optional[MeanReversionResult]:
    """Full Gate analysis for one symbol.

    Steps:
      1. Compute EMAs
      2. Check pre-condition (fanned out in history)
      3. Find compression zone (Location)
      4. Check alignment within compression
      5. Detect event (break above/below consolidation range)
    """
    if df is None or df.empty:
        return None

    required = {"open", "high", "low", "close"}
    cols_lower = {c.lower() for c in df.columns}
    if not required.issubset(cols_lower):
        return None

    if len(df) < 250:  # need enough history for 200 EMA + lookback
        return None

    ema_df = compute_emas(df)
    ema_df = ema_df.dropna(subset=["ema200"])
    if len(ema_df) < 30:
        return None

    n = len(ema_df)
    last_bar = ema_df.iloc[-1]
    last_close = float(last_bar["close"])

    # ── Step 1: Pre-condition ──────────────────────────────────────────
    was_fanned = detect_fanned_out(ema_df, min_spread_pct=min_spread_pct)

    # ── Step 2: Find compression ───────────────────────────────────────
    # First check if we're CURRENTLY in compression (includes last bar)
    zone_full = find_compression_zone_full(ema_df, compression_threshold, min_bars)
    # Also check compression before last bar (for event detection)
    zone_before = find_compression_zone(ema_df, compression_threshold, min_bars)

    # ── Decide status ──────────────────────────────────────────────────
    cols = ["ema20", "ema50", "ema100", "ema200"]
    last_ema20 = float(last_bar["ema20"])
    last_ema200 = float(last_bar["ema200"])
    ema_spread = _ema_spread_pct(last_ema20, last_ema200)
    ema_vals = np.array([float(last_bar[c]) for c in cols])
    comp_pct = _compression_pct(ema_vals)

    # Case 1: Currently in compression → Location
    if zone_full is not None:
        start, end, bar_count = zone_full
        cons_high, cons_low = consolidation_range(ema_df, start, end)
        aligned = alignment_in_compression(ema_df, start, end)
        direction = detect_direction_in_compression(ema_df, start, end)
        if direction is None:
            direction = "long"
        setup_type: SetupType = "fresh" if was_fanned else "continuation"

        return MeanReversionResult(
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            setup_type=setup_type,
            status="location",
            close=round(last_close, 2),
            ema20=round(last_ema20, 2),
            ema50=round(float(last_bar["ema50"]), 2),
            ema100=round(float(last_bar["ema100"]), 2),
            ema200=round(last_ema200, 2),
            ema_spread_pct=round(ema_spread, 2),
            compression_pct=round(comp_pct, 2),
            alignment_ok=aligned,
            bars_in_compression=bar_count,
            consolidation_high=round(cons_high, 2),
            consolidation_low=round(cons_low, 2),
            session_date=_bar_date(ema_df.index[-1]),
            event_price=round(last_close, 2),
        )

    # Case 2: Compression existed before last bar, last bar broke out → Event
    if zone_before is not None:
        start, end, bar_count = zone_before
        cons_high, cons_low = consolidation_range(ema_df, start, end)
        aligned = alignment_in_compression(ema_df, start, end)
        direction = detect_direction_in_compression(ema_df, start, end)
        if direction is None:
            direction = "long"
        setup_type = "fresh" if was_fanned else "continuation"

        if last_close > cons_high:
            status: SetupStatus = "event_long"
        elif last_close < cons_low:
            status = "event_short"
        else:
            status = "location"

        return MeanReversionResult(
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            setup_type=setup_type,
            status=status,
            close=round(last_close, 2),
            ema20=round(last_ema20, 2),
            ema50=round(float(last_bar["ema50"]), 2),
            ema100=round(float(last_bar["ema100"]), 2),
            ema200=round(last_ema200, 2),
            ema_spread_pct=round(ema_spread, 2),
            compression_pct=round(comp_pct, 2),
            alignment_ok=aligned,
            bars_in_compression=bar_count,
            consolidation_high=round(cons_high, 2),
            consolidation_low=round(cons_low, 2),
            session_date=_bar_date(ema_df.index[-1]),
            event_price=round(last_close, 2),
        )

    return None


def _bar_date(idx) -> date:
    return idx.date() if hasattr(idx, "date") else idx


# ---------------------------------------------------------------------------
# Result → row dict (for DataFrame)
# ---------------------------------------------------------------------------

def result_to_row(result: MeanReversionResult) -> dict:
    return {
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "direction": result.direction,
        "setup_type": result.setup_type,
        "status": result.status,
        "close": result.close,
        "ema20": result.ema20,
        "ema50": result.ema50,
        "ema100": result.ema100,
        "ema200": result.ema200,
        "ema_spread_pct": result.ema_spread_pct,
        "compression_pct": result.compression_pct,
        "alignment_ok": result.alignment_ok,
        "bars_in_compression": result.bars_in_compression,
        "consolidation_high": result.consolidation_high,
        "consolidation_low": result.consolidation_low,
        "session_date": result.session_date,
        "event_price": result.event_price,
    }


# ---------------------------------------------------------------------------
# Chart helper: return EMA levels + compression zone for plotting
# ---------------------------------------------------------------------------

def levels_for_chart(
    df: pd.DataFrame,
    compression_threshold: float = 5.0,
) -> dict[str, object]:
    """Return EMA values and compression zone for chart overlay."""
    if df is None or len(df) < 250:
        return {}

    ema_df = compute_emas(df)
    ema_df = ema_df.dropna(subset=["ema200"])
    if ema_df.empty:
        return {}

    last = ema_df.iloc[-1]
    zone = find_compression_zone_full(ema_df, compression_threshold)

    result: dict[str, object] = {
        "ema20": float(last["ema20"]),
        "ema50": float(last["ema50"]),
        "ema100": float(last["ema100"]),
        "ema200": float(last["ema200"]),
    }

    if zone is not None:
        start, end, _ = zone
        ch, cl = consolidation_range(ema_df, start, end)
        result["consolidation_high"] = ch
        result["consolidation_low"] = cl

    return result
