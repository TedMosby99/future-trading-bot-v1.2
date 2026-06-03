"""
bot/position_manager.py
Tracks open positions, enforces direction limits, detects TP1 hits,
manual closes, and triggers breakeven/trailing stop setup.
"""

import logging
from typing import Dict, List, Optional, Tuple
from bot.bybit_client import BybitClient

log = logging.getLogger("POSITION")


class PositionManager:
    """Manages open position state and lifecycle events."""

    def __init__(self, client: BybitClient):
        self.client = client
        # Our internal position records: {symbol: {qty, side, entry_price, tp1_hit, ...}}
        self._records: Dict[str, dict] = {}
        # Bybit-side snapshot: {symbol: position_dict}
        self._bybit_snapshot: Dict[str, dict] = {}

    # ---- Sync ---------------------------------------------------------

    def sync(self) -> List[dict]:
        """Sync with Bybit, return current open positions."""
        positions = self.client.get_positions()
        self._bybit_snapshot = {p["symbol"]: p for p in positions}
        return positions

    def get_open_positions(self) -> List[dict]:
        """Return cached Bybit positions (call sync() first)."""
        return list(self._bybit_snapshot.values())

    # ---- Slot checks --------------------------------------------------

    def can_open(self, direction: str, settings: dict) -> bool:
        """
        Returns True if a new position can be opened in the given direction.
        Checks both total position limit and same-direction limit.
        """
        positions = self.get_open_positions()
        total = len(positions)
        max_total = settings.get("max_positions", 3)
        max_dir   = settings.get("max_same_direction", 2)

        if total >= max_total:
            return False  # Will be handled by replacement logic

        same_dir = sum(
            1 for p in positions
            if self._bybit_side_to_direction(p.get("side", "")) == direction
        )
        if same_dir >= max_dir:
            log.info(f"Direction limit: already {same_dir} {direction} positions (max {max_dir})")
            return False

        return True

    def direction_slots_full(self, direction: str, settings: dict) -> bool:
        """Returns True if direction limit is reached."""
        positions = self.get_open_positions()
        max_dir = settings.get("max_same_direction", 2)
        same_dir = sum(
            1 for p in positions
            if self._bybit_side_to_direction(p.get("side", "")) == direction
        )
        return same_dir >= max_dir

    def get_worst_loser(self, min_confidence: float = 0.0) -> Optional[dict]:
        """
        Return the open position with the highest negative PnL (worst loser),
        only if its PnL is negative.
        Returns None if no losing positions exist.
        """
        positions = self.get_open_positions()
        losers = [
            p for p in positions
            if float(p.get("unrealisedPnl", 0)) < 0
        ]
        if not losers:
            return None
        return min(losers, key=lambda p: float(p.get("unrealisedPnl", 0)))

    # ---- Lifecycle event detection ------------------------------------

    def register_open(self, symbol: str, params: dict):
        """Record that we opened a position for this symbol."""
        self._records[symbol] = {
            "symbol": symbol,
            "side": params["side"],
            "direction": params["direction"],
            "entry_price": params["price"],
            "qty": params["qty"],
            "tp1_qty": params["tp1_qty"],
            "tp2_qty": params["tp2_qty"],
            "sl_price": params["sl_price"],
            "tp1_price": params["tp1_price"],
            "tp2_price": params["tp2_price"],
            "be_price": params["be_price"],
            "trail_activation": params["trail_activation"],
            "trailing_dist": params["trailing_dist"],
            "leverage": params["leverage"],
            "position_usd": params["position_usd"],
            "confidence": params["confidence"],
            "tp1_hit": False,
            "be_active": False,
            "trailing_active": False,
            "tp1_order_id": params.get("tp1_order_id"),
        }
        log.info(f"{symbol}: Position registered internally")

    def check_tp1_hit(self, symbol: str) -> bool:
        """
        Detect if TP1 was hit by checking if position qty decreased.
        Returns True if TP1 just hit (first detection).
        """
        rec = self._records.get(symbol)
        if rec is None or rec["tp1_hit"]:
            return False

        bybit_pos = self._bybit_snapshot.get(symbol)
        if bybit_pos is None:
            return False

        current_qty = float(bybit_pos.get("size", 0))
        original_qty = rec["qty"]

        if current_qty < original_qty * 0.75:  # qty reduced by >25% = TP1 hit
            rec["tp1_hit"] = True
            log.info(f"{symbol}: TP1 detected (qty {original_qty} → {current_qty})")
            return True

        return False

    def check_breakeven_trigger(self, symbol: str) -> bool:
        """
        Check if price has moved enough to activate breakeven stop.
        Returns True if breakeven should be set NOW (first time).
        """
        rec = self._records.get(symbol)
        if rec is None or rec["be_active"]:
            return False

        bybit_pos = self._bybit_snapshot.get(symbol)
        if bybit_pos is None:
            return False

        mark_price = float(bybit_pos.get("markPrice", 0))
        be_price = rec["be_price"]
        direction = rec["direction"]

        triggered = (
            (direction == "long" and mark_price >= be_price) or
            (direction == "short" and mark_price <= be_price)
        )

        if triggered:
            rec["be_active"] = True
            log.info(f"{symbol}: Breakeven trigger at mark={mark_price} be={be_price}")
            return True

        return False

    def check_trailing_trigger(self, symbol: str) -> bool:
        """
        Check if trailing stop should be activated.
        Returns True if trailing should be activated NOW (first time).
        """
        rec = self._records.get(symbol)
        if rec is None or rec["trailing_active"]:
            return False

        bybit_pos = self._bybit_snapshot.get(symbol)
        if bybit_pos is None:
            return False

        mark_price = float(bybit_pos.get("markPrice", 0))
        activation = rec["trail_activation"]
        direction = rec["direction"]

        triggered = (
            (direction == "long" and mark_price >= activation) or
            (direction == "short" and mark_price <= activation)
        )

        if triggered:
            rec["trailing_active"] = True
            log.info(f"{symbol}: Trailing stop trigger at mark={mark_price}")
            return True

        return False

    def detect_closed(self, known_symbols: set) -> List[Tuple[str, dict]]:
        """
        Compare current Bybit positions against known_symbols.
        Return list of (symbol, record) for positions that have closed.
        """
        closed = []
        for symbol in list(self._records.keys()):
            if symbol not in self._bybit_snapshot:
                rec = self._records.pop(symbol, {})
                closed.append((symbol, rec))
                log.info(f"{symbol}: Position closed (no longer in Bybit)")
        return closed

    def detect_manual_close(self, symbol: str, known_open_before: bool) -> bool:
        """Return True if a previously-open position is now gone from Bybit."""
        return known_open_before and symbol not in self._bybit_snapshot

    def remove_record(self, symbol: str):
        """Remove internal record for a closed position."""
        self._records.pop(symbol, None)

    def get_record(self, symbol: str) -> Optional[dict]:
        """Get internal record for a symbol."""
        return self._records.get(symbol)

    def get_all_records(self) -> dict:
        """Return all internal position records."""
        return dict(self._records)

    # ---- Helpers ------------------------------------------------------

    @staticmethod
    def _bybit_side_to_direction(side: str) -> str:
        return "long" if side == "Buy" else "short"

    def count_by_direction(self) -> Dict[str, int]:
        positions = self.get_open_positions()
        counts = {"long": 0, "short": 0}
        for p in positions:
            d = self._bybit_side_to_direction(p.get("side", ""))
            counts[d] = counts.get(d, 0) + 1
        return counts
