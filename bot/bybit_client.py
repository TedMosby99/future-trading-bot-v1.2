"""
bot/bybit_client.py
Wrapper around pybit's HTTP client.
Handles connection, error recovery, instrument info caching, and helper methods.
All methods return None/False on failure and log the error — they do NOT raise.
"""

import logging
import os
import time
import decimal
import math
from typing import Optional, Dict, List
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

load_dotenv()
log = logging.getLogger("BYBIT")

# Stablecoins to exclude from scanning
STABLECOINS = {
    "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDP", "GUSD",
    "LUSD", "FRAX", "USDD", "USTC", "USDJ", "SUSD", "CUSD",
    "NUSD", "XUSD", "EURC", "USDCE"
}


class BybitClient:
    """Wraps pybit HTTP session with helpers and instrument info caching."""

    def __init__(self, settings: dict):
        self.settings = settings
        self._mode: str = "DEMO"
        self._instrument_cache: Dict[str, dict] = {}
        self.session = self._connect()

    def _connect(self) -> Optional[HTTP]:
        try:
            api_key    = os.getenv("BYBIT_API_KEY", "")
            api_secret = os.getenv("BYBIT_API_SECRET", "")
            demo       = os.getenv("BYBIT_DEMO", "true").lower() == "true"
            testnet    = os.getenv("BYBIT_TESTNET", "false").lower() == "true"

            if demo:
                # Demo uses api-demo.bybit.com — key must be from Bybit Demo environment
                session = HTTP(demo=True, api_key=api_key, api_secret=api_secret)
                self._mode = "DEMO"
            elif testnet:
                session = HTTP(testnet=True, api_key=api_key, api_secret=api_secret)
                self._mode = "TESTNET"
            else:
                session = HTTP(testnet=False, api_key=api_key, api_secret=api_secret)
                self._mode = "LIVE"

            log.info(f"Bybit connected [{self._mode}]")
            return session
        except Exception as e:
            log.error(f"Failed to connect: {e}")
            return None

    def test_connection(self) -> bool:
        """Verify API connection and credentials."""
        try:
            self.session.get_server_time()
            # Try authenticated endpoint
            self.session.get_wallet_balance(accountType="UNIFIED")
            log.info("Connection test passed")
            return True
        except Exception as e:
            log.error(f"Connection test failed: {e}")
            return False

    def get_balance(self) -> Optional[float]:
        """Return available USDT wallet balance."""
        try:
            result = self.session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
            coins = result["result"]["list"][0]["coin"]
            for c in coins:
                if c["coin"] == "USDT":
                    return float(c["walletBalance"])
            return 0.0
        except Exception as e:
            log.error(f"get_balance error: {e}")
            return None

    def get_all_tickers(self) -> List[dict]:
        """Return all USDT linear perpetual tickers."""
        try:
            result = self.session.get_tickers(category="linear")
            return result["result"]["list"]
        except Exception as e:
            log.error(f"get_all_tickers error: {e}")
            return []

    def get_ticker(self, symbol: str) -> Optional[dict]:
        """Return ticker for a specific symbol."""
        try:
            result = self.session.get_tickers(category="linear", symbol=symbol)
            lst = result["result"]["list"]
            return lst[0] if lst else None
        except Exception as e:
            log.error(f"get_ticker {symbol} error: {e}")
            return None

    def get_kline(self, symbol: str, interval: str, limit: int = 200) -> List[list]:
        """
        Return OHLCV klines as list of [timestamp, open, high, low, close, volume].
        Data is returned oldest-first (Bybit sends newest-first; we reverse).
        interval: '1','5','15','30','60','120','240','D'
        """
        try:
            result = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,
                limit=limit,
            )
            data = result["result"]["list"]
            data.reverse()  # oldest first
            return data
        except Exception as e:
            log.error(f"get_kline {symbol}/{interval} error: {e}")
            return []

    def get_instrument_info(self, symbol: str) -> Optional[dict]:
        """Return instrument info (lot size, tick size). Cached per session."""
        if symbol in self._instrument_cache:
            return self._instrument_cache[symbol]
        try:
            result = self.session.get_instruments_info(category="linear", symbol=symbol)
            lst = result["result"]["list"]
            if not lst:
                return None
            info = {
                "min_qty": float(lst[0]["lotSizeFilter"]["minOrderQty"]),
                "qty_step": float(lst[0]["lotSizeFilter"]["qtyStep"]),
                "tick_size": float(lst[0]["priceFilter"]["tickSize"]),
            }
            self._instrument_cache[symbol] = info
            return info
        except Exception as e:
            log.error(f"get_instrument_info {symbol} error: {e}")
            return None

    def get_positions(self) -> List[dict]:
        """Return all open USDT linear positions (size > 0)."""
        try:
            result = self.session.get_positions(category="linear", settleCoin="USDT")
            positions = [
                p for p in result["result"]["list"]
                if float(p.get("size", 0)) > 0
            ]
            return positions
        except Exception as e:
            log.error(f"get_positions error: {e}")
            return []

    def get_position(self, symbol: str) -> Optional[dict]:
        """Return open position for a specific symbol, or None."""
        try:
            result = self.session.get_positions(category="linear", symbol=symbol)
            lst = result["result"]["list"]
            for p in lst:
                if float(p.get("size", 0)) > 0:
                    return p
            return None
        except Exception as e:
            log.error(f"get_position {symbol} error: {e}")
            return None

    def get_funding_rate(self, symbol: str) -> Optional[float]:
        """Return current funding rate for symbol."""
        try:
            result = self.session.get_tickers(category="linear", symbol=symbol)
            lst = result["result"]["list"]
            if lst:
                return float(lst[0].get("fundingRate", 0))
            return None
        except Exception as e:
            log.error(f"get_funding_rate {symbol} error: {e}")
            return None

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol (both buy and sell side)."""
        try:
            lev_str = str(leverage)
            self.session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=lev_str,
                sellLeverage=lev_str,
            )
            return True
        except Exception as e:
            # Code 110043 = leverage not changed (already set) — not an error
            if "110043" in str(e):
                return True
            log.error(f"set_leverage {symbol} lev={leverage} error: {e}")
            return False

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: float,
        price: Optional[float] = None,
        sl: Optional[float] = None,
        reduce_only: bool = False,
    ) -> Optional[str]:
        """
        Place an order. Returns order_id on success, None on failure.
        side: 'Buy' or 'Sell'
        order_type: 'Limit' or 'Market'
        """
        try:
            info = self.get_instrument_info(symbol)
            qty_str = self._format_qty(qty, info["qty_step"]) if info else str(qty)

            params = dict(
                category="linear",
                symbol=symbol,
                side=side,
                orderType=order_type,
                qty=qty_str,
                timeInForce="GTC" if order_type == "Limit" else "IOC",
                reduceOnly=reduce_only,
            )

            if order_type == "Limit" and price is not None:
                params["price"] = self._format_price(price, info["tick_size"] if info else 0.01)

            if sl is not None and not reduce_only:
                params["stopLoss"] = self._format_price(sl, info["tick_size"] if info else 0.01)
                params["slTriggerBy"] = "MarkPrice"

            result = self.session.place_order(**params)
            order_id = result["result"]["orderId"]
            log.info(f"Order placed: {symbol} {side} {order_type} qty={qty_str} id={order_id}")
            return order_id

        except Exception as e:
            log.error(f"place_order {symbol} {side} {order_type} error: {e}")
            return None

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel a specific order."""
        try:
            self.session.cancel_order(category="linear", symbol=symbol, orderId=order_id)
            log.info(f"Order cancelled: {symbol} {order_id}")
            return True
        except Exception as e:
            log.error(f"cancel_order {symbol} {order_id} error: {e}")
            return False

    def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all open orders for a symbol."""
        try:
            self.session.cancel_all_orders(category="linear", symbol=symbol)
            log.info(f"All orders cancelled: {symbol}")
            return True
        except Exception as e:
            log.error(f"cancel_all_orders {symbol} error: {e}")
            return False

    def close_position_market(self, symbol: str, side: str, qty: float) -> Optional[str]:
        """Close a position at market price."""
        close_side = "Sell" if side == "Buy" else "Buy"
        info = self.get_instrument_info(symbol)
        qty_str = self._format_qty(qty, info["qty_step"]) if info else str(qty)
        try:
            result = self.session.place_order(
                category="linear",
                symbol=symbol,
                side=close_side,
                orderType="Market",
                qty=qty_str,
                timeInForce="IOC",
                reduceOnly=True,
                closeOnTrigger=False,
            )
            return result["result"]["orderId"]
        except Exception as e:
            log.error(f"close_position_market {symbol} error: {e}")
            return None

    def set_trading_stop(
        self,
        symbol: str,
        sl: Optional[float] = None,
        trailing_stop: Optional[float] = None,
        active_price: Optional[float] = None,
    ) -> bool:
        """Set stop loss and/or trailing stop on an open position."""
        try:
            info = self.get_instrument_info(symbol)
            tick = info["tick_size"] if info else 0.01

            params = dict(category="linear", symbol=symbol, positionIdx=0)

            if sl is not None:
                params["stopLoss"] = self._format_price(sl, tick)
                params["slTriggerBy"] = "MarkPrice"

            if trailing_stop is not None:
                params["trailingStop"] = self._format_price(trailing_stop, tick)

            if active_price is not None:
                params["activePrice"] = self._format_price(active_price, tick)

            self.session.set_trading_stop(**params)
            return True
        except Exception as e:
            log.error(f"set_trading_stop {symbol} error: {e}")
            return False

    def get_closed_pnl(self, symbol: str, limit: int = 10) -> List[dict]:
        """Return recent closed P&L records for a symbol."""
        try:
            result = self.session.get_closed_pnl(
                category="linear", symbol=symbol, limit=limit
            )
            return result["result"]["list"]
        except Exception as e:
            log.error(f"get_closed_pnl {symbol} error: {e}")
            return []

    def get_open_orders(self, symbol: str) -> List[dict]:
        """Return all open orders for a symbol."""
        try:
            result = self.session.get_open_orders(category="linear", symbol=symbol)
            return result["result"]["list"]
        except Exception as e:
            log.error(f"get_open_orders {symbol} error: {e}")
            return []

    # --- Formatting helpers ---

    @staticmethod
    def _format_qty(qty: float, step: float) -> str:
        """Round qty down to the nearest step and format as string."""
        step_d = decimal.Decimal(str(step))
        qty_d = decimal.Decimal(str(qty))
        result = float(
            (qty_d / step_d).quantize(decimal.Decimal("1"), rounding=decimal.ROUND_DOWN)
            * step_d
        )
        # Determine decimal places from step
        decimals = max(0, -decimal.Decimal(str(step)).as_tuple().exponent)
        return f"{result:.{decimals}f}"

    @staticmethod
    def _format_price(price: float, tick: float) -> str:
        """Round price to tick size and format as string."""
        tick_d = decimal.Decimal(str(tick))
        price_d = decimal.Decimal(str(price))
        result = float(
            (price_d / tick_d).quantize(
                decimal.Decimal("1"), rounding=decimal.ROUND_HALF_UP
            )
            * tick_d
        )
        decimals = max(0, -decimal.Decimal(str(tick)).as_tuple().exponent)
        return f"{result:.{decimals}f}"

    @staticmethod
    def is_stablecoin_pair(symbol: str) -> bool:
        """Return True if the base currency is a stablecoin."""
        base = symbol.replace("USDT", "").replace("PERP", "")
        return base.upper() in STABLECOINS
