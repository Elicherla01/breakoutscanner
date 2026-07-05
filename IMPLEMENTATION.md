# Implementation Procedure

Step-by-step guide to install, configure, run, and maintain the NIFTY 500 Breakout Scanner.

---

## 1. Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.10+ |
| pip | Latest |
| Internet | For NSE symbol list & Yahoo Finance prices |

Optional: `git` for cloning from [GitHub](https://github.com/Elicherla01/breakoutscanner).

---

## 2. Installation

### 2.1 Clone the repository

```bash
git clone https://github.com/Elicherla01/breakoutscanner.git
cd breakoutscanner
```

### 2.2 Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate         # Windows PowerShell
```

### 2.3 Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Expected packages: `pandas`, `numpy`, `yfinance`, `streamlit`, `plotly`.

### 2.4 Verify installation

```bash
python -m py_compile app.py breakout.py scanner.py data_loader.py
python run_scanner.py scan --max 5 -t 1D
```

You should see a small table of breakouts (or “No breakouts found”) without import errors.

---

## 3. Running the Streamlit app

### 3.1 Start the server

```bash
streamlit run app.py
# or
python run_scanner.py app --port 8501
```

![Streamlit dashboard — scan settings and breakout cards](docs/images/dashboard-screenshot.png)

### 3.2 First launch behaviour

1. App loads **cached scan** from `data_cache/scan_results.csv` if it exists.
2. If no cache, the main panel prompts you to run a scan.
3. Price data is downloaded on first scan and cached under `data_cache/prices_daily/` and `data_cache/prices_hourly/`.

### 3.3 Sidebar workflow

1. **Breakout mode** — `Standard` or `Strict (ATR)`
2. **Timeframes** — select 1H, 1D, 1W (tabs appear in that order)
3. **Direction** — Both / Bullish / Bearish
4. **Min volume ratio** — e.g. 1.25 (standard) or 1.5 (strict)
5. **Donchian lookback** — default 20 bars
6. **Max symbols to scan** — use **500** for full NIFTY 500 coverage
7. Click **Force Refresh Scan** to download prices, scan, and save CSV

### 3.4 Results views

- **Tabs:** All → 1 Hour → 1 Day → 1 Week
- **Cards / Table** toggle per tab
- **Chart symbol** dropdown + candlestick chart below cards
- **Download CSV** per tab

---

## 4. Scan cache (local persistence)

After each successful force refresh:

| File | Contents |
|------|----------|
| `data_cache/scan_results.csv` | Breakout rows |
| `data_cache/scan_meta.json` | Scan parameters + `saved_at` timestamp |

**Normal reload:** App reads cache only — no network scan.

**Force refresh:** Re-runs scan and overwrites both files.

To clear cache manually:

```bash
rm -f data_cache/scan_results.csv data_cache/scan_meta.json
```

---

## 5. CLI automation

### 5.1 Basic scan

```bash
python run_scanner.py scan --max 500 --mode strict -t 1H -t 1D -t 1W
```

### 5.2 Useful flags

```bash
python run_scanner.py scan \
  --max 500 \
  --mode strict \
  --vol-mult 1.5 \
  --lookback 20 \
  --atr-mult 1.2 \
  --direction bullish \
  --only-52w \
  --csv output/breakouts_$(date +%Y%m%d).csv
```

CLI scans also update `data_cache/scan_results.csv` so the Streamlit app picks them up.

### 5.3 Cron example (daily EOD scan)

```cron
30 16 * * 1-5 cd /path/to/breakoutscanner && .venv/bin/python run_scanner.py scan --max 500 --mode strict -t 1D -t 1W >> logs/scan.log 2>&1
```

Adjust time for IST market close + data availability on Yahoo Finance.

---

## 6. Module reference

### `data_loader.py`

- `load_universe_symbols()` — NIFTY 500 from NSE CSV (fallback mirrors)
- `load_bars(symbol, timeframe)` — OHLCV for 1H / 1D / 1W
- Thread-safe yfinance downloads via lock

### `breakout.py`

- `detect_breakout(df, symbol, timeframe, mode=...)` — single-symbol detection
- Returns `BreakoutResult` dataclass or `None`

### `scanner.py`

- `scan_universe(symbols, timeframes, ...)` — parallel price load + scan
- Results sorted: timeframe → direction → volume ratio → break %

### `results_store.py`

- `save_scan_results(df, meta)` / `load_scan_results()`

---

## 7. Customisation

### Change default timeframe parameters

Edit `TIMEFRAMES` in `config.py`:

```python
"1D": TimeframeConfig(
    lookback=20,
    vol_lookback=20,
    vol_mult=1.25,
    atr_mult=1.2,
    ...
)
```

### Change strict defaults

```python
STRICT_VOL_MULT = 1.5
STRICT_ATR_MULT = 1.2
STRICT_ATR_PERIOD = 14
```

---

## 8. Deployment options

### Local only (default)

`streamlit run app.py` on your machine.

### LAN access

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

### Streamlit Community Cloud

1. Push repo to GitHub (this repository).
2. Go to [share.streamlit.io](https://share.streamlit.io).
3. Connect `Elicherla01/breakoutscanner`, main branch, `app.py`.
4. Add `requirements.txt` — auto-detected.

Note: Cloud deploy will re-download prices each session; local `data_cache/` is not persisted on free tier unless you add external storage.

---

## 9. Troubleshooting

| Issue | Fix |
|-------|-----|
| All symbols start with “A” | Increase **Max symbols** to 500; NSE list order clusters A-names in first 100 |
| No 1H breakouts | Hourly data limited to ~60 days on yfinance; strict filters reduce hits |
| Slow first scan | Normal — 500 symbols × 3 timeframes; subsequent runs use cache |
| Stale results | Click **Force Refresh Scan** |
| `yfinance` empty data | Check symbol spelling; retry later; verify `.NS` suffix |
| Duplicate Streamlit widget ID | Ensure unique `key=` on widgets (fixed in card/chart views) |

---

## 10. Open-source checklist

- [x] Source code in repository root
- [x] `requirements.txt` pinned loosely (`>=`)
- [x] `README.md` + `IMPLEMENTATION.md`
- [x] `.gitignore` excludes `data_cache/` and secrets
- [x] MIT `LICENSE`
- [ ] GitHub repo: [Elicherla01/breakoutscanner](https://github.com/Elicherla01/breakoutscanner)

---

## 11. Contributing

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/my-change`
3. Commit with a clear message.
4. Open a pull request against `main`.

Issues and feature requests welcome on GitHub.
