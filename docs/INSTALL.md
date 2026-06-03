# INSTALL.md — Step-by-step Installation Guide

---

## STEP 1: Verify Python Version
```bash
python --version
```
**Expected:** `Python 3.11.x` or higher  
**If Python 3.10 or below:** Install Python 3.11+ from https://python.org  
**If command not found:** Try `python3 --version` and use `python3` throughout

---

## STEP 2: Install Dependencies
```bash
pip install -r requirements.txt
```
**Expected:** `Successfully installed pybit-X pandas-X pandas_ta-X fastapi-X uvicorn-X ...`  
**If permission error:** Try `pip install --user -r requirements.txt`  
**If pandas_ta fails:** Try `pip install pandas_ta==0.3.14b0`  
**If pybit fails:** Try `pip install pybit --upgrade`

---

## STEP 3: Configure Environment
```bash
cp .env.example .env
```
Open `.env` in a text editor and set:

| Variable | Value | Notes |
|---|---|---|
| BYBIT_API_KEY | your key | From Bybit > API Management |
| BYBIT_API_SECRET | your secret | From Bybit > API Management |
| BYBIT_TESTNET | false | false = demo/live; true = testnet |
| PORT | 8000 | Change if 8000 is in use |
| LOG_LEVEL | INFO | DEBUG for verbose output |

**For Bybit Demo Trading:**
1. Log into Bybit
2. Switch to Demo Trading mode (top of page)
3. Go to Account > API Management
4. Create new API key (read + trade permissions)
5. Copy key and secret to .env
6. Keep BYBIT_TESTNET=false

---

## STEP 4: Initialize Database
```bash
python setup.py
```
**Expected output:**
```
==================================================
  Trading Bot — Setup
==================================================
[SETUP] .env file found.
[SETUP] Database initialized: data/trades.db
[SETUP] Default settings written: data/settings.json
[SETUP] Blacklist initialized: data/blacklist.json
==================================================
[SETUP] Setup complete. Run: python run.py
==================================================
```
**If `.env file not found`:** Go back to Step 3  
**If permission error on data/:** `mkdir data && chmod 755 data`  
**Safe to run again:** setup.py is idempotent — running it twice does not break anything

---

## STEP 5: Start the Server
```bash
python run.py
```
**Expected:**
```
==================================================
  Trading Bot
  UI → http://localhost:8000
  API docs → http://localhost:8000/api/docs
==================================================
INFO:     Uvicorn running on http://0.0.0.0:8000
```
**If port already in use:** Change PORT in .env to 8001 or 8080  
**If module not found:** Re-run `pip install -r requirements.txt`

---

## STEP 6: Open the Dashboard
Open a browser and go to: **http://localhost:8000**

**Expected:** Dark trading dashboard loads. Status shows `● STOPPED`

---

## STEP 7: Verify Exchange Connection
In the dashboard, open a terminal and run:
```bash
curl http://localhost:8000/api/status/exchange
```
**Expected:** `{"connected":true,"mode":"demo/live"}`  
**If connected=false:** Check .env API keys, check internet, check Bybit API permissions

---

## RUNNING IN BACKGROUND (optional)
```bash
# Linux/Mac — run in background with nohup
nohup python run.py > bot.log 2>&1 &

# Check if running
curl http://localhost:8000/api/status

# Stop it
kill $(lsof -t -i:8000)
```

---

## UPDATING SETTINGS
After install, all settings can be changed in the web UI under the **Settings** tab.
No restart required — settings are hot-reloaded each trading cycle.
