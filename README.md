# NIFTY 500 Breakout Scanner

A multi-timeframe stock breakout scanner for **NIFTY 500** constituents. Detects Donchian-style resistance/support breaks with volume confirmation on **1 Hour**, **1 Day**, **1 Week**, and **1 Month** bars.

Built with Python, [yfinance](https://github.com/ranaroussi/yfinance), and [Streamlit](https://streamlit.io/).

**Live app:** [breakoutscanner.streamlit.app](https://breakoutscanner.streamlit.app/) — try it in your browser (no install).

**Repository:** [github.com/Elicherla01/breakoutscanner](https://github.com/Elicherla01/breakoutscanner)

## Screenshot

Streamlit dashboard — sidebar scan settings, force-refresh cache, and card view of bullish/bearish breakouts across 1H / 1D / 1W / 1M.

![NIFTY 500 Breakout Scanner dashboard](docs/images/dashboard-screenshot.png)

---

## Features

- **Four timeframes:** 1H (yfinance hourly), 1D (daily), 1W (weekly resampled from daily), 1M (monthly resampled from ~6 years of daily)
- **Two detection modes:**
  - **Standard** — Donchian break + volume surge + strong close
  - **Strict (ATR)** — Standard rules + true range > ATR multiplier × ATR(14)
- **Bullish & bearish** breakouts
- **Card and table views** with candlestick charts
- **Local CSV cache** — scan results persist across app restarts; refresh only on **Force Refresh**
- **CLI** for headless scans and automation

---

## Quick start

### Try online (recommended)

Open the hosted app — configure scan settings in the sidebar and click **Force Refresh Scan**:

**👉 [https://breakoutscanner.streamlit.app/](https://breakoutscanner.streamlit.app/)**

### Run locally

```bash
git clone https://github.com/Elicherla01/breakoutscanner.git
cd breakoutscanner
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Open the URL shown in the terminal (default `http://localhost:8501`).

---

## Breakout logic

### Bullish

```
close > rolling_max(high, N).shift(1)
AND volume > vol_mult × SMA(volume, 20)
AND close in upper portion of bar (strong close)
```

### Bearish

```
close < rolling_min(low, N).shift(1)
AND volume > vol_mult × SMA(volume, 20)
AND close in lower portion of bar (strong close)
```

### Strict mode (additional filter)

```
true_range > atr_mult × ATR(14)
```

True range uses gaps: `max(H−L, |H−prev_close|, |L−prev_close|)`.

Default strict thresholds: **1.5×** volume, **1.2×** ATR (1.0× ATR on 1H).

---

## Project layout

```
breakoutscanner/
├── app.py              # Streamlit UI
├── breakout.py         # Breakout detection engine
├── config.py           # Timeframe settings & constants
├── data_loader.py      # NIFTY 500 universe + OHLCV fetch/cache
├── results_store.py    # Scan CSV persistence
├── scanner.py          # Parallel universe scan
├── run_scanner.py      # CLI entry point
├── requirements.txt
├── docs/
│   └── images/
│       └── dashboard-screenshot.png
├── README.md
├── DISCLAIMER.md
└── IMPLEMENTATION.md   # Detailed setup & operations guide
```

---

## CLI usage

```bash
# Launch UI
python run_scanner.py app

# Scan first 100 symbols, all timeframes, strict mode
python run_scanner.py scan --max 100 --mode strict -t 1H -t 1D -t 1W

# Export to custom path (also updates app cache)
python run_scanner.py scan --max 500 -t 1D --csv breakouts.csv
```

---

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| Lookback (N) | 20 bars | Donchian window |
| Volume mult | 1.25 (standard) / 1.5 (strict) | Min volume vs 20-bar avg |
| ATR mult | 1.2 | Strict mode TR/ATR threshold |
| Max symbols | 500 (UI default) | Full index; smaller values use even A–Z sample |

**Tip:** Keep **Max symbols to scan** at **500** for the full index. If you scan fewer, the app now samples **evenly across A–Z** (not just the first names in the NSE file).

---

## Data sources

- **Universe:** [NSE NIFTY 500 list](https://archives.nseindia.com/content/indices/ind_nifty500list.csv) (cached locally)
- **Prices:** Yahoo Finance (`.NS` suffix for NSE symbols)

Cached files are stored under `data_cache/` (gitignored).

---

## Disclaimer

> **Not financial advice.** See the full [DISCLAIMER.md](DISCLAIMER.md) before using this software.

This software is for **informational, educational, and research purposes only**. It does **not** constitute investment, trading, tax, or legal advice, and does not create an adviser–client relationship.

- **Risk of loss:** Trading securities involves substantial risk; you may lose some or all of your capital.  
- **No guarantees:** Signals are algorithmic outputs from historical data; past breakouts do not guarantee future results.  
- **Data limitations:** Prices from third-party sources (e.g. Yahoo Finance) may be delayed, incomplete, or inaccurate.  
- **Your responsibility:** Perform independent due diligence and consult a **SEBI-registered** or otherwise qualified financial adviser before trading.  
- **No liability:** Authors and contributors are not liable for losses arising from use of this tool.

By using this repository or application, you agree to the terms in [DISCLAIMER.md](DISCLAIMER.md).

---

## License

MIT License — see [LICENSE](LICENSE).

---

## Implementation guide

See **[IMPLEMENTATION.md](IMPLEMENTATION.md)** for step-by-step installation, configuration, deployment, and troubleshooting.
