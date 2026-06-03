"""
api/routes/positions.py
Live position data and manual close endpoint.
"""

from fastapi import APIRouter, HTTPException
from bot.main import bot, bot_state

router = APIRouter(tags=["Positions"])


@router.get("/positions")
def get_positions():
    """Return current open positions from Bybit + our internal records."""
    if not bot.client:
        return {"positions": []}

    bybit_positions = bot.client.get_positions()
    records = bot.positions.get_all_records() if bot.positions else {}

    enriched = []
    for p in bybit_positions:
        symbol = p["symbol"]
        rec = records.get(symbol, {})
        enriched.append({
            "symbol":       symbol,
            "side":         p.get("side"),
            "direction":    "long" if p.get("side") == "Buy" else "short",
            "size":         float(p.get("size", 0)),
            "entry_price":  float(p.get("avgPrice", 0)),
            "mark_price":   float(p.get("markPrice", 0)),
            "leverage":     p.get("leverage"),
            "pnl":          float(p.get("unrealisedPnl", 0)),
            "pnl_pct":      float(p.get("unrealisedPnl", 0)) /
                            max(float(rec.get("position_usd", 1)), 0.01) * 100,
            "sl_price":     float(p.get("stopLoss", 0)),
            "tp1_price":    rec.get("tp1_price", 0),
            "tp2_price":    rec.get("tp2_price", 0),
            "tp1_hit":      rec.get("tp1_hit", False),
            "trailing_on":  rec.get("trailing_active", False),
            "confidence":   rec.get("confidence", 0),
            "position_usd": rec.get("position_usd", 0),
        })

    return {"positions": enriched}


@router.post("/positions/{symbol}/close")
def close_position(symbol: str):
    """Manually close a position and trigger 1h cooldown."""
    symbol = symbol.upper()
    if not bot.client:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    position = bot.client.get_position(symbol)
    if not position:
        raise HTTPException(status_code=404, detail=f"No open position for {symbol}")

    rec = bot.positions.get_record(symbol) if bot.positions else {}
    ok = bot.orders.close_position(symbol, position)

    if ok:
        # Run PnL recording in background thread so API responds immediately
        # (_on_position_closed waits 2s for Bybit to settle before querying PnL)
        import threading
        def _record():
            bot._on_position_closed(symbol, position, rec, "manual")
            if bot.positions:
                bot.positions.remove_record(symbol)
        threading.Thread(target=_record, daemon=True).start()
        return {"ok": True, "message": f"{symbol} closed, 1h cooldown set"}

    raise HTTPException(status_code=500, detail=f"Failed to close {symbol}")
