# AGENT BRIEFING — TradingBot

## WHAT THIS IS
A Python-based cryptocurrency futures trading bot for Bybit.
It scans top USDT perpetual pairs, scores them with technical indicators,
and opens long/short trades using a confidence-weighted system.
A FastAPI server serves both the REST API and a web dashboard UI.

## WHAT IT DOES
- Scans top 10-20 pairs by 24H USDT turnover on Bybit
- Analyzes using 6 indicators across 15m, 1h, 4h timeframes
- Generates a confidence score 1-10; only trades at 7+
- Places limit orders with 5-minute timeout, falls back to market
- Manages SL, TP1 (partial close), TP2 (trailing stop), breakeven
- Enforces max 3 positions, max 2 same-direction
- Pauses on loss streaks (3 losses → 3h pause; 2 post-resume → 24h pause)
- Web UI at http://localhost:8000

## WHAT IT DOES NOT DO
- It does NOT trade automatically on startup — user must click Start in UI
- It does NOT support spot trading — futures (linear perpetuals) only
- It does NOT support inverse contracts

---

## PREREQUISITES CHECKLIST
Before installing, verify all of these:

- [ ] Python 3.11 or higher: `python --version`
- [ ] pip available: `pip --version`
- [ ] Port 8000 free: `lsof -i :8000` (should return nothing)
- [ ] Internet access to api.bybit.com
- [ ] Bybit Demo Trading account with API key + secret

---

## INSTALL SEQUENCE (exact order)

### STEP 1 — Install Python dependencies
```
pip install -r requirements.txt
```
Expected: `Successfully installed X packages`
If fail: see docs/ERRORS.md → INSTALL_ERRORS

### STEP 2 — Configure environment
```
cp .env.example .env
```
Then edit `.env` and fill in:
- `BYBIT_API_KEY` = your Bybit demo API key
- `BYBIT_API_SECRET` = your Bybit demo API secret
- `BYBIT_TESTNET` = false (for demo accounts on production endpoint)

### STEP 3 — Initialize database and settings
```
python setup.py
```
Expected output must include:
- `[SETUP] Database initialized: data/trades.db`
- `[SETUP] Default settings written: data/settings.json`
- `[SETUP] Setup complete. Run: python run.py`

If any line says ERROR: see docs/ERRORS.md

### STEP 4 — Start the server
```
python run.py
```
Expected: `INFO: Uvicorn running on http://0.0.0.0:8000`

### STEP 5 — Verify
Open browser: http://localhost:8000
Expected: Dark dashboard loads with status "STOPPED"

---

## HOW TO START TRADING
1. Open http://localhost:8000
2. Go to Settings tab — verify API keys via Exchange Status button
3. Click **▶ Start** in the header
4. Bot status changes to RUNNING (green dot)
5. First cycle runs at the next 15-minute candle close

---

## FILE MAP (what each file does)
```
run.py                  Entry point — starts FastAPI server
setup.py                One-time DB + settings initialization (idempotent)
config.py               Default settings + load/save helpers
requirements.txt        Python dependencies

bot/main.py             Orchestrator, BotState, TradingBot, shared state
bot/bybit_client.py     Bybit API wrapper (pybit)
bot/scanner.py          Pair scanner (top N by 24H turnover)
bot/market_data.py      OHLCV fetcher → pandas DataFrame
bot/indicators.py       6 technical indicators with directional scoring
bot/regime_filter.py    ADX gate, ATR range filter, session filter
bot/funding_monitor.py  Funding rate tracking and score modifier
bot/scorer.py           Weighted confidence scoring engine
bot/risk_manager.py     Leverage, position size, SL/TP calculation
bot/order_manager.py    Place/cancel/manage orders with limit timeout
bot/position_manager.py Track positions, detect TP1/BE/trailing triggers
bot/trade_tracker.py    SQLite trade recording, per-pair stats, auto-blacklist

api/server.py           FastAPI app setup
api/routes/bot.py       /api/start /api/stop /api/status
api/routes/settings.py  /api/settings /api/blacklist
api/routes/positions.py /api/positions /api/positions/{sym}/close
api/routes/stats.py     /api/stats/* /api/logs

ui/index.html           Full single-file web dashboard

data/settings.json      User settings (created by setup.py)
data/trades.db          Trade history SQLite database
data/blacklist.json     Manual blacklist
.env                    API keys (NEVER commit this)
```

---

## DO NOT MODIFY
- `data/trades.db` — SQLite binary, never edit manually
- `bot/__init__.py`, `api/__init__.py`, `api/routes/__init__.py` — empty package files, required
- `.env` — never commit, never log contents

## SAFE TO MODIFY
- `data/settings.json` — can be edited manually (valid JSON only)
- `data/blacklist.json` — list of symbol strings

---

## HEALTH CHECKS (run after install)
See docs/HEALTH.md for full curl-based health check commands.

Quick check:
```
curl http://localhost:8000/api/status
```
Expected: JSON with `"status": "stopped"`

---

## IF SOMETHING BREAKS
See docs/ERRORS.md for a full error catalog with causes and fixes.
Most common issues:
- Missing .env → copy .env.example to .env and fill keys
- DB not found → run `python setup.py`
- Port in use → change PORT in .env
- pybit import error → `pip install pybit --upgrade`
- pandas_ta error → `pip install pandas_ta==0.3.14b0`
