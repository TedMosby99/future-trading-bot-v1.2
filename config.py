"""
config.py
Default settings schema and load/save helpers.
All values here are the system defaults. User values are stored in data/settings.json.
See docs/CONFIG.md for full parameter documentation.
"""

import json
import os

SETTINGS_PATH = "data/settings.json"

DEFAULT_SETTINGS = {
    # --- Pair Scanning ---
    "scan_top_n": 15,                   # How many top pairs to scan (10-20)
    "blacklist": [],                     # Manually blacklisted pairs

    # --- Signal Filtering ---
    "confidence_threshold": 7.0,         # Minimum score to open trade (1-10)

    # --- Position Limits ---
    "max_positions": 3,                  # Max concurrent open positions
    "max_same_direction": 2,             # Max positions in same direction (long/short)

    # --- Position Sizing ---
    "base_trade_pct": 0.10,             # Base position size as % of capital (10%)
    "max_trade_pct": 0.14,              # Max position size as % of capital (14%)
    "min_trade_usd": 5.0,               # Minimum trade size in USD
    "max_trade_usd": 500.0,             # Hard cap on trade size in USD

    # --- Leverage ---
    "leverage_mode": "dynamic",          # "dynamic" or "fixed"
    "fixed_leverage": 5,                 # Used when leverage_mode = "fixed"
    "leverage_cap": 10,                  # Hard ceiling for dynamic leverage
    "leverage_target_return": 30.0,      # Target return % for leverage calc (30%)

    # --- Risk / Reward ---
    "rr_ratio": 3.0,                    # TP2 risk:reward ratio (2.0 or 3.0)
    "tp1_rr": 1.5,                      # TP1 risk:reward ratio
    "tp1_size_pct": 0.50,               # % of position to close at TP1 (50%)
    "atr_sl_multiplier": 1.5,           # SL = ATR * this multiplier
    "max_sl_pct": 5.0,                  # Max SL as % of entry price
    "max_tp_pct": 20.0,                 # Max TP as % of entry price

    # --- Trailing Stop ---
    "trailing_stop_enabled": True,
    "trailing_activation_pct": 1.0,     # Activate trailing after X% profit
    "trailing_distance_pct": 0.8,       # Trail distance as % of price

    # --- Breakeven Stop ---
    "breakeven_enabled": True,
    "breakeven_activation_rr": 1.0,     # Move SL to BE when profit = 1x SL

    # --- Order Settings ---
    "limit_timeout_seconds": 300,        # 5 min limit order timeout
    "entry_type": "limit",               # "limit", "market", or "smart"

    # --- Session Filter ---
    "session_filter_enabled": False,
    "session_allowed_hours_utc": [6, 22], # [start_hour, end_hour] UTC

    # --- Regime Filter ---
    "adx_threshold": 20.0,              # Minimum ADX to consider trending
    "atr_percentile_low": 20,           # Skip if ATR below this percentile
    "atr_percentile_high": 90,          # Skip if ATR above this percentile (news spike)

    # --- Funding Rate ---
    "funding_extreme_threshold": 0.001,  # 0.1% per 8h = extreme funding
    "funding_modifier_enabled": True,

    # --- Indicator Weights (must sum ~100) ---
    "weights": {
        "ema_cross": 20,
        "macd": 20,
        "volume": 20,
        "rsi": 15,
        "adx": 15,
        "bbands": 10,
    },

    # --- Loss Streak Protection ---
    "loss_streak_pause": 3,              # Losses before first pause
    "loss_streak_pause_hours": 3,        # Duration of first pause
    "post_resume_loss_limit": 2,         # Losses after resume before 24h pause
    "post_resume_pause_hours": 24,       # Duration of second pause

    # --- Cooldowns ---
    "manual_close_cooldown_hours": 1,    # Cooldown after manual close

    # --- Auto Blacklist ---
    "auto_blacklist_enabled": True,
    "auto_blacklist_losses": 4,          # Losses on pair in last N trades
    "auto_blacklist_window": 5,          # Window of recent trades to check
    "auto_blacklist_hours": 24,          # How long to blacklist pair
}


def load_settings() -> dict:
    """Load settings from data/settings.json, falling back to defaults."""
    if not os.path.exists(SETTINGS_PATH):
        return DEFAULT_SETTINGS.copy()

    try:
        with open(SETTINGS_PATH, "r") as f:
            saved = json.load(f)

        # Merge with defaults (new keys get default values)
        merged = DEFAULT_SETTINGS.copy()
        merged.update(saved)
        # Merge nested weights dict
        if "weights" in saved:
            merged["weights"] = {**DEFAULT_SETTINGS["weights"], **saved["weights"]}
        return merged

    except Exception as e:
        print(f"[CONFIG] Error loading settings: {e} — using defaults")
        return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict) -> bool:
    """Save settings to data/settings.json."""
    try:
        os.makedirs("data", exist_ok=True)
        with open(SETTINGS_PATH, "w") as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        print(f"[CONFIG] Error saving settings: {e}")
        return False


def load_blacklist() -> list:
    """Load manual blacklist from data/blacklist.json."""
    path = "data/blacklist.json"
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_blacklist(blacklist: list) -> bool:
    """Save manual blacklist to data/blacklist.json."""
    try:
        os.makedirs("data", exist_ok=True)
        with open("data/blacklist.json", "w") as f:
            json.dump(blacklist, f, indent=2)
        return True
    except Exception:
        return False
