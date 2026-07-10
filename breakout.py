"""Donchian-style breakout detection with volume confirmation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

import numpy as np
import pandas as pd

from config import (
    STRICT_ATR_MULT,
    STRICT_ATR_PERIOD,
    STRICT_VOL_MULT,
    TIMEFRAMES,
    TimeframeConfig,
)

BreakoutDirection = Literal["bullish", "bearish"]
BreakoutMode = Literal["standard", "strict"]


@dataclass
class BreakoutResult:
    symbol: str
    timeframe: str
    direction: BreakoutDirection
    close: float
    level: float
    breakout_pct: float
    volume: float
    avg_volume: float
    volume_ratio: float
    bar_high: float
    bar_low: float
    strong_close: bool
    lookback: int
    bar_time: date
    prior_high: float
    prior_low: float
    mode: str = "standard"
    is_52w_high: bool = False
    true_range: Optional[float] = None
    atr: Optional[float] = None
    tr_atr_ratio: Optional[float] = None


def _bar_date(idx) -> date:
    return idx.date() if hasattr(idx, "date") else idx


def _strong_close(row: pd.Series, direction: BreakoutDirection, pct: float) -> bool:
    rng = float(row["high"]) - float(row["low"])
    if rng <= 0:
        return True
    if direction == "bullish":
        return (float(row["close"]) - float(row["low"])) / rng >= pct
    return (float(row["high"]) - float(row["close"])) / rng >= pct


def _true_range_series(hist: pd.DataFrame) -> pd.Series:
    high = hist["high"].astype(float)
    low = hist["low"].astype(float)
    close = hist["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def _atr_at_index(hist: pd.DataFrame, idx: int, period: int) -> float:
    if idx < period:
        return float("nan")
    tr = _true_range_series(hist.iloc[: idx + 1])
    return float(tr.iloc[-period:].mean())


def detect_breakout(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    cfg: Optional[TimeframeConfig] = None,
    *,
    mode: BreakoutMode = "standard",
    vol_mult: Optional[float] = None,
    lookback: Optional[int] = None,
    atr_period: Optional[int] = None,
    atr_mult: Optional[float] = None,
    direction_filter: Optional[BreakoutDirection] = None,
) -> Optional[BreakoutResult]:
    """
    Detect breakout on the latest completed bar.

    Standard: Donchian break + volume surge + strong close.
    Strict: same + true_range > atr_mult × ATR(period); default vol 1.5× on 1D.
    """
    if df is None or df.empty:
        return None

    tf = timeframe.upper()
    cfg = cfg or TIMEFRAMES[tf]
    lb = lookback if lookback is not None else cfg.lookback
    atr_p = atr_period if atr_period is not None else cfg.atr_period
    atr_m = atr_mult if atr_mult is not None else cfg.atr_mult

    if mode == "strict":
        vm = vol_mult if vol_mult is not None else STRICT_VOL_MULT
        if atr_mult is None:
            atr_m = STRICT_ATR_MULT if tf != "1H" else cfg.atr_mult
        if atr_period is None:
            atr_p = STRICT_ATR_PERIOD
    else:
        vm = vol_mult if vol_mult is not None else cfg.vol_mult

    min_len = max(cfg.min_bars, lb + cfg.vol_lookback + 2, atr_p + lb + 2)
    if len(df) < min_len:
        return None

    hist = df.dropna(subset=["close", "high", "low"]).copy()
    if len(hist) < min_len:
        return None

    prior = hist.iloc[-(lb + 1) : -1]
    bar = hist.iloc[-1]
    bar_idx = len(hist) - 1
    resistance = float(prior["high"].max())
    support = float(prior["low"].min())

    vol_series = hist["volume"].astype(float) if "volume" in hist.columns else pd.Series(0.0, index=hist.index)
    avg_vol = float(vol_series.iloc[-(cfg.vol_lookback + 1) : -1].mean())
    vol = float(vol_series.iloc[-1]) if len(vol_series) else 0.0
    vol_ok = avg_vol <= 0 or vol >= vm * avg_vol

    bullish = float(bar["close"]) > resistance and vol_ok
    bearish = float(bar["close"]) < support and vol_ok

    direction: Optional[BreakoutDirection] = None
    level = resistance
    if bullish and (direction_filter in (None, "bullish")):
        direction = "bullish"
        level = resistance
    elif bearish and (direction_filter in (None, "bearish")):
        direction = "bearish"
        level = support
    else:
        return None

    strong = _strong_close(bar, direction, cfg.strong_close_pct)
    if not strong:
        return None

    tr_val: Optional[float] = None
    atr_val: Optional[float] = None
    tr_atr_ratio: Optional[float] = None

    if mode == "strict":
        tr_series = _true_range_series(hist)
        tr_val = float(tr_series.iloc[-1])
        atr_val = _atr_at_index(hist, bar_idx, atr_p)
        if not np.isfinite(atr_val) or atr_val <= 0:
            return None
        tr_atr_ratio = tr_val / atr_val
        if tr_val <= atr_m * atr_val:
            return None

    breakout_pct = (float(bar["close"]) - level) / level * 100 if level else 0.0
    vol_ratio = vol / avg_vol if avg_vol > 0 else float("nan")

    is_52w = False
    windows_52w = {"1D": 252, "1W": 52, "1M": 12}
    if tf in windows_52w:
        window = windows_52w[tf]
        if len(hist) > window:
            prior_high = float(hist["high"].iloc[-window - 1 : -1].max())
            is_52w = direction == "bullish" and float(bar["close"]) >= prior_high

    return BreakoutResult(
        symbol=symbol.upper(),
        timeframe=tf,
        direction=direction,
        close=float(bar["close"]),
        level=level,
        breakout_pct=breakout_pct,
        volume=vol,
        avg_volume=avg_vol,
        volume_ratio=float(vol_ratio),
        bar_high=float(bar["high"]),
        bar_low=float(bar["low"]),
        strong_close=strong,
        lookback=lb,
        bar_time=_bar_date(hist.index[-1]),
        prior_high=resistance,
        prior_low=support,
        mode=mode,
        is_52w_high=is_52w,
        true_range=tr_val,
        atr=atr_val,
        tr_atr_ratio=float(tr_atr_ratio) if tr_atr_ratio is not None else None,
    )


def result_to_row(result: BreakoutResult) -> dict:
    row = {
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "direction": result.direction,
        "mode": result.mode,
        "close": round(result.close, 2),
        "level": round(result.level, 2),
        "breakout_pct": round(result.breakout_pct, 2),
        "volume_ratio": round(result.volume_ratio, 2)
        if np.isfinite(result.volume_ratio)
        else None,
        "prior_high": round(result.prior_high, 2),
        "prior_low": round(result.prior_low, 2),
        "bar_time": result.bar_time,
        "lookback": result.lookback,
        "is_52w_high": result.is_52w_high,
        "strong_close": result.strong_close,
    }
    if result.true_range is not None:
        row["true_range"] = round(result.true_range, 2)
    if result.atr is not None:
        row["atr"] = round(result.atr, 2)
    if result.tr_atr_ratio is not None and np.isfinite(result.tr_atr_ratio):
        row["tr_atr_ratio"] = round(result.tr_atr_ratio, 2)
    return row
