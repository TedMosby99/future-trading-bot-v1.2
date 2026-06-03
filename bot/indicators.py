"""
bot/indicators.py
Calculates all technical indicators and returns directional scores.

Each indicator returns a score from -1.0 to +1.0:
    +1.0 = strong bullish
    -1.0 = strong bearish
     0.0 = neutral

The IndicatorEngine.calculate_all() method returns a dict of all scores
plus raw values (ATR, ADX) needed for risk calculations.
"""

import logging
from typing import Optional, Dict
import numpy as np
import pandas as pd

log = logging.getLogger("INDICATORS")

try:
    import pandas_ta as ta
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False
    log.error("pandas_ta not installed. Run: pip install pandas_ta")


def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


class IndicatorEngine:
    """Calculates all indicators and returns scored signals."""

    def calculate_all(self, df: pd.DataFrame) -> Dict:
        """
        Calculate all indicators on the given DataFrame.

        Returns dict with keys:
            scores: {indicator_name: score (-1 to 1)}
            raw:    {atr, adx, current_price, ema20, ema50}
        """
        if df is None or len(df) < 50:
            return {"scores": {}, "raw": {}}

        scores = {}
        raw = {}

        try:
            price = float(df["close"].iloc[-1])
            raw["current_price"] = price

            scores["ema_cross"], r = self._score_ema(df)
            raw.update(r)

            scores["rsi"] = self._score_rsi(df)
            scores["macd"] = self._score_macd(df)
            scores["bbands"] = self._score_bbands(df)
            scores["volume"] = self._score_volume(df)

            scores["adx"], r = self._score_adx(df)
            raw.update(r)

            r = self._calc_atr(df)
            raw.update(r)

        except Exception as e:
            log.error(f"calculate_all error: {e}", exc_info=True)

        return {"scores": scores, "raw": raw}

    # ---- Individual indicators ----------------------------------------

    def _score_ema(self, df: pd.DataFrame):
        """EMA 20/50 crossover. Score based on separation relative to price."""
        try:
            close = df["close"]
            ema20 = ta.ema(close, length=20)
            ema50 = ta.ema(close, length=50)

            if ema20 is None or ema50 is None:
                return 0.0, {}

            e20 = float(ema20.iloc[-1])
            e50 = float(ema50.iloc[-1])
            price = float(close.iloc[-1])

            if price == 0:
                return 0.0, {}

            # Separation as % of price; cap at ±2%
            diff_pct = (e20 - e50) / price
            score = _clamp(diff_pct / 0.02)

            return score, {"ema20": e20, "ema50": e50}

        except Exception as e:
            log.debug(f"EMA score error: {e}")
            return 0.0, {}

    def _score_rsi(self, df: pd.DataFrame) -> float:
        """RSI(14). Trend following: above 50 = bullish, below 50 = bearish."""
        try:
            rsi = ta.rsi(df["close"], length=14)
            if rsi is None:
                return 0.0

            v = float(rsi.iloc[-1])
            if np.isnan(v):
                return 0.0

            # Normalize distance from 50
            score = (v - 50.0) / 50.0

            # Dampen extremes (overbought/oversold = exhaustion risk)
            if v > 75:
                score = 0.5
            elif v < 25:
                score = -0.5

            return _clamp(score)

        except Exception as e:
            log.debug(f"RSI score error: {e}")
            return 0.0

    def _score_macd(self, df: pd.DataFrame) -> float:
        """MACD histogram normalized by recent ATR."""
        try:
            macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
            if macd_df is None:
                return 0.0

            hist_col = [c for c in macd_df.columns if "MACDh" in c]
            if not hist_col:
                return 0.0

            hist = float(macd_df[hist_col[0]].iloc[-1])
            if np.isnan(hist):
                return 0.0

            atr_s = ta.atr(df["high"], df["low"], df["close"], length=14)
            atr = float(atr_s.iloc[-1]) if atr_s is not None else 1.0
            if atr == 0:
                return 0.0

            # Normalize histogram by a fraction of ATR
            score = hist / (atr * 0.15)
            return _clamp(score)

        except Exception as e:
            log.debug(f"MACD score error: {e}")
            return 0.0

    def _score_bbands(self, df: pd.DataFrame) -> float:
        """Bollinger Bands. Price position relative to bands."""
        try:
            bb = ta.bbands(df["close"], length=20, std=2.0)
            if bb is None:
                return 0.0

            upper_col = [c for c in bb.columns if "BBU" in c]
            lower_col = [c for c in bb.columns if "BBL" in c]
            mid_col   = [c for c in bb.columns if "BBM" in c]

            if not upper_col or not lower_col or not mid_col:
                return 0.0

            upper = float(bb[upper_col[0]].iloc[-1])
            lower = float(bb[lower_col[0]].iloc[-1])
            mid   = float(bb[mid_col[0]].iloc[-1])
            price = float(df["close"].iloc[-1])

            band_range = upper - lower
            if band_range == 0:
                return 0.0

            # -1 at lower band, 0 at mid, +1 at upper band
            score = (price - mid) / (band_range / 2)
            return _clamp(score)

        except Exception as e:
            log.debug(f"BBands score error: {e}")
            return 0.0

    def _score_volume(self, df: pd.DataFrame) -> float:
        """Volume vs 20-period average, directionally weighted by price move."""
        try:
            current_vol = float(df["volume"].iloc[-1])
            avg_vol = float(df["volume"].rolling(20).mean().iloc[-1])
            if avg_vol == 0:
                return 0.0

            # Direction from last candle
            price_delta = float(df["close"].iloc[-1]) - float(df["close"].iloc[-2])
            direction = 1 if price_delta >= 0 else -1

            vol_ratio = current_vol / avg_vol
            # 0 at 1x avg, 1 at 3x avg
            vol_strength = _clamp((vol_ratio - 1.0) / 2.0, 0.0, 1.0)
            score = direction * vol_strength
            return _clamp(score)

        except Exception as e:
            log.debug(f"Volume score error: {e}")
            return 0.0

    def _score_adx(self, df: pd.DataFrame):
        """ADX with DI direction. Returns score + raw adx value."""
        try:
            adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
            if adx_df is None:
                return 0.0, {}

            adx_col = [c for c in adx_df.columns if c.startswith("ADX")]
            dmp_col = [c for c in adx_df.columns if c.startswith("DMP")]
            dmn_col = [c for c in adx_df.columns if c.startswith("DMN")]

            if not adx_col or not dmp_col or not dmn_col:
                return 0.0, {}

            adx = float(adx_df[adx_col[0]].iloc[-1])
            dmp = float(adx_df[dmp_col[0]].iloc[-1])
            dmn = float(adx_df[dmn_col[0]].iloc[-1])

            if np.isnan(adx):
                return 0.0, {}

            direction = 1 if dmp > dmn else -1
            # Strength: 0 at ADX=20, 1 at ADX=50
            strength = _clamp((adx - 20.0) / 30.0, 0.0, 1.0)
            score = direction * strength

            return _clamp(score), {"adx": adx, "dmp": dmp, "dmn": dmn}

        except Exception as e:
            log.debug(f"ADX score error: {e}")
            return 0.0, {}

    def _calc_atr(self, df: pd.DataFrame) -> dict:
        """Calculate ATR(14) as raw value and as % of price. Not scored."""
        try:
            atr_s = ta.atr(df["high"], df["low"], df["close"], length=14)
            if atr_s is None:
                return {}
            atr = float(atr_s.iloc[-1])
            price = float(df["close"].iloc[-1])
            atr_pct = (atr / price * 100) if price > 0 else 0.0

            # ATR percentile (how current ATR compares to last 100 bars)
            atr_series = atr_s.dropna()
            if len(atr_series) >= 20:
                pct_rank = float((atr_series < atr).sum() / len(atr_series) * 100)
            else:
                pct_rank = 50.0

            return {
                "atr": atr,
                "atr_pct": atr_pct,
                "atr_percentile": pct_rank,
            }
        except Exception as e:
            log.debug(f"ATR calc error: {e}")
            return {}
