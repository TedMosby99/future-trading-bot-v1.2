"""
api/routes/stats.py
Trade history, performance statistics, scanner info, and log polling.
"""

import datetime
from fastapi import APIRouter, Query
from typing import Optional
from bot.main import bot, bot_state, log_buffer, log_buffer_lock

router = APIRouter(tags=["Stats"])


@router.get("/stats/summary")
def get_summary():
    if not bot.tracker:
        return {}
    return bot.tracker.get_summary()


@router.get("/stats/trades")
def get_trades(
    limit: int = Query(100, le=500),
    symbol: Optional[str] = None,
):
    if not bot.tracker:
        return {"trades": []}
    trades = bot.tracker.get_trades(limit=limit, symbol=symbol)
    return {"trades": trades}


@router.get("/stats/pairs")
def get_pair_stats():
    if not bot.tracker:
        return {"pairs": []}
    return {"pairs": bot.tracker.get_pair_stats()}


@router.get("/scanner/last-run")
def scanner_last_run():
    return {
        "pairs":     bot_state.last_scan_pairs,
        "count":     len(bot_state.last_scan_pairs),
        "timestamp": bot_state.last_scan_time.isoformat() if bot_state.last_scan_time else None,
    }


@router.get("/balance")
def get_balance():
    if not bot.client:
        return {"balance": None}
    balance = bot.client.get_balance()
    return {"balance": balance}


@router.get("/logs")
def get_logs(since: int = Query(0, description="Return logs after this index")):
    """
    Poll-based log endpoint.
    Client sends the index of the last log it received.
    Returns new logs since that index.
    """
    with log_buffer_lock:
        total = len(log_buffer)
        start = max(0, since)
        new_logs = log_buffer[start:] if start < total else []
        return {
            "logs":  new_logs,
            "total": total,
            "next":  total,
        }


@router.get("/stats/analysis")
def get_full_analysis():
    """Full stats analysis: confidence, direction, time, pairs."""
    if not bot.tracker:
        return {}
    return {
        "confidence": bot.tracker.get_confidence_stats(),
        "direction":  bot.tracker.get_direction_stats(),
        "time":       bot.tracker.get_time_stats(),
        "pairs":      bot.tracker.get_pair_detail_stats(),
    }
