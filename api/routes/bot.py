"""
api/routes/bot.py
Bot control endpoints: start, stop, pause, resume, status.
"""

import datetime
import os
from fastapi import APIRouter
from bot.main import bot, bot_state

router = APIRouter(tags=["Bot Control"])


@router.get("/status")
def get_status():
    s = bot_state
    demo    = os.getenv("BYBIT_DEMO", "true").lower() == "true"
    testnet = os.getenv("BYBIT_TESTNET", "false").lower() == "true"
    mode    = "DEMO" if demo else ("TESTNET" if testnet else "LIVE")
    return {
        "status":          s.status,
        "running":         s.running,
        "paused":          s.paused,
        "pause_reason":    s.pause_reason,
        "pause_remaining": s.pause_seconds_remaining(),
        "uptime":          s.uptime,
        "start_time":      s.start_time.isoformat() if s.start_time else None,
        "loss_streak":     s.loss_streak,
        "is_post_resume":  s.is_post_resume,
        "last_cycle":      s.last_cycle_time.isoformat() if s.last_cycle_time else None,
        "last_scan_time":  s.last_scan_time.isoformat() if s.last_scan_time else None,
        "last_scan_pairs": s.last_scan_pairs,
        "cooldowns":       s.get_active_cooldowns(),
        "auto_blacklist":  s.get_active_blacklist(),
        "mode":            mode,
    }


@router.post("/start")
def start_bot():
    ok, msg = bot.start()
    return {"ok": ok, "message": msg}


@router.post("/stop")
def stop_bot():
    ok, msg = bot.stop()
    return {"ok": ok, "message": msg}


@router.post("/pause")
def pause_bot():
    ok, msg = bot.pause_manual()
    return {"ok": ok, "message": msg}


@router.post("/resume")
def resume_bot():
    ok, msg = bot.resume_manual()
    return {"ok": ok, "message": msg}


@router.get("/status/exchange")
def exchange_status():
    """Test Bybit API connectivity."""
    if not bot.client:
        return {"connected": False, "message": "Bot not initialized"}
    ok = bot.client.test_connection()
    demo    = os.getenv("BYBIT_DEMO", "true").lower() == "true"
    testnet = os.getenv("BYBIT_TESTNET", "false").lower() == "true"
    mode    = "DEMO" if demo else ("TESTNET" if testnet else "LIVE")
    return {"connected": ok, "mode": mode}
