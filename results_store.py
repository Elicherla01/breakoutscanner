"""Persist breakout scan results to local CSV."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from config import (
    CPR_SCAN_INFO_CSV,
    CPR_SCAN_META_JSON,
    CPR_SCAN_RESULTS_CSV,
    SCAN_INFO_CSV,
    SCAN_META_JSON,
    SCAN_RESULTS_CSV,
    ensure_dirs,
)

_BOOL_COLS = ("is_52w_high", "strong_close")
_DISPLAY_TZ = ZoneInfo("Asia/Kolkata")

_SCAN_INFO_COLUMNS = (
    "scanned_at",
    "scanned_at_display",
    "symbols_scanned",
    "universe_total",
    "universe_sample",
    "timeframes",
    "mode",
    "breakout_mode",
    "direction",
    "vol_mult",
    "lookback",
    "atr_mult",
    "only_52w",
    "max_symbols",
    "breakout_count",
)


def format_scanned_at(iso_value: str | datetime | None, *, short: bool = False) -> str:
    """Format scan timestamp for UI display (IST)."""
    if not iso_value:
        return "—"
    try:
        if isinstance(iso_value, datetime):
            dt = iso_value
        else:
            dt = datetime.fromisoformat(str(iso_value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_DISPLAY_TZ)
        else:
            dt = dt.astimezone(_DISPLAY_TZ)
        if short:
            return dt.strftime("%d %b, %I:%M %p")
        return dt.strftime("%d %b %Y, %I:%M %p IST")
    except (TypeError, ValueError):
        return str(iso_value)


def save_scan_results(df: pd.DataFrame, meta: dict[str, Any]) -> Path:
    """Write scan results, scan_info.csv, and metadata JSON to data_cache/."""
    ensure_dirs()
    scanned_at = datetime.now(_DISPLAY_TZ).replace(microsecond=0)
    scanned_iso = scanned_at.isoformat(timespec="seconds")
    scanned_display = format_scanned_at(scanned_at)

    out = df.copy()
    out["scanned_at"] = scanned_iso
    out.to_csv(SCAN_RESULTS_CSV, index=False)

    timeframes = meta.get("timeframes") or []
    if isinstance(timeframes, list):
        tf_str = ", ".join(timeframes)
    else:
        tf_str = str(timeframes)

    info_row = {
        "scanned_at": scanned_iso,
        "scanned_at_display": scanned_display,
        "symbols_scanned": meta.get("symbols", ""),
        "universe_total": meta.get("universe_total", ""),
        "universe_sample": meta.get("universe_sample", ""),
        "timeframes": tf_str,
        "mode": meta.get("mode", meta.get("breakout_mode", "")),
        "breakout_mode": meta.get("breakout_mode", ""),
        "direction": meta.get("direction", ""),
        "vol_mult": meta.get("vol_mult", ""),
        "lookback": meta.get("lookback", ""),
        "atr_mult": meta.get("atr_mult", ""),
        "only_52w": meta.get("only_52w", False),
        "max_symbols": meta.get("max_symbols", ""),
        "breakout_count": len(out),
    }
    pd.DataFrame([info_row], columns=list(_SCAN_INFO_COLUMNS)).to_csv(SCAN_INFO_CSV, index=False)

    payload = {
        **meta,
        "scanned_at": scanned_iso,
        "scanned_at_display": scanned_display,
        "saved_at": scanned_iso,
        "row_count": len(out),
    }
    SCAN_META_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return SCAN_RESULTS_CSV


def load_scan_info() -> dict[str, Any]:
    """Load last-scan metadata from scan_info.csv (falls back to JSON)."""
    if SCAN_INFO_CSV.is_file():
        try:
            info = pd.read_csv(SCAN_INFO_CSV).iloc[0].to_dict()
            for key in ("only_52w",):
                if key in info:
                    info[key] = _parse_bool(info[key])
            return {k: (None if pd.isna(v) else v) for k, v in info.items()}
        except Exception:
            pass

    if SCAN_META_JSON.is_file():
        try:
            meta = json.loads(SCAN_META_JSON.read_text(encoding="utf-8"))
            if meta.get("saved_at") and "scanned_at" not in meta:
                meta["scanned_at"] = meta["saved_at"]
            if meta.get("scanned_at") and "scanned_at_display" not in meta:
                meta["scanned_at_display"] = format_scanned_at(meta["scanned_at"])
            return meta
        except Exception:
            pass
    return {}


def load_scan_results() -> tuple[Optional[pd.DataFrame], dict[str, Any]]:
    """Load cached scan results if present."""
    if not SCAN_RESULTS_CSV.is_file():
        return None, {}

    try:
        df = pd.read_csv(SCAN_RESULTS_CSV)
        for col in _BOOL_COLS:
            if col in df.columns:
                df[col] = df[col].map(_parse_bool)
        if "bar_time" in df.columns:
            df["bar_time"] = pd.to_datetime(df["bar_time"], errors="coerce").dt.date
        meta = load_scan_info()
        if not meta and SCAN_META_JSON.is_file():
            meta = json.loads(SCAN_META_JSON.read_text(encoding="utf-8"))
        return df, meta
    except Exception:
        return None, {}


def cached_scan_available() -> bool:
    return SCAN_RESULTS_CSV.is_file()


_CPR_BOOL_COLS = ("is_virgin", "is_narrow")
_CPR_INFO_COLUMNS = (
    "scanned_at",
    "scanned_at_display",
    "symbols_scanned",
    "universe_total",
    "universe_sample",
    "timeframe",
    "narrow_percentile",
    "virgin_count",
    "result_count",
)


def save_cpr_results(df: pd.DataFrame, meta: dict[str, Any]) -> Path:
    """Write CPR scan results and metadata to data_cache/."""
    ensure_dirs()
    scanned_at = datetime.now(_DISPLAY_TZ).replace(microsecond=0)
    scanned_iso = scanned_at.isoformat(timespec="seconds")
    scanned_display = format_scanned_at(scanned_at)

    out = df.copy()
    out["scanned_at"] = scanned_iso
    out.to_csv(CPR_SCAN_RESULTS_CSV, index=False)

    info_row = {
        "scanned_at": scanned_iso,
        "scanned_at_display": scanned_display,
        "symbols_scanned": meta.get("symbols", ""),
        "universe_total": meta.get("universe_total", ""),
        "universe_sample": meta.get("universe_sample", ""),
        "timeframe": meta.get("timeframe", "Daily"),
        "narrow_percentile": meta.get("narrow_percentile", ""),
        "virgin_count": int(out["is_virgin"].sum()) if "is_virgin" in out.columns else 0,
        "result_count": len(out),
    }
    pd.DataFrame([info_row], columns=list(_CPR_INFO_COLUMNS)).to_csv(CPR_SCAN_INFO_CSV, index=False)

    payload = {
        **meta,
        "scanned_at": scanned_iso,
        "scanned_at_display": scanned_display,
        "saved_at": scanned_iso,
        "row_count": len(out),
    }
    CPR_SCAN_META_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return CPR_SCAN_RESULTS_CSV


def load_cpr_scan_info() -> dict[str, Any]:
    if CPR_SCAN_INFO_CSV.is_file():
        try:
            info = pd.read_csv(CPR_SCAN_INFO_CSV).iloc[0].to_dict()
            return {k: (None if pd.isna(v) else v) for k, v in info.items()}
        except Exception:
            pass
    if CPR_SCAN_META_JSON.is_file():
        try:
            return json.loads(CPR_SCAN_META_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def load_cpr_results() -> tuple[Optional[pd.DataFrame], dict[str, Any]]:
    if not CPR_SCAN_RESULTS_CSV.is_file():
        return None, {}
    try:
        df = pd.read_csv(CPR_SCAN_RESULTS_CSV)
        for col in _CPR_BOOL_COLS:
            if col in df.columns:
                df[col] = df[col].map(_parse_bool)
        for col in ("source_date", "session_date"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
        for col in ("distance_pct", "width_pct", "width_percentile", "ltp", "tc", "bc", "pivot"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "is_narrow" not in df.columns:
            df["is_narrow"] = False
        if "type" not in df.columns:
            df["type"] = "—"
        meta = load_cpr_scan_info()
        return df, meta
    except Exception:
        return None, {}


def cached_cpr_scan_available() -> bool:
    return CPR_SCAN_RESULTS_CSV.is_file()


def _parse_bool(val: object) -> bool:
    if isinstance(val, bool):
        return val
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    return str(val).strip().lower() in {"1", "true", "yes", "t"}
