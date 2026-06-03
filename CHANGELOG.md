# CHANGELOG

All changes to the trading bot are documented here.
Format: version — date — what changed and why.

---

## v1.1 — 2025

### 1. Demo API — Correct Endpoint
**File:** `bot/bybit_client.py`, `.env.example`

**What changed:** Bybit Demo Trading uses `api-demo.bybit.com`, not `api.bybit.com`.
The original code used `testnet=False` which points to the production endpoint.
Fixed by using `HTTP(demo=True, ...)` in pybit which correctly routes to the demo endpoint.

**New env var:** `BYBIT_DEMO=true` (default) in `.env`.
Set `BYBIT_DEMO=false` only for real money live trading.

---

### 2. Duplicate Entry Prevention
**File:** `bot/main.py` → `_process_symbol()`

**What changed:** Added check to skip a symbol if there is already an open position for it.
Previously the bot checked for pending (unfilled) orders but not open positions,
meaning it could try to open a second position on the same symbol.

---

### 3. Trade DB Persistence + Restart Reconciliation
**File:** `bot/main.py` → `_recover_open_trades()`, `bot/trade_tracker.py` → `get_open_trades()`

**What changed:** On bot startup, open trades in the SQLite DB are reconciled against
live Bybit positions. If a position closed while the bot was offline (stopped), the
closed PnL is fetched from Bybit and recorded in the DB automatically. If the position
is still open, the internal `_trade_ids` tracking map is restored so the bot can
continue monitoring it.

---

### 4. Guardian Mode — Monitor Positions When Paused
**File:** `bot/main.py` → `_monitor_loop()`

**What changed:** The position monitor loop now runs even when the bot is paused.
Previously it skipped monitoring entirely during pause. Now it continues to:
- Detect TP1 hits and move SL to breakeven
- Activate trailing stops
- Record position closes to DB

When the bot is fully stopped, Bybit's exchange handles SL/TP execution natively
(orders remain on Bybit regardless of our bot state). On next start, reconciliation
records any closes that happened offline (see item 3).

---

### 5. VPS Access
**File:** `.env.example`

**What changed:** Documented that `HOST=0.0.0.0` makes the dashboard accessible at
`http://YOUR_VPS_IP:PORT` from any device with internet access.
Port 8000 must be open on the VPS firewall (`ufw allow 8000`).

---

### 6. Position Size in $ Added to All Tables
**File:** `ui/index.html`

**What changed:** Added `Size $` column (position size before leverage) to:
- Dashboard open positions table
- Positions tab full table
- History tab trade table
- Recent trades section

This shows how much real capital was allocated per trade.

---

### 7. Table Horizontal Overflow Fix
**File:** `ui/index.html`

**What changed:** Tables with many columns were overflowing their containers.
Fixed by adding `overflow-x: auto` to `.section-body` and `min-width: 720px`
to all tables. Tables now scroll horizontally within their box instead of
breaking the layout.

---

### 8. Stats Tab — Full Performance Analysis
**Files:** `ui/index.html`, `api/routes/stats.py`, `bot/trade_tracker.py`

**What changed:** New "Stats" tab added to the dashboard with:
- **Direction cards** — Long vs Short WR%, PnL, trade count
- **Confidence Range WR chart** — Which score range performs best
- **Confidence Range PnL chart** — Avg PnL per confidence bucket
- **Time of Day WR chart** — Which UTC hours are most profitable
- **Long vs Short comparison chart** — Dual-axis WR% and Total PnL
- **PnL by Pair horizontal bar** — Top 12 pairs by total PnL
- **Confidence Range table** — Detailed breakdown with signal rating
- **Time of Day table** — Full hourly breakdown
- **Pair Detail table** — Symbol, trades, WR, avg confidence, PnL
- **Auto Recommendations** — Text insights generated from the data
  (raise threshold, blacklist weak pairs, enable session filter, etc.)

New API endpoint: `GET /api/stats/analysis`

New DB queries in TradeTracker:
- `get_confidence_stats()`
- `get_direction_stats()`
- `get_time_stats()`
- `get_pair_detail_stats()`
- `get_open_trades()` (for restart reconciliation)

---

### 9. Max 3 Positions — Verified Correct
**File:** `bot/main.py`, `bot/position_manager.py`

**No code change.** Confirmed the max 3 positions logic with max 2 same-direction
is implemented correctly as designed. Position replacement (worst loser replaced
by higher-confidence signal) is intact.

---

## v1.0 — Initial Release

- Bybit USDT perpetuals futures bot
- Top 10-20 pairs by 24H turnover scanner
- 6 indicators: EMA cross, MACD, Volume, RSI, ADX, Bollinger Bands
- Multi-timeframe: 15m primary, 1h + 4h confirmation
- Weighted confidence scoring (1-10), trade only at 7+
- Dynamic leverage: round(30 / projected_ATR_move%), cap 10x
- Position sizing: 10-14% of capital scaled by confidence
- Max 3 positions, max 2 same direction
- Limit entry with 5-min timeout → re-evaluate → market fallback
- TP1 at 1:1.5 RR (50% close) → SL to breakeven
- TP2 with trailing stop
- Loss streak: 3 losses → 3h pause; 2 post-resume losses → 24h pause
- Manual close → 1h cooldown on pair
- Auto-blacklist: 4 losses in last 5 trades → 24h blacklist
- Regime filter: ADX gate, ATR percentile range, session filter
- Funding rate modifier on confidence score
- FastAPI backend + vanilla HTML/JS dashboard
- SQLite trade history
- Web UI: Dashboard, Positions, History, Settings, Blacklist, Logs tabs
