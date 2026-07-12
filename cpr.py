"""Central Pivot Range (CPR) calculations and Virgin CPR detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

import numpy as np
import pandas as pd

from config import (
    NARROW_CPR_PCT,
    NARROW_PERCENTILE,
    WIDE_CPR_PCT,
    WIDE_PERCENTILE,
    WIDTH_HISTORY_DAYS,
)

Position = Literal["above", "below", "inside"]
WidthType = Literal["narrow", "normal", "wide"]
VirginType = Literal["V+W", "V+N", "V", "WIDE", "NARROW", "TOUCHED", "—"]


@dataclass(frozen=True)
class CPRLevels:
    """CPR levels computed from one session's OHLC."""

    pivot: float
    tc: float
    bc: float
    r1: float
    s1: float
    width: float
    width_pct: float
    source_date: date

    @property
    def cpr_high(self) -> float:
        return self.tc

    @property
    def cpr_low(self) -> float:
        return self.bc


@dataclass
class VirginCPRResult:
    """Scanner output for one symbol."""

    symbol: str
    status: str
    cpr_type: VirginType
    distance_pct: float
    trend: Position
    ltp: float
    virgin_level: float
    pivot: float
    tc: float
    bc: float
    width_pct: float
    width_percentile: float
    narrow_threshold_pct: float
    days_virgin: int
    source_date: date
    session_date: date
    is_virgin: bool
    width_class: WidthType
    ml_trend_confidence: Optional[float] = None


def compute_cpr(high: float, low: float, close: float, source_date: date) -> CPRLevels:
    """Standard CPR from previous session OHLC."""
    pivot = (high + low + close) / 3.0
    bc = (high + low) / 2.0
    tc = 2.0 * pivot - bc
    if tc < bc:
        tc, bc = bc, tc

    width = tc - bc
    width_pct = (width / pivot * 100.0) if pivot else 0.0
    r1 = 2.0 * pivot - low
    s1 = 2.0 * pivot - high

    return CPRLevels(
        pivot=pivot,
        tc=tc,
        bc=bc,
        r1=r1,
        s1=s1,
        width=width,
        width_pct=width_pct,
        source_date=source_date,
    )


def _scalar(row: pd.Series, col: str) -> float:
    val = row[col]
    if isinstance(val, pd.Series):
        val = val.iloc[0]
    return float(val)


def _to_date(value: object) -> date:
    if hasattr(value, "date"):
        return value.date()
    return pd.to_datetime(value).date()


def _drop_incomplete_weekly(weekly: pd.DataFrame) -> pd.DataFrame:
    """Drop the in-progress week (W-FRI label is Friday; skip if that week has not finished)."""
    if weekly.empty or len(weekly) < 2:
        return weekly
    today = date.today()
    last_end = _to_date(weekly.index[-1])
    if last_end > today:
        return weekly.iloc[:-1]
    return weekly


def _prepare_bars(daily: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Return OHLC bars for CPR scan: daily sessions or completed weekly bars."""
    if daily is None or daily.empty:
        return pd.DataFrame()

    if timeframe == "Weekly":
        weekly = resample_to_weekly(daily)
        return _drop_incomplete_weekly(weekly)

    df = daily.sort_index().copy()
    df.columns = [c.lower() for c in df.columns]
    today = date.today()
    # Drop any accidental future-dated rows from the feed.
    df = df[df.index.map(_to_date) <= today]
    return df.dropna(subset=["close"])


def build_cpr_width_history(
    bars: pd.DataFrame,
    *,
    timeframe: str = "Daily",
    max_sessions: int = WIDTH_HISTORY_DAYS,
) -> pd.Series:
    """CPR width % series — one value per session, from the prior bar's OHLC."""
    if bars is None or len(bars) < 3:
        return pd.Series(dtype=float)

    df = bars.sort_index().copy()
    df.columns = [c.lower() for c in df.columns]
    if max_sessions > 0:
        df = df.tail(max_sessions + 1)

    widths: list[float] = []
    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        src = _to_date(df.index[i - 1])
        lv = compute_cpr(_scalar(prev, "high"), _scalar(prev, "low"), _scalar(prev, "close"), src)
        widths.append(lv.width_pct)

    return pd.Series(widths, dtype=float)


def classify_width_fixed(width_pct: float) -> WidthType:
    if width_pct <= NARROW_CPR_PCT:
        return "narrow"
    if width_pct >= WIDE_CPR_PCT:
        return "wide"
    return "normal"


def classify_width_relative(
    width_pct: float,
    history: pd.Series,
    narrow_percentile: float = NARROW_PERCENTILE,
    wide_percentile: float = WIDE_PERCENTILE,
) -> tuple[WidthType, float, float]:
    """Classify CPR width vs instrument's own 1-year history."""
    clean = history.dropna()
    if len(clean) < 30:
        return classify_width_fixed(width_pct), 50.0, NARROW_CPR_PCT

    narrow_thr = float(np.percentile(clean, narrow_percentile))
    wide_thr = float(np.percentile(clean, wide_percentile))
    rank = float((clean < width_pct).mean() * 100.0)

    if width_pct <= narrow_thr:
        return "narrow", rank, narrow_thr
    if width_pct >= wide_thr:
        return "wide", rank, narrow_thr
    return "normal", rank, narrow_thr


def cpr_zone_touched(day_high: float, day_low: float, tc: float, bc: float) -> bool:
    """True if the session range overlaps the CPR zone [BC, TC]."""
    return day_high >= bc and day_low <= tc


def _signed_distance_pct(price: float, tc: float, bc: float) -> tuple[float, float, Position]:
    """Distance % to CPR zone and trend position."""
    if price > tc:
        level = tc
        dist = (price - level) / level * 100.0
        return dist, level, "above"
    if price < bc:
        level = bc
        dist = (price - level) / level * 100.0
        return dist, level, "below"

    mid = (tc + bc) / 2.0
    dist = (price - mid) / mid * 100.0
    return dist, mid, "inside"


def _build_type(is_virgin: bool, width_class: WidthType) -> VirginType:
    if is_virgin:
        if width_class == "wide":
            return "V+W"
        if width_class == "narrow":
            return "V+N"
        return "V"
    if width_class == "wide":
        return "WIDE"
    if width_class == "narrow":
        return "NARROW"
    return "TOUCHED"


def _days_virgin_since_formed(df: pd.DataFrame, cpr_index: int, tc: float, bc: float) -> int:
    """Sessions since CPR formed that have not touched the zone (including today)."""
    days = 0
    for j in range(cpr_index, len(df)):
        bar = df.iloc[j]
        if cpr_zone_touched(_scalar(bar, "high"), _scalar(bar, "low"), tc, bc):
            break
        days += 1
    return days


def resample_to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Resample daily OHLC to weekly bars ending Friday."""
    df = daily.copy()
    df.index = pd.to_datetime(df.index)
    df.columns = [c.lower() for c in df.columns]
    resampled = df.resample("W-FRI").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum" if "volume" in df.columns else "first",
        }
    ).dropna()
    return resampled


def scan_today_cpr(
    daily: pd.DataFrame,
    narrow_percentile: float = NARROW_PERCENTILE,
    wide_percentile: float = WIDE_PERCENTILE,
    timeframe: str = "Daily",
) -> Optional[VirginCPRResult]:
    """
    Scan CPR for the latest session.

    Daily: CPR from the previous trading day's OHLC applied to the latest daily bar.
    Weekly: CPR from the previous completed week's OHLC applied to the latest week.
    """
    if daily is None or len(daily) < 2:
        return None

    df = _prepare_bars(daily, timeframe)
    if len(df) < 2:
        return None

    df.columns = [c.lower() for c in df.columns]
    required = {"open", "high", "low", "close"}
    if not required.issubset(df.columns):
        return None

    from datetime import timedelta
    today = date.today()
    latest_bar_date = _to_date(df.index[-1])
    is_future_session = latest_bar_date < today

    if is_future_session:
        source_bar = df.iloc[-1]
        source_date = latest_bar_date
        if timeframe == "Weekly":
            session_date = source_date + timedelta(days=7)
        else:
            next_date = source_date + timedelta(days=1)
            while next_date.weekday() >= 5:
                next_date += timedelta(days=1)
            session_date = next_date
    else:
        # Only previous session (CPR reference) + latest session (today)
        df_scan = df.tail(2)
        if len(df_scan) < 2:
            return None
        source_bar = df_scan.iloc[-2]
        source_date = _to_date(df_scan.index[-2])
        session_date = _to_date(df_scan.index[-1])

    levels = compute_cpr(
        _scalar(source_bar, "high"),
        _scalar(source_bar, "low"),
        _scalar(source_bar, "close"),
        source_date,
    )

    width_class = classify_width_fixed(levels.width_pct)
    width_percentile = float("nan")
    narrow_thr = NARROW_CPR_PCT

    if is_future_session:
        ltp = _scalar(source_bar, "close")
        touched_today = False
        is_virgin = True
        days_virgin = 1
    else:
        session_bar = df_scan.iloc[-1]
        ltp = _scalar(session_bar, "close")
        touched_today = cpr_zone_touched(
            _scalar(session_bar, "high"), _scalar(session_bar, "low"), levels.tc, levels.bc
        )
        is_virgin = not touched_today
        days_virgin = 1 if is_virgin else 0

    dist, virgin_level, trend = _signed_distance_pct(ltp, levels.tc, levels.bc)

    return VirginCPRResult(
        symbol="",
        status=f"{virgin_level:.2f}",
        cpr_type=_build_type(is_virgin, width_class),
        distance_pct=round(dist, 2),
        trend=trend,
        ltp=round(ltp, 2),
        virgin_level=round(virgin_level, 2),
        pivot=round(levels.pivot, 2),
        tc=round(levels.tc, 2),
        bc=round(levels.bc, 2),
        width_pct=round(levels.width_pct, 3),
        width_percentile=round(width_percentile, 1) if width_percentile == width_percentile else 0.0,
        narrow_threshold_pct=round(narrow_thr, 3),
        days_virgin=days_virgin,
        source_date=source_date,
        session_date=session_date,
        is_virgin=is_virgin,
        width_class=width_class,
    )


def levels_for_chart(daily: pd.DataFrame, timeframe: str = "Daily") -> dict[str, float]:
    """CPR levels for chart overlay (from previous session/week)."""
    if daily is None or len(daily) < 2:
        return {}
    df = _prepare_bars(daily, timeframe)
    if len(df) < 2:
        return {}

    df.columns = [c.lower() for c in df.columns]
    source_bar = df.iloc[-2]
    src = _to_date(df.index[-2])
    lv = compute_cpr(
        _scalar(source_bar, "high"),
        _scalar(source_bar, "low"),
        _scalar(source_bar, "close"),
        src,
    )
    return {
        "CPR HIGH (TC)": lv.tc,
        "CPR TC": lv.tc,
        "CPR PIVOT": lv.pivot,
        "CPR BC": lv.bc,
        "CPR LOW (BC)": lv.bc,
        "R1": lv.r1,
        "S1": lv.s1,
    }
