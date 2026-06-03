"""
bot/trade_tracker.py
Records completed trades to SQLite and manages:
    - Per-pair win/loss statistics
    - Auto-blacklist based on recent pair performance
"""

import sqlite3
import logging
import datetime
from typing import Optional, Dict

log = logging.getLogger("TRACKER")
DB_PATH = "data/trades.db"


class TradeTracker:
    """Records trades and computes per-pair performance."""

    def record_open(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        leverage: int,
        position_usd: float,
        confidence: float,
        open_time: Optional[str] = None,
    ) -> int:
        """Insert a new open trade. Returns the trade DB id."""
        open_time = open_time or datetime.datetime.utcnow().isoformat()
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                INSERT INTO trades
                (symbol, side, entry_price, quantity, leverage, position_usd, confidence, open_time, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')
            """, (symbol, side, entry_price, quantity, leverage, position_usd, confidence, open_time))
            conn.commit()
            trade_id = c.lastrowid
            conn.close()
            log.info(f"Trade recorded: id={trade_id} {symbol} {side}")
            return trade_id
        except Exception as e:
            log.error(f"record_open error: {e}")
            return -1

    def record_close(
        self,
        trade_id: int,
        symbol: str,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        close_reason: str,
        tp1_hit: bool = False,
    ):
        """Update a trade record on close and update pair stats."""
        close_time = datetime.datetime.utcnow().isoformat()
        is_win = pnl > 0
        status = "win" if is_win else "loss"

        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                UPDATE trades
                SET exit_price=?, pnl=?, pnl_pct=?, close_time=?, close_reason=?, status=?, tp1_hit=?
                WHERE id=?
            """, (exit_price, pnl, pnl_pct, close_time, close_reason, status, int(tp1_hit), trade_id))

            # Upsert pair stats
            c.execute("""
                INSERT INTO pair_stats (symbol, total_trades, wins, losses, total_pnl, last_trade_time)
                VALUES (?, 1, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    total_trades = total_trades + 1,
                    wins         = wins + ?,
                    losses       = losses + ?,
                    total_pnl    = total_pnl + ?,
                    last_trade_time = ?
            """, (
                symbol,
                int(is_win), int(not is_win), pnl, close_time,
                int(is_win), int(not is_win), pnl, close_time,
            ))
            conn.commit()
            conn.close()
            log.info(f"Trade closed: id={trade_id} {symbol} PnL={pnl:.4f} ({close_reason})")
        except Exception as e:
            log.error(f"record_close error: {e}")

    def get_recent_pair_trades(self, symbol: str, n: int = 5) -> list:
        """Return last N closed trades for a symbol."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                SELECT status, pnl FROM trades
                WHERE symbol=? AND status IN ('win', 'loss')
                ORDER BY close_time DESC LIMIT ?
            """, (symbol, n))
            rows = c.fetchall()
            conn.close()
            return rows
        except Exception as e:
            log.error(f"get_recent_pair_trades error: {e}")
            return []

    def check_auto_blacklist(self, symbol: str, state, settings: dict):
        """
        If pair lost N out of last M trades, add to auto_blacklist for X hours.
        Modifies state.auto_blacklist in place.
        """
        if not settings.get("auto_blacklist_enabled", True):
            return

        threshold = settings.get("auto_blacklist_losses", 4)
        window    = settings.get("auto_blacklist_window", 5)
        hours     = settings.get("auto_blacklist_hours", 24)

        recent = self.get_recent_pair_trades(symbol, window)
        if len(recent) < window:
            return

        losses = sum(1 for r in recent if r[0] == "loss")
        if losses >= threshold:
            until = datetime.datetime.utcnow() + datetime.timedelta(hours=hours)
            state.auto_blacklist[symbol] = until
            log.warning(f"Auto-blacklisted {symbol}: {losses}/{window} losses → {hours}h cooldown")

    def get_summary(self) -> dict:
        """Return overall performance summary."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                SELECT
                    COUNT(*) total,
                    SUM(CASE WHEN status='win' THEN 1 ELSE 0 END) wins,
                    SUM(CASE WHEN status='loss' THEN 1 ELSE 0 END) losses,
                    COALESCE(SUM(pnl), 0) total_pnl,
                    COALESCE(MAX(pnl), 0) best_trade,
                    COALESCE(MIN(pnl), 0) worst_trade
                FROM trades WHERE status IN ('win', 'loss')
            """)
            row = c.fetchone()
            conn.close()
            total, wins, losses, total_pnl, best, worst = row
            win_rate = round((wins / total * 100) if total > 0 else 0, 1)
            return {
                "total_trades": total or 0,
                "wins": wins or 0,
                "losses": losses or 0,
                "win_rate": win_rate,
                "total_pnl": round(total_pnl or 0, 4),
                "best_trade": round(best or 0, 4),
                "worst_trade": round(worst or 0, 4),
            }
        except Exception as e:
            log.error(f"get_summary error: {e}")
            return {}

    def get_trades(self, limit: int = 100, symbol: Optional[str] = None) -> list:
        """Return trade history."""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            if symbol:
                c.execute("SELECT * FROM trades WHERE symbol=? ORDER BY open_time DESC LIMIT ?",
                          (symbol, limit))
            else:
                c.execute("SELECT * FROM trades ORDER BY open_time DESC LIMIT ?", (limit,))
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            log.error(f"get_trades error: {e}")
            return []

    def get_pair_stats(self) -> list:
        """Return per-pair performance stats."""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM pair_stats ORDER BY total_pnl DESC")
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            log.error(f"get_pair_stats error: {e}")
            return []

    def get_open_trades(self) -> list:
        """Return all trades still marked open in DB (for restart reconciliation)."""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM trades WHERE status='open'")
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            log.error(f"get_open_trades error: {e}")
            return []

    def get_confidence_stats(self) -> list:
        """WR and PnL grouped by confidence score range."""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT
                    CASE
                        WHEN confidence >= 7.0 AND confidence < 7.5 THEN '7.0-7.5'
                        WHEN confidence >= 7.5 AND confidence < 8.0 THEN '7.5-8.0'
                        WHEN confidence >= 8.0 AND confidence < 8.5 THEN '8.0-8.5'
                        WHEN confidence >= 8.5 AND confidence < 9.0 THEN '8.5-9.0'
                        WHEN confidence >= 9.0               THEN '9.0-10.0'
                        ELSE 'other'
                    END as range,
                    COUNT(*) as total,
                    SUM(CASE WHEN status='win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN status='loss' THEN 1 ELSE 0 END) as losses,
                    ROUND(AVG(pnl), 4) as avg_pnl,
                    ROUND(SUM(pnl), 4) as total_pnl
                FROM trades WHERE status IN ('win','loss') AND confidence IS NOT NULL
                GROUP BY range ORDER BY range
            """)
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            for r in rows:
                r['win_rate'] = round(r['wins'] / r['total'] * 100, 1) if r['total'] > 0 else 0
            return rows
        except Exception as e:
            log.error(f"get_confidence_stats error: {e}")
            return []

    def get_direction_stats(self) -> list:
        """WR and PnL for long (Buy) vs short (Sell)."""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT side,
                    COUNT(*) as total,
                    SUM(CASE WHEN status='win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN status='loss' THEN 1 ELSE 0 END) as losses,
                    ROUND(SUM(pnl), 4) as total_pnl,
                    ROUND(AVG(pnl), 4) as avg_pnl,
                    ROUND(MAX(pnl), 4) as best_pnl,
                    ROUND(MIN(pnl), 4) as worst_pnl
                FROM trades WHERE status IN ('win','loss')
                GROUP BY side
            """)
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            for r in rows:
                r['win_rate'] = round(r['wins'] / r['total'] * 100, 1) if r['total'] > 0 else 0
                r['direction'] = 'Long' if r['side'] == 'Buy' else 'Short'
            return rows
        except Exception as e:
            log.error(f"get_direction_stats error: {e}")
            return []

    def get_time_stats(self) -> list:
        """WR and PnL grouped by UTC hour of trade open."""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT
                    CAST(SUBSTR(open_time, 12, 2) AS INTEGER) as hour,
                    COUNT(*) as total,
                    SUM(CASE WHEN status='win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN status='loss' THEN 1 ELSE 0 END) as losses,
                    ROUND(AVG(pnl), 4) as avg_pnl,
                    ROUND(SUM(pnl), 4) as total_pnl
                FROM trades WHERE status IN ('win','loss')
                GROUP BY hour ORDER BY hour
            """)
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            for r in rows:
                r['win_rate'] = round(r['wins'] / r['total'] * 100, 1) if r['total'] > 0 else 0
            return rows
        except Exception as e:
            log.error(f"get_time_stats error: {e}")
            return []

    def get_pair_detail_stats(self) -> list:
        """Detailed per-pair stats including avg confidence and PnL."""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT symbol,
                    COUNT(*) as total,
                    SUM(CASE WHEN status='win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN status='loss' THEN 1 ELSE 0 END) as losses,
                    ROUND(SUM(pnl), 4) as total_pnl,
                    ROUND(AVG(pnl), 4) as avg_pnl,
                    ROUND(AVG(confidence), 2) as avg_confidence,
                    ROUND(MAX(pnl), 4) as best_pnl,
                    ROUND(MIN(pnl), 4) as worst_pnl
                FROM trades WHERE status IN ('win','loss')
                GROUP BY symbol ORDER BY total_pnl DESC
            """)
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            for r in rows:
                r['win_rate'] = round(r['wins'] / r['total'] * 100, 1) if r['total'] > 0 else 0
            return rows
        except Exception as e:
            log.error(f"get_pair_detail_stats error: {e}")
            return []
