"""
bot/scanner.py
Scans Bybit for top USDT perpetual pairs by 24H turnover.
Excludes stablecoins, manually blacklisted, auto-blacklisted, and cooldown pairs.
"""

import logging
from typing import List
from bot.bybit_client import BybitClient

log = logging.getLogger("SCANNER")


class Scanner:
    """Scans and filters tradeable pairs."""

    def __init__(self, client: BybitClient, settings: dict):
        self.client = client
        self.settings = settings

    def get_top_pairs(
        self,
        blacklist: List[str] = None,
        auto_blacklist: dict = None,
        cooldown_pairs: dict = None,
    ) -> List[str]:
        """
        Return top N symbols sorted by 24H USDT turnover.
        Filters: USDT pairs only, no stablecoins, no blacklisted, no cooldown.

        Args:
            blacklist: manually blacklisted symbols
            auto_blacklist: {symbol: datetime} - auto-blacklisted with expiry
            cooldown_pairs: {symbol: datetime} - cooldown after manual close

        Returns:
            List of symbol strings, e.g. ['ETHUSDT', 'SOLUSDT', ...]
        """
        blacklist = blacklist or []
        auto_blacklist = auto_blacklist or {}
        cooldown_pairs = cooldown_pairs or {}

        tickers = self.client.get_all_tickers()
        if not tickers:
            log.warning("No tickers returned from Bybit")
            return []

        candidates = []
        for t in tickers:
            symbol = t.get("symbol", "")

            # Must be USDT linear perpetual
            if not symbol.endswith("USDT"):
                continue

            # Exclude stablecoins
            if self.client.is_stablecoin_pair(symbol):
                continue

            # Exclude manually blacklisted
            if symbol in blacklist:
                continue

            # Exclude auto-blacklisted
            if symbol in auto_blacklist:
                continue

            # Exclude cooldown pairs
            if symbol in cooldown_pairs:
                continue

            turnover = float(t.get("turnover24h", 0) or 0)
            candidates.append((symbol, turnover))

        # Sort by 24H turnover descending
        candidates.sort(key=lambda x: x[1], reverse=True)

        top_n = self.settings.get("scan_top_n", 15)
        result = [sym for sym, _ in candidates[:top_n]]

        log.info(f"Scanned {len(candidates)} pairs, returning top {len(result)}: "
                 f"{result[:5]}{'...' if len(result) > 5 else ''}")
        return result
