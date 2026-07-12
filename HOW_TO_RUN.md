# How to Run

## Prerequisites

```bash
pip install -r requirements.txt
```

## Start the App

```bash
streamlit run app.py --server.port=8550 --server.address=localhost --server.headless=true
```

Open http://localhost:8550 in your browser.

## What It Does

- **Breakout Scanner** — Donchian channel breakout signals
- **CPR Scanner** — Central Pivot Range analysis
- **Mean Reversion** — EMA compression & gate chronology (1H / 1D / 1W)
