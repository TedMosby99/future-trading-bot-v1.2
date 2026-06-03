"""
bot/market_data.py
Fetches OHLCV data from Bybit and returns pandas DataFrames.
Timeframes: '15' (15m), '60' (1h), '240' (4h).
"""

import logging
from typing import Optional
import pandas as pd
from bot.bybit_client import BybitClient

log = logging.getLogger("MARKET_DATA")

INTERVAL_LABELS = {
    "15": "15m",
    "60": "1h",
    "240": "4h",
}


class MarketData:
    """Fetches and structures OHLCV data for indicator calculation."""

    def __init__(self, client: BybitClient):
        self.client = client

    def fetch(self, symbol: str, interval: str, limit: int = 200) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data for symbol/interval.

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume, turnover
            Sorted oldest-first. Returns None on failure.
        """
        raw = self.client.get_kline(symbol, interval, limit)
        if not raw or len(raw) < 20:
            log.warning(f"Insufficient kline data for {symbol}/{interval} ({len(raw)} bars)")
            return None

        try:
            df = pd.DataFrame(
                raw,
                columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"]
            )
            df = df.astype({
                "open": float,
                "high": float,
                "low": float,
                "close": float,
                "volume": float,
            })
            df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ms")
            df = df.sort_values("timestamp").reset_index(drop=True)
            return df

        except Exception as e:
            log.error(f"fetch {symbol}/{interval} parse error: {e}")
            return None

    def fetch_all_timeframes(self, symbol: str) -> dict:
        """
        Fetch 15m, 1h, and 4h data in one call.

        Returns:
            {'15m': df, '1h': df, '4h': df} — any may be None if fetch fails
        """
        return {
            "15m": self.fetch(symbol, "15", 200),
            "1h":  self.fetch(symbol, "60", 100),
            "4h":  self.fetch(symbol, "240", 100),
        }
