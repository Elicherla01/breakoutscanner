"""
Confluence scanner script to find:
1. Stocks with breakout in 1H, 1D, and 1W all together.
2. Stocks with narrow CPR in both Daily and Weekly all together.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
import pandas as pd
import numpy as np
import yfinance as yf

# Setup project import path
project_dir = "/Users/ravindraprasad/01-Elicherla/01/01-algo/01-main/projects/109-Breakout"
if project_dir not in sys.path:
    sys.path.append(project_dir)

from config import (
    UNIVERSE_NIFTY50, UNIVERSE_FNO, UNIVERSE_NIFTY500,
    NIFTY50_CACHE, FNO_CACHE, UNIVERSE_CACHE,
    TIMEFRAMES, NARROW_CPR_PCT
)
from data_loader import load_bars, load_daily
from breakout import detect_breakout
from cpr import compute_cpr, levels_for_chart
from cpr_scanner import scan_symbol as scan_cpr_symbol


def load_selected_symbols(universe_type: str = "fno") -> list[str]:
    """Loads symbols for the chosen universe."""
    if universe_type == "nifty50":
        path = NIFTY50_CACHE
    elif universe_type == "fno":
        path = FNO_CACHE
    else:
        path = UNIVERSE_CACHE
        
    if not path.is_file():
        # Fallback to default list if file doesn't exist
        from config import DEFAULT_WATCHLIST
        return DEFAULT_WATCHLIST
        
    df = pd.read_csv(path)
    return df["symbol"].astype(str).str.strip().str.upper().tolist()


def run_confluence_scan(symbols: list[str], use_cache: bool = True) -> tuple[list[dict], list[dict]]:
    """Runs breakout and CPR confluence scans."""
    breakout_confluences = []
    cpr_confluences = []
    
    total = len(symbols)
    print(f"Scanning {total} symbols...")
    
    for i, sym in enumerate(symbols):
        # Progress indication
        if (i + 1) % 25 == 0 or (i + 1) == total:
            print(f"  Processed {i + 1}/{total} symbols...")
            
        try:
            # ── 1. BREAKOUT SCAN (1H, 1D, 1W) ──
            # Load price bars
            df_1h = load_bars(sym, "1H", use_cache=use_cache)
            df_1d = load_bars(sym, "1D", use_cache=use_cache)
            df_1w = load_bars(sym, "1W", use_cache=use_cache)
            
            bo_1h = detect_breakout(df_1h, sym, "1H")
            bo_1d = detect_breakout(df_1d, sym, "1D")
            bo_1w = detect_breakout(df_1w, sym, "1W")
            
            # Check if breakout occurred on all 3 timeframes and in the SAME direction
            if bo_1h and bo_1d and bo_1w:
                if bo_1h.direction == bo_1d.direction == bo_1w.direction:
                    breakout_confluences.append({
                        "Symbol": sym,
                        "Direction": bo_1h.direction.upper(),
                        "Close (1D)": round(bo_1d.close, 2),
                        "Break Level (1D)": round(bo_1d.level, 2),
                        "Vol Ratio (1D)": round(bo_1d.volume_ratio, 2) if np.isfinite(bo_1d.volume_ratio) else None,
                        "Time": bo_1d.bar_time
                    })
            
            # ── 2. CPR SCAN (Daily, Weekly) ──
            # Calculate Daily CPR
            df_daily_cpr = load_daily(sym, days=14, use_cache=use_cache)
            df_weekly_cpr = load_daily(sym, days=28, use_cache=use_cache) # resampled weekly bars are handled in load_daily
            
            cpr_daily = scan_cpr_symbol(sym, df_daily_cpr, timeframe="Daily", use_cache=use_cache)
            cpr_weekly = scan_cpr_symbol(sym, df_weekly_cpr, timeframe="Weekly", use_cache=use_cache)
            
            if cpr_daily and cpr_weekly:
                # Standard narrow threshold is 0.35% width
                if cpr_daily.width_pct <= NARROW_CPR_PCT and cpr_weekly.width_pct <= NARROW_CPR_PCT:
                    cpr_confluences.append({
                        "Symbol": sym,
                        "Daily Width %": round(cpr_daily.width_pct, 3),
                        "Weekly Width %": round(cpr_weekly.width_pct, 3),
                        "Daily Status": cpr_daily.status,
                        "Weekly Status": cpr_weekly.status,
                        "LTP": round(cpr_daily.ltp, 2)
                    })
        except Exception as e:
            # Skip errors silently to keep output clean
            continue
            
    return breakout_confluences, cpr_confluences


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", "-u", choices=["nifty50", "fno", "nifty500"], default="fno")
    parser.add_argument("--no-cache", action="store_true", help="Bypass cache and download fresh data")
    args = parser.parse_args()
    
    symbols = load_selected_symbols(args.universe)
    print(f"Loaded {len(symbols)} symbols from universe: {args.universe.upper()}")
    
    bo_results, cpr_results = run_confluence_scan(symbols, use_cache=not args.no_cache)
    
    # Print Results
    print("\n" + "="*60)
    print("CONFLUENCE SCAN RESULTS")
    print("="*60)
    
    print(f"\n1. BREAKOUT CONFLUENCE (1H + 1D + 1W breakouts together):")
    if bo_results:
        df_bo = pd.DataFrame(bo_results)
        print(df_bo.to_string(index=False))
    else:
        print("  No symbols met the breakout confluence condition.")
        
    print(f"\n2. CPR CONFLUENCE (Narrow CPR in Daily and Weekly together):")
    if cpr_results:
        df_cpr = pd.DataFrame(cpr_results).sort_values("Daily Width %")
        print(df_cpr.to_string(index=False))
    else:
        print("  No symbols met the CPR confluence condition.")
    print("="*60)
