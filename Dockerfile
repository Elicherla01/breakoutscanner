# ── Base image ──────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Keep Python output unbuffered so container logs appear in real-time
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# ── System deps (needed by some scipy/pandas wheels on slim) ─────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ────────────────────────────────────────────────────────
WORKDIR /app

# ── Install Python dependencies first (layer cached until requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application source ──────────────────────────────────────────────────
COPY . .

# ── Create the data cache directory (will be mounted as a volume) ────────────
RUN mkdir -p data_cache/prices_daily data_cache/prices_hourly

# ── Expose Streamlit default port ────────────────────────────────────────────
EXPOSE 8550

# ── Health-check so Docker Desktop shows the container as healthy ────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8550/_stcore/health')"

# ── Start the app ────────────────────────────────────────────────────────────
CMD ["streamlit", "run", "app.py", \
     "--server.port=8550", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
