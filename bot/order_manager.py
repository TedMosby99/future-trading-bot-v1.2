"""
bot/order_manager.py
Handles all order operations:
    - Place entry (limit with 5-min timeout, fallback to market)
    - Place TP1 reduce-only limit order
    - Set SL via set_trading_stop
    - Move SL to breakeven
    - Activate trailing stop
    - Cancel all orders for a symbol
    - Close position at market
"""

import logging
import time
import threading
from typing import Optional, Dict, Callable
from bot.bybit_client import BybitClient

log = logging.getLogger("ORDER")


class OrderManager:
    """Manages entry and exit orders with limit-timeout logic."""

    def __init__(self, client: BybitClient, settings: dict):
        self.client = client
        self.settings = settings
        # Pending limit orders: {order_id: {symbol, params, placed_at, on_fill, on_cancel}}
        self._pending: Dict[str, dict] = {}
        self._lock = threading.Lock()

    # ---- Entry --------------------------------------------------------

    def place_entry(
        self,
        symbol: str,
        direction: str,
        params: dict,
        settings: Optional[dict] = None,
        on_fill: Optional[Callable] = None,
        on_cancel: Optional[Callable] = None,
    ) -> Optional[str]:
        """
        Place a limit entry order.
        Spawns a monitor thread that watches for fill or timeout.

        Args:
            symbol: trading pair
            direction: 'long' or 'short'
            params: dict from RiskManager.calculate()
            settings: override settings
            on_fill: callback(symbol, params) when order fills
            on_cancel: callback(symbol) when order times out

        Returns:
            order_id if placed, None on failure
        """
        s = settings or self.settings
        side = params["side"]
        price = params["price"]
        qty = params["qty"]
        sl = params["sl_price"]
        leverage = params["leverage"]

        # Set leverage before placing order
        if not self.client.set_leverage(symbol, leverage):
            log.warning(f"{symbol}: failed to set leverage {leverage}x")

        # Determine entry type
        entry_type = s.get("entry_type", "limit")

        if entry_type == "market":
            order_id = self.client.place_order(symbol, side, "Market", qty, sl=sl)
            if order_id and on_fill:
                on_fill(symbol, params)
            return order_id

        # Limit order
        order_id = self.client.place_order(symbol, side, "Limit", qty, price=price, sl=sl)
        if not order_id:
            return None

        timeout = s.get("limit_timeout_seconds", 300)
        log.info(f"{symbol}: limit order placed id={order_id}, timeout={timeout}s")

        with self._lock:
            self._pending[order_id] = {
                "symbol": symbol,
                "params": params,
                "placed_at": time.time(),
                "timeout": timeout,
                "on_fill": on_fill,
                "on_cancel": on_cancel,
            }

        # Monitor in background thread
        t = threading.Thread(
            target=self._monitor_limit_order,
            args=(order_id, symbol, params, s, on_fill, on_cancel),
            daemon=True,
            name=f"order-{order_id[:8]}",
        )
        t.start()

        return order_id

    def _monitor_limit_order(
        self,
        order_id: str,
        symbol: str,
        params: dict,
        s: dict,
        on_fill: Optional[Callable],
        on_cancel: Optional[Callable],
    ):
        """Monitor a limit order until filled, cancelled, or timed out."""
        timeout = s.get("limit_timeout_seconds", 300)
        check_interval = 10  # seconds
        elapsed = 0

        while elapsed < timeout:
            time.sleep(check_interval)
            elapsed += check_interval

            # Check order status
            orders = self.client.get_open_orders(symbol)
            order_ids = {o["orderId"] for o in orders}

            if order_id not in order_ids:
                # Order no longer open — either filled or cancelled externally
                log.info(f"{symbol}: limit order {order_id} no longer open (filled or cancelled)")
                with self._lock:
                    self._pending.pop(order_id, None)
                if on_fill:
                    on_fill(symbol, params)
                return

        # Timeout — cancel and decide whether to re-evaluate
        log.info(f"{symbol}: limit order {order_id} timed out after {timeout}s")
        self.client.cancel_order(symbol, order_id)

        with self._lock:
            self._pending.pop(order_id, None)

        # Re-evaluate: use "smart" fallback — fire on_cancel which triggers rescore
        if on_cancel:
            on_cancel(symbol, params)

    # ---- Post-fill setup ---------------------------------------------

    def setup_exit_orders(self, symbol: str, params: dict, settings: Optional[dict] = None):
        """
        After entry fills, place TP1 reduce-only limit order and
        configure SL + trailing stop via set_trading_stop.
        """
        s = settings or self.settings
        direction = params["direction"]
        close_side = "Sell" if direction == "long" else "Buy"

        # TP1 — reduce-only limit order for 50% of position
        tp1_qty = params.get("tp1_qty", params["qty"] / 2)
        tp1_price = params["tp1_price"]

        if tp1_qty > 0:
            tp1_id = self.client.place_order(
                symbol, close_side, "Limit", tp1_qty,
                price=tp1_price, reduce_only=True
            )
            if tp1_id:
                log.info(f"{symbol}: TP1 order placed at {tp1_price} qty={tp1_qty} id={tp1_id}")
            params["tp1_order_id"] = tp1_id

        # SL via set_trading_stop (already set on entry order, but set again to be safe)
        self.client.set_trading_stop(symbol, sl=params["sl_price"])

        log.info(f"{symbol}: Exit orders configured (TP1={tp1_price}, SL={params['sl_price']})")

    def move_sl_to_breakeven(self, symbol: str, be_price: float):
        """Move stop loss to breakeven price."""
        ok = self.client.set_trading_stop(symbol, sl=be_price)
        if ok:
            log.info(f"{symbol}: SL moved to breakeven {be_price}")
        return ok

    def activate_trailing_stop(self, symbol: str, trailing_dist: float, active_price: float):
        """Activate Bybit native trailing stop."""
        ok = self.client.set_trading_stop(
            symbol,
            trailing_stop=trailing_dist,
            active_price=active_price,
        )
        if ok:
            log.info(f"{symbol}: Trailing stop activated dist={trailing_dist} activation={active_price}")
        return ok

    # ---- Cleanup ------------------------------------------------------

    def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all open orders for a symbol."""
        # Remove from pending tracking
        with self._lock:
            to_remove = [oid for oid, v in self._pending.items() if v["symbol"] == symbol]
            for oid in to_remove:
                self._pending.pop(oid)
        return self.client.cancel_all_orders(symbol)

    def close_position(self, symbol: str, position: dict) -> bool:
        """Close a position at market price."""
        side = position.get("side", "")
        qty = float(position.get("size", 0))
        if qty == 0:
            return True

        self.cancel_all_orders(symbol)
        order_id = self.client.close_position_market(symbol, side, qty)
        if order_id:
            log.info(f"{symbol}: Position closed at market qty={qty}")
            return True
        return False

    def has_pending_order(self, symbol: str) -> bool:
        """Check if there's a pending entry order for this symbol."""
        with self._lock:
            return any(v["symbol"] == symbol for v in self._pending.values())

    def pending_count(self) -> int:
        """Total number of pending (unfilled) entry orders."""
        with self._lock:
            return len(self._pending)

    def pending_direction_count(self, direction: str) -> int:
        """Number of pending orders in a given direction ('long' or 'short')."""
        with self._lock:
            return sum(
                1 for v in self._pending.values()
                if v.get("params", {}).get("direction") == direction
            )
