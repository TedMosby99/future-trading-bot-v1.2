"""
bot/risk_manager.py
Calculates all risk parameters for a trade:
    - Projected move (ATR-based)
    - Leverage (dynamic or fixed)
    - Position size (scaled by confidence and capital)
    - Stop loss price
    - TP1 price (partial close at 1:1.5)
    - TP2 price (final target)
    - Breakeven activation price
    - Trailing stop parameters
    - Minimum quantity check
"""

import logging
import math
from typing import Optional, Dict
import pandas as pd
from bot.bybit_client import BybitClient

log = logging.getLogger("RISK")


class RiskManager:
    """Calculates trade risk parameters."""

    def __init__(self, client: BybitClient, settings: dict):
        self.client = client
        self.settings = settings

    def calculate(
        self,
        symbol: str,
        df_15m: pd.DataFrame,
        df_1h: Optional[pd.DataFrame],
        raw_15m: dict,
        raw_1h: dict,
        confidence: float,
        direction: str,
        balance: float,
        settings: Optional[dict] = None,
    ) -> Optional[Dict]:
        """
        Calculate all risk parameters for a trade.

        Returns dict with all trade parameters, or None if trade should be skipped
        (e.g., calculated qty below minimum order size).
        """
        s = settings or self.settings

        # --- Current price ---
        price = raw_15m.get("current_price") or float(df_15m["close"].iloc[-1])

        # --- ATR-based projected move ---
        atr_15m = raw_15m.get("atr_pct", 0)
        atr_1h  = raw_1h.get("atr_pct", 0) if raw_1h else 0

        # Weighted average: 40% 15m, 60% 1h
        if atr_1h > 0:
            projected_move_pct = (atr_15m * 0.40) + (atr_1h * 0.60)
        else:
            projected_move_pct = atr_15m

        projected_move_pct = max(projected_move_pct, 0.3)  # Floor at 0.3%

        # --- Leverage ---
        leverage = self._calc_leverage(projected_move_pct, s)

        # --- Position size ---
        position_usd = self._calc_position_size(confidence, balance, s)

        # --- Quantity ---
        info = self.client.get_instrument_info(symbol)
        if info is None:
            log.warning(f"{symbol}: no instrument info, skipping")
            return None

        notional = position_usd * leverage
        qty = notional / price

        # Round down to qty_step
        qty = self._round_down(qty, info["qty_step"])

        # Minimum quantity check
        if qty < info["min_qty"]:
            log.warning(
                f"{symbol}: qty={qty} < min={info['min_qty']} "
                f"(need ${info['min_qty'] * price / leverage:.2f} capital at {leverage}x)"
            )
            return None

        # --- SL/TP prices ---
        atr_abs = raw_15m.get("atr", 0)
        sl_mult = s.get("atr_sl_multiplier", 1.5)
        sl_distance = atr_abs * sl_mult

        # Respect max SL %
        max_sl_dist = price * s.get("max_sl_pct", 5.0) / 100
        sl_distance = min(sl_distance, max_sl_dist)

        if sl_distance == 0:
            log.warning(f"{symbol}: SL distance is 0, skipping")
            return None

        rr = s.get("rr_ratio", 3.0)
        tp1_rr = s.get("tp1_rr", 1.5)

        if direction == "long":
            sl_price  = price - sl_distance
            tp1_price = price + sl_distance * tp1_rr
            tp2_price = price + sl_distance * rr
            be_price  = price + sl_distance  # breakeven = price + 1x SL distance
            trail_activation = price + sl_distance * s.get("breakeven_activation_rr", 1.0)
        else:
            sl_price  = price + sl_distance
            tp1_price = price - sl_distance * tp1_rr
            tp2_price = price - sl_distance * rr
            be_price  = price - sl_distance
            trail_activation = price - sl_distance * s.get("breakeven_activation_rr", 1.0)

        # Respect max TP %
        max_tp_dist = price * s.get("max_tp_pct", 20.0) / 100
        if direction == "long":
            tp2_price = min(tp2_price, price + max_tp_dist)
        else:
            tp2_price = max(tp2_price, price - max_tp_dist)

        # Trailing stop distance in price units
        trailing_dist = price * s.get("trailing_distance_pct", 0.8) / 100
        trailing_dist = max(trailing_dist, info["tick_size"])

        # TP1 quantity (50% of position)
        tp1_qty = self._round_down(qty * s.get("tp1_size_pct", 0.5), info["qty_step"])
        tp2_qty = self._round_down(qty - tp1_qty, info["qty_step"])

        tick = info["tick_size"]

        result = {
            "symbol": symbol,
            "direction": direction,
            "side": "Buy" if direction == "long" else "Sell",
            "price": price,
            "qty": qty,
            "tp1_qty": tp1_qty,
            "tp2_qty": tp2_qty,
            "leverage": leverage,
            "position_usd": position_usd,
            "notional": notional,
            "sl_price": self._round_price(sl_price, tick),
            "tp1_price": self._round_price(tp1_price, tick),
            "tp2_price": self._round_price(tp2_price, tick),
            "be_price": self._round_price(be_price, tick),
            "trail_activation": self._round_price(trail_activation, tick),
            "trailing_dist": self._round_price(trailing_dist, tick),
            "sl_distance": sl_distance,
            "projected_move_pct": round(projected_move_pct, 3),
            "confidence": confidence,
            "atr_pct": round(atr_15m, 3),
            "tick_size": tick,
            "qty_step": info["qty_step"],
        }

        log.info(
            f"{symbol} {direction.upper()} | "
            f"price={price} qty={qty} lev={leverage}x ${position_usd:.2f} | "
            f"SL={result['sl_price']} TP1={result['tp1_price']} TP2={result['tp2_price']}"
        )

        return result

    def _calc_leverage(self, projected_move_pct: float, s: dict) -> int:
        """
        Dynamic leverage: target 30% return on projected move.
        leverage = target_return / projected_move
        Capped at leverage_cap.
        """
        if s.get("leverage_mode") == "fixed":
            return int(s.get("fixed_leverage", 5))

        target = s.get("leverage_target_return", 30.0)
        cap = s.get("leverage_cap", 10)

        lev = round(target / projected_move_pct)
        return max(1, min(cap, lev))

    def _calc_position_size(self, confidence: float, balance: float, s: dict) -> float:
        """
        Scale position size between base_trade_pct and max_trade_pct of capital.
        Confidence 7 = base, confidence 10 = max.
        Hard floor: min_trade_usd. Hard ceiling: max_trade_usd.
        """
        base_pct = s.get("base_trade_pct", 0.10)
        max_pct  = s.get("max_trade_pct", 0.14)
        min_usd  = s.get("min_trade_usd", 5.0)
        max_usd  = s.get("max_trade_usd", 500.0)

        threshold = s.get("confidence_threshold", 7.0)
        scale = min(1.0, (confidence - threshold) / (10.0 - threshold))
        pct = base_pct + (max_pct - base_pct) * scale
        size = balance * pct

        return max(min_usd, min(max_usd, size))

    @staticmethod
    def _round_down(value: float, step: float) -> float:
        if step == 0:
            return value
        return math.floor(value / step) * step

    @staticmethod
    def _round_price(price: float, tick: float) -> float:
        if tick == 0:
            return round(price, 4)
        return round(round(price / tick) * tick, 10)
