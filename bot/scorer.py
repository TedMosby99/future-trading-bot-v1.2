"""
bot/scorer.py
Weighted confidence scoring engine.

Takes indicator scores from all three timeframes (15m, 1h, 4h),
applies weights, adds multi-timeframe alignment bonuses, applies
funding rate modifier, and returns a final confidence score 1-10
plus trade direction.
"""

import logging
from typing import Dict, Tuple, Optional

log = logging.getLogger("SCORER")

DEFAULT_WEIGHTS = {
    "ema_cross": 20,
    "macd": 20,
    "volume": 20,
    "rsi": 15,
    "adx": 15,
    "bbands": 10,
}


class Scorer:
    """Produces confidence scores from multi-timeframe indicator data."""

    def __init__(self, settings: dict):
        self.settings = settings

    def score(
        self,
        ind_15m: dict,
        ind_1h: Optional[dict],
        ind_4h: Optional[dict],
        funding_modifier: int,
        settings: Optional[dict] = None,
    ) -> Tuple[float, str, dict]:
        """
        Calculate confidence score and direction.

        Args:
            ind_15m: indicator results from 15m timeframe
            ind_1h:  indicator results from 1h timeframe (may be None)
            ind_4h:  indicator results from 4h timeframe (may be None)
            funding_modifier: +1, 0, or -1 from FundingMonitor
            settings: override settings

        Returns:
            (confidence_score: 1.0-10.0, direction: 'long'|'short', breakdown: dict)
        """
        s = settings or self.settings
        weights = s.get("weights", DEFAULT_WEIGHTS)

        # --- Primary score from 15m ---
        base_score, direction = self._weighted_score(ind_15m.get("scores", {}), weights)

        if base_score == 0:
            return 1.0, "long", {}

        # --- Multi-timeframe alignment bonus ---
        mtf_bonus = 0

        if ind_1h and ind_1h.get("scores"):
            score_1h, dir_1h = self._weighted_score(ind_1h["scores"], weights)
            if dir_1h == direction:
                mtf_bonus += 1
                log.debug(f"MTF: 1h agrees ({direction}) +1")

                if ind_4h and ind_4h.get("scores"):
                    score_4h, dir_4h = self._weighted_score(ind_4h["scores"], weights)
                    if dir_4h == direction:
                        mtf_bonus += 1
                        log.debug(f"MTF: 4h agrees ({direction}) +1 (total +2)")

        # --- Funding rate modifier ---
        funding_penalty = 0
        if s.get("funding_modifier_enabled", True) and funding_modifier != 0:
            # Penalize if funding is extreme in opposite direction of trade
            if (direction == "long" and funding_modifier > 0) or \
               (direction == "short" and funding_modifier < 0):
                funding_penalty = 1  # high funding = crowd is on our side = risky
                log.debug(f"Funding penalty: -1 (crowd already positioned)")

        # --- Final score ---
        # base_score is 0-10 (normalized absolute)
        # Add MTF bonus (max +2), subtract funding penalty
        final = base_score + mtf_bonus - funding_penalty
        final = max(1.0, min(10.0, final))

        breakdown = {
            "base": round(base_score, 2),
            "mtf_bonus": mtf_bonus,
            "funding_penalty": funding_penalty,
            "final": round(final, 2),
            "direction": direction,
        }

        log.debug(f"Score: base={base_score:.2f} mtf=+{mtf_bonus} funding=-{funding_penalty} "
                  f"→ {final:.2f} ({direction})")

        return round(final, 1), direction, breakdown

    def _weighted_score(self, scores: Dict[str, float], weights: dict) -> Tuple[float, str]:
        """
        Compute weighted sum, return (abs_score_0_to_10, direction).

        Args:
            scores: {indicator_name: score (-1 to 1)}
            weights: {indicator_name: weight (0-100)}

        Returns:
            (confidence: 0-10, direction: 'long'|'short')
        """
        if not scores:
            return 0.0, "long"

        weighted_sum = 0.0
        total_weight = 0.0

        for name, weight in weights.items():
            if name in scores:
                weighted_sum += scores[name] * weight
                total_weight += weight

        if total_weight == 0:
            return 0.0, "long"

        # Normalize to -1..+1
        normalized = weighted_sum / total_weight

        direction = "long" if normalized >= 0 else "short"
        confidence = abs(normalized) * 10.0  # 0-10

        return confidence, direction
