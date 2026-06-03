"""
setup.py
One-time (idempotent) setup: creates the SQLite database and default settings.
Run this before starting the bot for the first time.
It is safe to run multiple times — it will not overwrite existing data.

Usage:
    python setup.py
"""

import os
import sqlite3
import json
from config import DEFAULT_SETTINGS, SETTINGS_PATH


def init_database():
    """Create SQLite database and tables if they don't exist."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/trades.db")
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT    NOT NULL,
            side            TEXT    NOT NULL,
            entry_price     REAL    NOT NULL,
            exit_price      REAL,
            quantity        REAL    NOT NULL,
            leverage        INTEGER NOT NULL,
            position_usd    REAL    NOT NULL,
            pnl             REAL,
            pnl_pct         REAL,
            confidence      REAL,
            open_time       TEXT    NOT NULL,
            close_time      TEXT,
            close_reason    TEXT,
            status          TEXT    NOT NULL DEFAULT 'open',
            tp1_hit         INTEGER NOT NULL DEFAULT 0,
            notes           TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS pair_stats (
            symbol          TEXT    PRIMARY KEY,
            total_trades    INTEGER NOT NULL DEFAULT 0,
            wins            INTEGER NOT NULL DEFAULT 0,
            losses          INTEGER NOT NULL DEFAULT 0,
            total_pnl       REAL    NOT NULL DEFAULT 0,
            last_trade_time TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("[SETUP] Database initialized: data/trades.db")


def init_settings():
    """Write default settings.json if it does not exist."""
    os.makedirs("data", exist_ok=True)

    if os.path.exists(SETTINGS_PATH):
        print(f"[SETUP] Settings already exist: {SETTINGS_PATH} — skipping")
        return

    with open(SETTINGS_PATH, "w") as f:
        json.dump(DEFAULT_SETTINGS, f, indent=2)
    print(f"[SETUP] Default settings written: {SETTINGS_PATH}")


def init_blacklist():
    """Create empty blacklist.json if it does not exist."""
    path = "data/blacklist.json"
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump([], f)
        print("[SETUP] Blacklist initialized: data/blacklist.json")
    else:
        print("[SETUP] Blacklist already exists — skipping")


def check_env():
    """Warn if .env file is missing."""
    if not os.path.exists(".env"):
        print("[SETUP] WARNING: .env file not found.")
        print("         Copy .env.example to .env and fill in your API keys.")
    else:
        print("[SETUP] .env file found.")


if __name__ == "__main__":
    print("=" * 50)
    print("  Trading Bot — Setup")
    print("=" * 50)
    check_env()
    init_database()
    init_settings()
    init_blacklist()
    print("=" * 50)
    print("[SETUP] Setup complete. Run: python run.py")
    print("=" * 50)
