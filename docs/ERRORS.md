# ERRORS.md — Error Catalog

Each entry: ERROR → CAUSE → FIX

---

## INSTALL ERRORS

**ERROR:** `ModuleNotFoundError: No module named 'pybit'`  
**CAUSE:** Dependencies not installed  
**FIX:** `pip install -r requirements.txt`

---

**ERROR:** `ModuleNotFoundError: No module named 'pandas_ta'`  
**CAUSE:** pandas_ta not installed or install failed  
**FIX:** `pip install pandas_ta==0.3.14b0`  
If still fails: `pip install pandas_ta --no-deps && pip install pandas numpy`

---

**ERROR:** `ModuleNotFoundError: No module named 'fastapi'`  
**CAUSE:** FastAPI not installed  
**FIX:** `pip install fastapi uvicorn`

---

**ERROR:** `sqlite3.OperationalError: no such table: trades`  
**CAUSE:** setup.py was not run  
**FIX:** `python setup.py`

---

**ERROR:** `FileNotFoundError: data/settings.json`  
**CAUSE:** setup.py was not run  
**FIX:** `python setup.py`

---

**ERROR:** `OSError: [Errno 98] Address already in use` (Linux)  
**ERROR:** `OSError: [Errno 48] Address already in use` (Mac)  
**CAUSE:** Port 8000 is already occupied  
**FIX (option A):** Change PORT in .env to 8001, then `python run.py`  
**FIX (option B):** Kill the process using port 8000:
- Linux/Mac: `lsof -i :8000` then `kill -9 <PID>`
- Windows: `netstat -ano | findstr :8000` then `taskkill /PID <PID> /F`

---

**ERROR:** `ERROR: data/trades.db: No such file or directory`  
**CAUSE:** `data/` directory doesn't exist  
**FIX:** `mkdir data && python setup.py`

---

## RUNTIME ERRORS

**ERROR:** `pybit.exceptions.InvalidRequestError: retCode=10004`  
**CAUSE:** API key or secret is wrong  
**FIX:** Check `.env` — ensure BYBIT_API_KEY and BYBIT_API_SECRET match Bybit exactly. No spaces, no quotes around values.

---

**ERROR:** `pybit.exceptions.InvalidRequestError: retCode=10003`  
**CAUSE:** API key does not have trade permissions  
**FIX:** In Bybit API Management, ensure the key has "Trade" permission enabled

---

**ERROR:** `Connection test failed` in logs  
**CAUSE:** API credentials wrong, or network issue  
**FIX:**  
1. Verify .env credentials  
2. Test internet: `curl https://api.bybit.com/v5/market/time`  
3. If using testnet, set BYBIT_TESTNET=true  
4. If using demo, set BYBIT_TESTNET=false and use demo API keys

---

**ERROR:** `pybit.exceptions.InvalidRequestError: retCode=110043`  
**CAUSE:** Leverage already set to that value (not a real error)  
**FIX:** Ignore — the bot handles this automatically

---

**ERROR:** `pybit.exceptions.InvalidRequestError: retCode=110007`  
**CAUSE:** Insufficient balance to place order  
**FIX:** Add funds to your Bybit demo account, or reduce position size in Settings

---

**ERROR:** `Insufficient kline data for XYZUSDT/15 (N bars)`  
**CAUSE:** Pair has too little trading history  
**FIX:** Normal — bot skips this pair and continues. No action needed.

---

**ERROR:** `qty=0.0 < min=0.001`  
**CAUSE:** Position size ($5 × leverage) is below Bybit minimum for that pair  
**FIX:** This is expected for high-price pairs like BTC at $100k with small capital.  
The bot skips these pairs automatically. No action needed.

---

**ERROR:** `pandas_ta: AttributeError` or NaN values everywhere  
**CAUSE:** DataFrame too short for indicator calculation  
**FIX:** Normal on new/low-activity pairs. Bot skips them. No action needed.

---

**ERROR:** Bot starts but never opens trades  
**CAUSE (A):** All pairs failing regime filter (ADX too low = choppy market)  
**FIX (A):** Lower `adx_threshold` in Settings (try 15)  
**CAUSE (B):** Confidence threshold too high  
**FIX (B):** Lower `confidence_threshold` in Settings (try 6.5 for testing)  
**CAUSE (C):** All pairs below minimum qty  
**FIX (C):** Increase leverage_cap or capital

---

**ERROR:** UI loads but API calls return 404  
**CAUSE:** Routes not loading properly  
**FIX:** Check terminal for import errors. Run `python run.py` and look for red errors on startup.

---

**ERROR:** `json.JSONDecodeError` when loading settings  
**CAUSE:** data/settings.json is corrupted  
**FIX:** Delete `data/settings.json` and run `python setup.py` to regenerate defaults

---

## LOG LEVEL GUIDE

| Level | Meaning |
|---|---|
| `[INFO]` | Normal operation — trade signals, orders, cycle completions |
| `[WARNING]` | Something unusual but not breaking — loss streak, skipped pair |
| `[ERROR]` | Something failed — API error, calculation error |
| `[DEBUG]` | Verbose detail — only shown when LOG_LEVEL=DEBUG in .env |

Prefixes in log messages:
- `[BOT]` — main bot
- `[CYCLE]` — trading cycle
- `[SCANNER]` — pair scanning
- `[SCORE]` — confidence scoring
- `[RISK]` — risk calculation
- `[ORDER]` — order placement
- `[POSITION]` — position tracking
- `[MONITOR]` — position monitor loop
- `[STREAK]` — loss streak events
- `[TRACKER]` — trade recording
- `[BYBIT]` — Bybit API calls
- `[MANUAL]` — manual close events
