"""
Machine Learning engine for Central Pivot Range (CPR) Scanner to predict trending vs choppy days.
"""

from __future__ import annotations

import os
import pickle
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import date, timedelta
from typing import Optional

from sklearn.ensemble import RandomForestClassifier

from config import DATA_DIR, DEFAULT_WATCHLIST
from data_loader import load_daily
from ml_engine import compute_rsi, compute_atr, compute_ema, _flatten_yfinance_cols, get_market_regime_classification

MODEL_PATH = DATA_DIR / "cpr_ml_model.pkl"


def compute_cpr_levels(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Calculate Pivot, BC, TC, and CPR width % from daily bars."""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    
    pivot = (high + low + close) / 3.0
    bc = (high + low) / 2.0
    tc = (pivot - bc) + pivot
    
    # CPR Width %
    width_pct = (tc - bc).abs() / pivot * 100.0
    return pivot, bc, tc, width_pct


def extract_cpr_features_and_labels(df: pd.DataFrame, nifty_df: Optional[pd.DataFrame] = None) -> tuple[pd.DataFrame, pd.Series]:
    """Extract features and target labels from daily stock bars for CPR ML model."""
    df = df.copy()
    if df.empty or len(df) < 30:
        return pd.DataFrame(), pd.Series()
        
    # 1. Compute CPR levels for the next day's session (using today's OHLC)
    pivot, bc, tc, width_pct = compute_cpr_levels(df)
    
    # 2. Compute stock technical indicators at close of today (prior to tomorrow's session)
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)
    
    rsi = compute_rsi(close, 14)
    vol_ratio = volume / volume.rolling(20).mean().fillna(1.0)
    atr = compute_atr(df, 14)
    
    # CPR Trend: Change in pivot compared to yesterday's pivot
    pivot_change = (pivot - pivot.shift(1)) / pivot.shift(1).replace(0, np.nan) * 100.0
    
    # Width relative to its rolling average
    width_vs_avg = width_pct / width_pct.rolling(10).mean().replace(0, np.nan)
    
    # 3. Target Label: Tomorrow's daily trading range vs today's ATR
    # Tomorrow's range = Tomorrow's High - Tomorrow's Low
    tomorrow_high = high.shift(-1)
    tomorrow_low = low.shift(-1)
    tomorrow_range = tomorrow_high - tomorrow_low
    
    # Label = 1 (Trending Day) if tomorrow's range >= 1.35 * today's ATR
    # Label = 0 (Rangebound Day) otherwise
    label = (tomorrow_range >= 1.35 * atr).astype(int)
    
    # Assemble raw features dataframe
    feats = pd.DataFrame({
        "cpr_width_pct": width_pct,
        "cpr_width_vs_avg": width_vs_avg.fillna(1.0),
        "prior_rsi": rsi,
        "prior_vol_ratio": vol_ratio.fillna(1.0),
        "cpr_trend": pivot_change.fillna(0.0),
    }, index=df.index)
    
    # Align Nifty features if provided
    if nifty_df is not None and not nifty_df.empty:
        nifty_aligned = nifty_df.reindex(df.index, method="ffill")
        feats["market_volatility"] = nifty_aligned["nifty_volatility"]
        feats["market_momentum"] = nifty_aligned["nifty_momentum"]
    else:
        feats["market_volatility"] = 0.15
        feats["market_momentum"] = 0.0
        
    # Drop rows where we don't have tomorrow's target label (the last row) and initial NaN windows
    valid_mask = label.notna() & feats["cpr_width_vs_avg"].notna() & feats["prior_rsi"].notna()
    # Also drop the last row because we don't know tomorrow's range yet
    if not valid_mask.empty:
        valid_mask.iloc[-1] = False
        
    return feats[valid_mask], label[valid_mask]


def train_cpr_confidence_model(use_cache: bool = True) -> Optional[RandomForestClassifier]:
    """Train the Central Pivot Range ML model on historical stock bars."""
    model_dir = MODEL_PATH.parent
    model_dir.mkdir(parents=True, exist_ok=True)
    
    if use_cache and MODEL_PATH.is_file():
        try:
            with open(MODEL_PATH, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
            
    print("Training CPR ML Model...")
    
    # Download Nifty data for market regime features
    nifty_df = pd.DataFrame()
    try:
        nifty = yf.download("^NSEI", period="2y", progress=False)
        if not nifty.empty:
            nifty = _flatten_yfinance_cols(nifty)
            n_close = nifty["close"].astype(float)
            n_log_ret = np.log(n_close / n_close.shift(1))
            
            nifty_df = pd.DataFrame({
                "nifty_volatility": n_log_ret.rolling(window=20).std() * np.sqrt(252),
                "nifty_momentum": (n_close - compute_ema(n_close, 50)) / compute_ema(n_close, 50)
            }, index=nifty.index).fillna(0.0)
    except Exception:
        pass
        
    X_list = []
    y_list = []
    
    # Gather training samples across watchlist stocks
    symbols = list(DEFAULT_WATCHLIST)[:25]  # Sample 25 stocks to balance train speed and accuracy
    for symbol in symbols:
        try:
            df = load_daily(symbol, days=350, use_cache=True)
            if df.empty or len(df) < 50:
                continue
            feats, target = extract_cpr_features_and_labels(df, nifty_df)
            if not feats.empty:
                X_list.append(feats)
                y_list.append(target)
        except Exception:
            continue
            
    if not X_list:
        print("Failed to train CPR ML model: no valid training samples found.")
        return None
        
    X = pd.concat(X_list, ignore_index=True)
    y = pd.concat(y_list, ignore_index=True)
    
    # Train Random Forest Classifier
    model = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42)
    model.fit(X, y)
    
    # Save the model
    try:
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f)
        print("CPR ML model trained and saved successfully!")
        return model
    except Exception as e:
        print(f"Failed to save CPR ML model: {e}")
        return None


def predict_cpr_trending_confidence(
    symbol: str,
    df: pd.DataFrame,
    nifty_regime: Optional[dict] = None
) -> Optional[float]:
    """
    Predict the probability (0.0 to 100.0) of the upcoming session being a Trending Day 
    for the given symbol based on its current technical state.
    """
    if df.empty or len(df) < 25:
        return None
        
    # Ensure model is trained/loaded
    model = train_cpr_confidence_model(use_cache=True)
    if model is None:
        return None
        
    try:
        # Calculate features at current last row (latest session close)
        pivot, bc, tc, width_pct = compute_cpr_levels(df)
        
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        volume = df["volume"].astype(float)
        
        rsi = compute_rsi(close, 14).iloc[-1]
        vol_ratio = (volume / volume.rolling(20).mean()).fillna(1.0).iloc[-1]
        
        # CPR Trend
        pivot_change = ((pivot - pivot.shift(1)) / pivot.shift(1).replace(0, np.nan) * 100.0).fillna(0.0).iloc[-1]
        
        # Width relative to its rolling average
        width_vs_avg = (width_pct / width_pct.rolling(10).mean()).fillna(1.0).iloc[-1]
        
        # Current market regime features
        market_vol = 0.15
        market_mom = 0.0
        
        if nifty_regime is None:
            nifty_regime = get_market_regime_classification()
            
        # Standard values representing the Nifty regime
        if nifty_regime and nifty_regime.get("name") == "Bullish Trend":
            market_vol = 0.11
            market_mom = 0.04
        elif nifty_regime and nifty_regime.get("name") == "Volatile Bearish":
            market_vol = 0.22
            market_mom = -0.05
        else: # Choppy/Neutral
            market_vol = 0.14
            market_mom = 0.00
            
        # Assemble feature row (matches columns of X)
        feat_names = ["cpr_width_pct", "cpr_width_vs_avg", "prior_rsi", "prior_vol_ratio", "cpr_trend", "market_volatility", "market_momentum"]
        feat_vals = [width_pct.iloc[-1], width_vs_avg, rsi, vol_ratio, pivot_change, market_vol, market_mom]
        
        X_pred = pd.DataFrame([feat_vals], columns=feat_names)
        
        # Predict probability of Trending Day (class 1)
        prob = model.predict_proba(X_pred)[0][1]
        return round(float(prob) * 100.0, 1)
    except Exception as e:
        # Silently fail and return None
        return None
