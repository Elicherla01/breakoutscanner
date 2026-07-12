"""
Machine Learning engine for Market Regime Classification and Breakout Confidence Scoring.
"""

from __future__ import annotations

import os
import pickle
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from typing import Literal, Optional

from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier

from config import DATA_DIR, DEFAULT_WATCHLIST
from breakout import detect_breakout

MODEL_PATH = DATA_DIR / "breakout_ml_model.pkl"
REGIME_MODEL_PATH = DATA_DIR / "market_regime_model.pkl"


def compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculates Relative Strength Index (RSI)."""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs)).fillna(50.0)


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculates Average True Range (ATR)."""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    
    return tr.rolling(window=period).mean().fillna(0.0)


def compute_ema(series: pd.Series, span: int = 20) -> pd.Series:
    """Calculates Exponential Moving Average (EMA)."""
    return series.ewm(span=span, adjust=False).mean()


def _flatten_yfinance_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Flattens MultiIndex columns from yfinance downloads and lowercases them."""
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]
    return df


def get_market_regime_classification(lookback_days: int = 365) -> dict:
    """
    Downloads Nifty 50 (^NSEI) daily data, runs KMeans clustering to identify 
    the current market regime, and returns details.
    """
    try:
        # Download Nifty index data
        nifty = yf.download("^NSEI", period="2y", progress=False)
        if nifty.empty:
            return {"name": "Unknown", "desc": "No market data available.", "color": "#9aa0a6"}
        
        nifty = _flatten_yfinance_cols(nifty)
        close = nifty["close"].astype(float)
        volume = nifty["volume"].astype(float)
        
        # Calculate features
        log_ret = np.log(close / close.shift(1))
        volatility = log_ret.rolling(window=20).std() * np.sqrt(252)
        nifty_ema = compute_ema(close, 50)
        momentum = (close - nifty_ema) / nifty_ema
        
        df_feats = pd.DataFrame({
            "volatility": volatility,
            "momentum": momentum
        }).dropna()
        
        # Fit KMeans clustering
        scaler = StandardScaler()
        X = scaler.fit_transform(df_feats)
        
        kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
        clusters = kmeans.fit_predict(X)
        df_feats["cluster"] = clusters
        
        # Profile clusters to name them
        profiles = df_feats.groupby("cluster").mean()
        
        # Sort profiles:
        # 1. Bullish: High positive momentum, low/moderate volatility
        # 2. Bearish: Negative momentum, high volatility
        # 3. Choppy: Near zero momentum, low volatility
        
        cluster_names = {}
        for c in profiles.index:
            mom = profiles.loc[c, "momentum"]
            vol = profiles.loc[c, "volatility"]
            
            if mom > 0.01:
                cluster_names[c] = ("Bullish Trend", "Market is strong and steady. Breakouts have high success rate.", "#3dd68c")
            elif mom < -0.01 or vol > profiles["volatility"].mean() * 1.1:
                cluster_names[c] = ("Volatile Bearish", "Market is weak and volatile. High risk of false breakouts.", "#ff6b6b")
            else:
                cluster_names[c] = ("Neutral/Choppy", "Market is rangebound and sideways. Breakout signals are noisy.", "#ffc107")
        
        # Check if we successfully mapped unique clusters. If duplicate names exist, fallback to rank sorting.
        names_used = [x[0] for x in cluster_names.values()]
        if len(set(names_used)) < 3:
            # Fallback based on simple momentum ordering
            sorted_by_mom = profiles.sort_values("momentum").index.tolist()
            cluster_names[sorted_by_mom[0]] = ("Volatile Bearish", "Market is weak and volatile. High risk of false breakouts.", "#ff6b6b")
            cluster_names[sorted_by_mom[1]] = ("Neutral/Choppy", "Market is rangebound and sideways. Breakout signals are noisy.", "#ffc107")
            cluster_names[sorted_by_mom[2]] = ("Bullish Trend", "Market is strong and steady. Breakouts have high success rate.", "#3dd68c")

        # Get latest day's cluster
        latest_feat = df_feats.iloc[-1]
        latest_cluster = int(latest_feat["cluster"])
        name, desc, color = cluster_names[latest_cluster]
        
        return {
            "name": name,
            "desc": desc,
            "color": color,
            "momentum": float(latest_feat["momentum"]),
            "volatility": float(latest_feat["volatility"])
        }
    except Exception as e:
        return {
            "name": "Unknown",
            "desc": f"Error classifying regime: {e}",
            "color": "#9aa0a6"
        }


def extract_historical_breakouts(
    symbol: str, 
    df: pd.DataFrame, 
    timeframe: str = "1D"
) -> pd.DataFrame:
    """
    Scans a stock's historical DataFrame to find historical breakout bars 
    and gathers features and target success labels.
    """
    if df.empty or len(df) < 60:
        return pd.DataFrame()
        
    df = df.copy()
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float) if "volume" in df.columns else pd.Series(1.0, index=df.index)
    
    # Calculate indicators
    df["RSI"] = compute_rsi(close, 14)
    df["ATR"] = compute_atr(df, 14)
    df["EMA20"] = compute_ema(close, 20)
    df["EMA_dist"] = (close - df["EMA20"]) / df["EMA20"]
    df["avg_volume"] = volume.rolling(window=20).mean()
    df["volume_ratio"] = volume / df["avg_volume"].replace(0, np.nan)
    
    # Prior 10-bar returns
    df["return_10d"] = close.pct_change(10)
    
    # True range / ATR ratio
    prev_close = close.shift(1)
    df["tr"] = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    df["tr_atr_ratio"] = df["tr"] / df["ATR"].replace(0, np.nan)
    
    records = []
    # Loop to find historical breakouts
    # We stop 15 bars before the end to ensure we have future bars to evaluate outcome
    for idx in range(30, len(df) - 15):
        # Slice prior window for Donchian calculation
        prior = df.iloc[idx - 20: idx]
        bar = df.iloc[idx]
        
        resistance = prior["high"].max()
        support = prior["low"].min()
        
        # Basic breakout checks
        bullish = bar["close"] > resistance and bar["volume_ratio"] >= 1.25
        bearish = bar["close"] < support and bar["volume_ratio"] >= 1.25
        
        if not (bullish or bearish):
            continue
            
        direction = "bullish" if bullish else "bearish"
        
        # Evaluate future outcome (success = reached 3% before falling 2.5% in next 10 bars)
        future_window = df.iloc[idx + 1: idx + 11]
        if future_window.empty:
            continue
            
        close_t = bar["close"]
        success = 0
        
        if direction == "bullish":
            for f_close in future_window["close"]:
                if f_close >= close_t * 1.03:
                    success = 1
                    break
                elif f_close <= close_t * 0.975:
                    success = 0
                    break
        else: # bearish
            for f_close in future_window["close"]:
                if f_close <= close_t * 0.97:
                    success = 1
                    break
                elif f_close >= close_t * 1.025:
                    success = 0
                    break
                    
        records.append({
            "rsi": bar["RSI"],
            "volume_ratio": bar["volume_ratio"],
            "ema_dist": bar["EMA_dist"],
            "tr_atr_ratio": bar["tr_atr_ratio"],
            "return_10d": bar["return_10d"],
            "target": success
        })
        
    return pd.DataFrame(records)


def train_confidence_model(use_cache: bool = True) -> RandomForestClassifier | None:
    """
    Gathers historical breakouts from watchlist symbols, trains a 
    RandomForest classifier, and serializes it to disk.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    if use_cache and MODEL_PATH.is_file():
        try:
            with open(MODEL_PATH, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass

    # Load bars for watchlist symbols to compile training data
    all_records = []
    for symbol in DEFAULT_WATCHLIST:
        try:
            # Load daily bars (1D)
            ticker_ns = f"{symbol}.NS"
            df = yf.download(ticker_ns, period="2y", progress=False)
            if df.empty:
                continue
            
            df = _flatten_yfinance_cols(df)
            recs = extract_historical_breakouts(symbol, df, "1D")
            if not recs.empty:
                all_records.append(recs)
        except Exception:
            continue
            
    if not all_records:
        return None
        
    df_train = pd.concat(all_records, ignore_index=True).dropna()
    if len(df_train) < 15:
        # Not enough samples to train a meaningful ML model
        return None
        
    # Split features and target
    feature_cols = ["rsi", "volume_ratio", "ema_dist", "tr_atr_ratio", "return_10d"]
    X = df_train[feature_cols]
    y = df_train["target"]
    
    # Train Random Forest Classifier
    clf = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
    clf.fit(X, y)
    
    # Cache model
    try:
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(clf, f)
    except Exception:
        pass
        
    return clf


def predict_confidence(
    row: dict,
    model: Optional[RandomForestClassifier] = None,
    bars_df: Optional[pd.DataFrame] = None
) -> Optional[float]:
    """
    Uses the trained model and current breakout metrics to output 
    the probability of success (0.0 to 1.0).
    """
    if model is None:
        if MODEL_PATH.is_file():
            try:
                with open(MODEL_PATH, "rb") as f:
                    model = pickle.load(f)
            except Exception:
                return None
        else:
            return None
            
    if bars_df is None or bars_df.empty or model is None:
        return None

    try:
        # Calculate current features from latest bar
        hist = _flatten_yfinance_cols(bars_df)
        close = hist["close"].astype(float)
        
        rsi_series = compute_rsi(close, 14)
        atr_series = compute_atr(hist, 14)
        ema_series = compute_ema(close, 20)
        
        rsi_val = float(rsi_series.iloc[-1])
        vol_ratio = float(row.get("volume_ratio", 1.0))
        ema_dist = float((close.iloc[-1] - ema_series.iloc[-1]) / ema_series.iloc[-1])
        
        tr_val = float(close.diff().abs().iloc[-1])  # approximation of true range for latest bar
        atr_val = float(atr_series.iloc[-1])
        tr_atr_ratio = tr_val / atr_val if atr_val > 0 else 1.0
        
        ret_10d = float(close.pct_change(10).iloc[-1])
        
        feat_df = pd.DataFrame([{
            "rsi": rsi_val,
            "volume_ratio": vol_ratio,
            "ema_dist": ema_dist,
            "tr_atr_ratio": tr_atr_ratio,
            "return_10d": ret_10d
        }])
        
        # Predict success probability
        probs = model.predict_proba(feat_df)[0]
        # Return probability of class 1 (success)
        return float(probs[1])
    except Exception:
        return None
