# ARCHITECTURE.md — System Architecture

## Overview

```
python run.py
     │
     └── uvicorn starts FastAPI (api/server.py)
              │
              ├── Serves web UI at /  (ui/index.html)
              ├── Mounts API routes   (/api/*)
              │
              └── bot/main.py (imported by all API routes)
                       │
                       ├── BotState        (shared state)
                       ├── log_buffer      (shared log ring buffer)
                       └── TradingBot      (all trading logic)
                                │
                                ├── Thread: _main_loop (15m candle-aligned)
                                └── Thread: _monitor_loop (every 30s)
```

---

## Thread Model

| Thread | Name | Purpose | Frequency |
|---|---|---|---|
| Main | uvicorn | Serves HTTP requests | Always |
| Bot | bot-main | Trading cycle | Every 15m (candle-aligned) |
| Monitor | bot-monitor | Position monitoring | Every 30s |
| Per-order | order-{id} | Limit order timeout | Spawned per order |

All threads share `bot_state` (BotState object). Thread safety via `threading.Lock` on the state object.

---

## Data Flow (single cycle)

```
_run_cycle()
    │
    ├── client.get_balance()
    ├── positions.sync()          ← sync with Bybit
    ├── scanner.get_top_pairs()   ← top N by 24H turnover
    │
    └── for each symbol:
              │
              ├── market_data.fetch_all_timeframes()  ← 15m, 1h, 4h OHLCV
              ├── indicators.calculate_all()           ← scores per TF
              ├── regime_filter.passes()               ← ADX gate + ATR range
              ├── funding_monitor.get_modifier()       ← funding rate signal
              ├── scorer.score()                       ← confidence + direction
              │
              ├── [if score < threshold] → skip
              ├── [if direction limit]   → skip
              ├── [if slots full]        → try replacing worst loser
              │
              ├── risk_manager.calculate()             ← qty, SL, TP, leverage
              └── order_manager.place_entry()          ← limit order + timeout thread
```

---

## Module Dependencies

```
bybit_client   ← no internal deps
scanner        ← bybit_client
market_data    ← bybit_client
indicators     ← pandas_ta (external)
regime_filter  ← (no internal deps)
funding_monitor← bybit_client
scorer         ← (no internal deps)
risk_manager   ← bybit_client (for instrument info)
order_manager  ← bybit_client
position_manager← bybit_client
trade_tracker  ← sqlite3 (stdlib)
main           ← ALL of the above
```

---

## State Object (BotState)

Lives in `bot/main.py`. Imported by all API routes.

| Field | Type | Purpose |
|---|---|---|
| running | bool | Is bot loop active |
| paused | bool | Is bot in pause state |
| pause_reason | str | Why it's paused |
| pause_until | datetime | Auto-resume time |
| loss_streak | int | Current consecutive loss count |
| post_resume_losses | int | Losses after resume (for 24h pause logic) |
| is_post_resume | bool | Whether in post-resume monitoring period |
| cooldown_pairs | dict | {symbol: expiry_datetime} |
| auto_blacklist | dict | {symbol: expiry_datetime} |
| last_scan_pairs | list | Last scanned symbol list |

---

## Persistence

| Data | File | Format | Created by |
|---|---|---|---|
| Settings | data/settings.json | JSON | setup.py |
| Blacklist | data/blacklist.json | JSON array | setup.py |
| Trade history | data/trades.db | SQLite | setup.py |
| API keys | .env | Key=Value | User manually |

---

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | /api/status | Bot status, streaks, cooldowns |
| POST | /api/start | Start bot |
| POST | /api/stop | Stop bot |
| POST | /api/pause | Pause bot |
| POST | /api/resume | Resume bot |
| GET | /api/status/exchange | Test Bybit connectivity |
| GET | /api/settings | Get all settings |
| PUT | /api/settings | Update settings |
| POST | /api/settings/reset | Reset to defaults |
| GET | /api/blacklist | Get manual blacklist |
| POST | /api/blacklist | Add to blacklist |
| DELETE | /api/blacklist/{sym} | Remove from blacklist |
| GET | /api/positions | Live open positions |
| POST | /api/positions/{sym}/close | Manually close position |
| GET | /api/stats/summary | Overall PnL/win rate |
| GET | /api/stats/trades | Trade history |
| GET | /api/stats/pairs | Per-pair stats |
| GET | /api/scanner/last-run | Last scan results |
| GET | /api/balance | Account balance |
| GET | /api/logs | Log buffer (poll-based) |

---

## Confidence Score Formula

```
base_score = weighted_sum(indicator_scores) / total_weight × 10

final_score = base_score
            + (1 if 1h agrees with 15m direction)
            + (1 if 4h also agrees)
            - (1 if funding rate extreme in same direction as trade)

final_score clamped to 1.0 – 10.0
```

---

## Leverage Formula

```
projected_move_pct = ATR(14)_15m × 0.4 + ATR(14)_1h × 0.6  (as % of price)
leverage = round(target_return_pct / projected_move_pct)
leverage = max(1, min(leverage_cap, leverage))
```

Default: target_return=30%, cap=10x
