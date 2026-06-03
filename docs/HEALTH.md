# HEALTH.md — Health Check Procedures

Run these checks after install to verify the bot is working correctly.
All commands assume the server is running on port 8000.

---

## CHECK 1: Server is alive
```bash
curl http://localhost:8000/api/status
```
**Expected:** JSON response containing `"status": "stopped"` (or "running")  
**If fail:** Server not running — run `python run.py`

---

## CHECK 2: Bybit API connected
```bash
curl http://localhost:8000/api/status/exchange
```
**Expected:** `{"connected":true,"mode":"demo/live"}`  
**If connected=false:** API credentials wrong — check .env

---

## CHECK 3: Settings loaded
```bash
curl http://localhost:8000/api/settings
```
**Expected:** Large JSON object with keys like `confidence_threshold`, `max_positions`, etc.  
**If 500 error:** Run `python setup.py` to regenerate settings

---

## CHECK 4: Database readable
```bash
curl http://localhost:8000/api/stats/summary
```
**Expected:** `{"total_trades":0,"wins":0,"losses":0,"win_rate":0.0,...}`  
**If error:** Database not initialized — run `python setup.py`

---

## CHECK 5: Balance readable (requires bot started)
```bash
curl -X POST http://localhost:8000/api/start
# wait 5 seconds
curl http://localhost:8000/api/balance
```
**Expected:** `{"balance": 10000.0}` (or whatever your demo balance is)  
**If balance=null:** API keys don't have read permission, or wrong keys

---

## CHECK 6: Scanner works (requires bot running, wait for first cycle)
```bash
curl http://localhost:8000/api/scanner/last-run
```
**Expected:** `{"pairs":["ETHUSDT","SOLUSDT",...],"count":15,"timestamp":"..."}`  
**If count=0:** Check logs — scanner may be failing silently

---

## CHECK 7: Logs are streaming
```bash
curl "http://localhost:8000/api/logs?since=0"
```
**Expected:** JSON with `"logs":[...]` array containing log entries  
**If empty:** Bot hasn't logged anything yet — normal on fresh start

---

## FULL HEALTH SEQUENCE (copy-paste)
```bash
echo "=== Health Check ===" && \
curl -s http://localhost:8000/api/status | python -c "import sys,json; d=json.load(sys.stdin); print('Status:', d.get('status'))" && \
curl -s http://localhost:8000/api/status/exchange | python -c "import sys,json; d=json.load(sys.stdin); print('Exchange:', d.get('connected'), d.get('mode'))" && \
curl -s http://localhost:8000/api/stats/summary | python -c "import sys,json; d=json.load(sys.stdin); print('DB trades:', d.get('total_trades',0))" && \
echo "=== All checks done ==="
```

---

## WHAT HEALTHY LOOKS LIKE IN LOGS
After starting the bot, the log stream should show (in order):
```
[BOT]         Bot started ✓
[BOT-MAIN]    Loop started
[BOT-MONITOR] Loop started
[BOT-CYCLE]   Starting new cycle
[SCANNER]     Scanned N pairs, returning top 15: ['ETHUSDT', ...]
[SCORE]       ETHUSDT: 7.3 (long) {base: 6.2, mtf_bonus: 1, ...}
[RISK]        ETHUSDT long | price=3000 qty=0.02 lev=8x $6.00 | SL=... TP1=...
[ORDER]       Order placed: ETHUSDT Buy Limit qty=0.02 id=...
[MAIN]        Next cycle in 742s
```

If you see only:
```
[BOT-CYCLE]   Starting new cycle
[SCANNER]     Scanned 15 pairs...
[MAIN]        Next cycle in 742s
```
...with no SCORE or RISK lines, every pair is failing the regime filter. Lower `adx_threshold` in settings.
