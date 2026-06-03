"""
bot/regime_filter.py
Hard filters that gate whether a pair is worth analyzing at all.
If any filter fails, the pair is skipped for this cycle.

Filters:
    1. ADX gate         — market must be trending (ADX >= threshold)
    2. ATR range        — volatility must be in normal range (not too flat, not news spike)
    3. Session filter   — optional UTC hour window for low-liquidity avoidance
"""

import logging
import datetime
from typing import Optional
import pandas as pd

log = logging.getLogger("REGIME")


class RegimeFilter:
    """Applies pre-signal hard filters."""

    def __init__(self, settings: dict):
        self.settings = settings

    def passes(self, df: pd.DataFrame, indicator_raw: dict, settings: Optional[dict] = None) -> bool:
        """
        Returns True if the pair passes all regime filters.

        Args:
            df: 15m OHLCV DataFrame
            indicator_raw: raw values dict from IndicatorEngine (includes adx, atr_pct, atr_percentile)
            settings: override settings (uses self.settings if None)
        """
        s = settings or self.settings

        if not self._check_adx(indicator_raw, s):
            return False

        if not self._check_atr_range(indicator_raw, s):
            return False

        if not self._check_session(s):
            return False

        return True

    def _check_adx(self, raw: dict, s: dict) -> bool:
        """ADX must be above threshold — confirms trending market."""
        adx = raw.get("adx")
        if adx is None:
            log.debug("Regime: ADX unavailable — skipping pair")
            return False

        threshold = s.get("adx_threshold", 20.0)
        if adx < threshold:
            log.debug(f"Regime: ADX={adx:.1f} < {threshold} — choppy, skip")
            return False

        return True

    def _check_atr_range(self, raw: dict, s: dict) -> bool:
        """ATR must be within acceptable percentile range."""
        pct = raw.get("atr_percentile")
        if pct is None:
            return True  # Can't determine, allow through

        low = s.get("atr_percentile_low", 20)
        high = s.get("atr_percentile_high", 90)

        if pct < low:
            log.debug(f"Regime: ATR percentile={pct:.0f} too low (flatline) — skip")
            return False

        if pct > high:
            log.debug(f"Regime: ATR percentile={pct:.0f} too high (news spike) — skip")
            return False

        return True

    def _check_session(self, s: dict) -> bool:
        """Optional: only trade within allowed UTC hours."""
        if not s.get("session_filter_enabled", False):
            return True

        allowed = s.get("session_allowed_hours_utc", [6, 22])
        if len(allowed) != 2:
            return True

        start_h, end_h = allowed
        current_h = datetime.datetime.utcnow().hour

        if start_h <= end_h:
            in_session = start_h <= current_h < end_h
        else:  # wraps midnight
            in_session = current_h >= start_h or current_h < end_h

        if not in_session:
            log.debug(f"Regime: Outside session ({start_h}-{end_h} UTC, now {current_h}h) — skip")
            return False

        return True
