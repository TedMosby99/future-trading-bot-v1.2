"""
api/routes/settings.py
Settings read/update/reset and blacklist management.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List
from config import load_settings, save_settings, DEFAULT_SETTINGS, load_blacklist, save_blacklist

router = APIRouter(tags=["Settings"])


class SettingsPayload(BaseModel):
    settings: Dict[str, Any]


class BlacklistAdd(BaseModel):
    symbol: str


@router.get("/settings")
def get_settings():
    return load_settings()


@router.put("/settings")
def update_settings(payload: SettingsPayload):
    current = load_settings()
    current.update(payload.settings)
    if "weights" in payload.settings:
        current["weights"] = {**DEFAULT_SETTINGS["weights"], **payload.settings["weights"]}
    ok = save_settings(current)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save settings")
    return {"ok": True, "settings": current}


@router.post("/settings/reset")
def reset_settings():
    ok = save_settings(DEFAULT_SETTINGS.copy())
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to reset settings")
    return {"ok": True, "settings": DEFAULT_SETTINGS}


# ── Blacklist ──────────────────────────────────────────────────────────────

@router.get("/blacklist")
def get_blacklist():
    return {"blacklist": load_blacklist()}


@router.post("/blacklist")
def add_to_blacklist(payload: BlacklistAdd):
    symbol = payload.symbol.upper().strip()
    if not symbol.endswith("USDT"):
        symbol = symbol + "USDT"
    bl = load_blacklist()
    if symbol not in bl:
        bl.append(symbol)
        save_blacklist(bl)
    # Also update settings
    s = load_settings()
    if symbol not in s.get("blacklist", []):
        s.setdefault("blacklist", []).append(symbol)
        save_settings(s)
    return {"ok": True, "blacklist": bl}


@router.delete("/blacklist/{symbol}")
def remove_from_blacklist(symbol: str):
    symbol = symbol.upper()
    bl = load_blacklist()
    bl = [s for s in bl if s != symbol]
    save_blacklist(bl)
    # Also update settings
    s = load_settings()
    s["blacklist"] = [x for x in s.get("blacklist", []) if x != symbol]
    save_settings(s)
    return {"ok": True, "blacklist": bl}
