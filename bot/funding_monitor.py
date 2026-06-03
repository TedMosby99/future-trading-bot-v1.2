"""
bot/funding_monitor.py
Monitors funding rates for open and candidate positions.

Roles:
    1. Score modifier  — extreme funding opposite to trade direction reduces confidence
    2. Cost tracker    — accumulates funding cost for open positions
    3. Contrarian flag — extreme funding warns of squeeze risk
"""

import logging
from typing import Dict, Optional
from bot.bybit_client import BybitClient

log = logging.getLogger("FUNDING")


class FundingMonitor:
    """Tracks and scores funding rates."""

    def __init__(self, client: BybitClient):
        self.client = client
        self._rate_cache: Dict[str, float] = {}
        self._cumulative_cost: Dict[str, float] = {}  # symbol -> USD cost

    def get_rate(self, symbol: str) -> Optional[float]:
        """Return current funding rate for symbol (cached briefly)."""
        rate = self.client.get_funding_rate(symbol)
        if rate is not None:
            self._rate_cache[symbol] = rate
        return self._rate_cache.get(symbol)

    def get_modifier(self, symbol: str, settings: dict) -> int:
        """
        Return a confidence score modifier based on funding rate.

            0  = normal funding, no change
           -1  = extreme funding warning (direction mismatch risk)

        The scorer applies this per-direction:
            If going long and funding is extreme positive  → -1
            If going short and funding is extreme negative → -1
        """
        if not settings.get("funding_modifier_enabled", True):
            return 0

        rate = self.get_rate(symbol)
        if rate is None:
            return 0

        threshold = settings.get("funding_extreme_threshold", 0.001)
        abs_rate = abs(rate)

        if abs_rate >= threshold:
            direction = "positive" if rate > 0 else "negative"
            log.debug(f"Funding {symbol}: {rate:.4%} ({direction} extreme)")
            return int(rate / abs_rate)  # +1 or -1

        return 0

    def update_cost(self, position: dict, settings: dict):
        """
        Estimate and accumulate funding cost for an open position.
        Bybit charges funding every 8h. This is a rough tracker, not exact.
        """
        symbol = position.get("symbol", "")
        rate = self._rate_cache.get(symbol, 0)
        pos_value = abs(float(position.get("positionValue", 0)))
        cost = pos_value * abs(rate)

        if symbol not in self._cumulative_cost:
            self._cumulative_cost[symbol] = 0.0
        self._cumulative_cost[symbol] += cost

    def get_cumulative_cost(self, symbol: str) -> float:
        """Return estimated total funding cost paid for a symbol."""
        return self._cumulative_cost.get(symbol, 0.0)

    def clear(self, symbol: str):
        """Clear funding tracking for a closed position."""
        self._cumulative_cost.pop(symbol, None)
        self._rate_cache.pop(symbol, None)
