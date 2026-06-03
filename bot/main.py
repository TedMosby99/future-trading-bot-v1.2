"""
bot/main.py
Core orchestrator. Owns:
    - BotState (shared state imported by API routes)
    - log_buffer (shared log ring buffer)
    - TradingBot class (all trading logic threads)
    - Global `bot` instance

API routes import: from bot.main import bot, bot_state, log_buffer
"""

import logging
import threading
import time
import datetime
from typing import Optional, Dict, List
from queue import Queue, Empty

from config import load_settings, save_settings
from bot.bybit_client import BybitClient
from bot.scanner import Scanner
from bot.market_data import MarketData
from bot.indicators import IndicatorEngine
from bot.regime_filter import RegimeFilter
from bot.funding_monitor import FundingMonitor
from bot.scorer import Scorer
from bot.risk_manager import RiskManager
from bot.order_manager import OrderManager
from bot.position_manager import PositionManager
from bot.trade_tracker import TradeTracker

# ── Shared log buffer (API polls this) ─────────────────────────────────────

log_buffer: List[dict] = []
log_buffer_lock = threading.Lock()
MAX_LOG_BUFFER = 600


class _BufferHandler(logging.Handler):
    def emit(self, record):
        try:
            entry = {
                "ts": datetime.datetime.utcnow().strftime("%H:%M:%S"),
                "level": record.levelname,
                "msg": self.format(record),
            }
            with log_buffer_lock:
                log_buffer.append(entry)
                if len(log_buffer) > MAX_LOG_BUFFER:
                    log_buffer.pop(0)
        except Exception:
            pass


def _setup_logging(level: str = "INFO"):
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not root.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("[%(name)-12s] %(message)s"))
        root.addHandler(ch)
    bh = _BufferHandler()
    bh.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    root.addHandler(bh)


_setup_logging()
log = logging.getLogger("BOT")


# ── Shared bot state ────────────────────────────────────────────────────────

class BotState:
    def __init__(self):
        self.running: bool = False
        self.paused: bool = False
        self.pause_reason: Optional[str] = None
        self.pause_until: Optional[datetime.datetime] = None
        self.loss_streak: int = 0
        self.post_resume_losses: int = 0
        self.is_post_resume: bool = False
        self.cooldown_pairs: Dict[str, datetime.datetime] = {}
        self.auto_blacklist: Dict[str, datetime.datetime] = {}
        self.last_scan_pairs: List[str] = []
        self.last_scan_time: Optional[datetime.datetime] = None
        self.last_cycle_time: Optional[datetime.datetime] = None
        self.start_time: Optional[datetime.datetime] = None
        self._lock = threading.Lock()

    @property
    def uptime(self) -> str:
        if not self.start_time:
            return "—"
        delta = datetime.datetime.utcnow() - self.start_time
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        return f"{h}h {m:02d}m {s:02d}s"

    @property
    def status(self) -> str:
        if not self.running:
            return "stopped"
        if self.paused:
            return "paused"
        return "running"

    def pause(self, reason: str, hours: float):
        self.paused = True
        self.pause_reason = reason
        self.pause_until = datetime.datetime.utcnow() + datetime.timedelta(hours=hours)
        log.warning(f"Bot paused: {reason} — resumes in {hours}h")

    def resume(self):
        self.paused = False
        self.pause_reason = None
        self.pause_until = None
        log.info("Bot resumed")

    def check_pause_expiry(self):
        if self.paused and self.pause_until:
            if datetime.datetime.utcnow() >= self.pause_until:
                self.is_post_resume = True
                self.post_resume_losses = 0
                self.resume()

    def pause_seconds_remaining(self) -> int:
        if not self.paused or not self.pause_until:
            return 0
        delta = self.pause_until - datetime.datetime.utcnow()
        return max(0, int(delta.total_seconds()))

    def get_active_blacklist(self) -> Dict[str, str]:
        now = datetime.datetime.utcnow()
        return {
            sym: dt.isoformat()
            for sym, dt in self.auto_blacklist.items()
            if dt > now
        }

    def get_active_cooldowns(self) -> Dict[str, str]:
        now = datetime.datetime.utcnow()
        return {
            sym: dt.isoformat()
            for sym, dt in self.cooldown_pairs.items()
            if dt > now
        }

    def clean_expired(self):
        now = datetime.datetime.utcnow()
        self.cooldown_pairs = {k: v for k, v in self.cooldown_pairs.items() if v > now}
        self.auto_blacklist = {k: v for k, v in self.auto_blacklist.items() if v > now}


bot_state = BotState()


# ── Trading Bot ─────────────────────────────────────────────────────────────

class TradingBot:

    def __init__(self):
        self.state = bot_state
        self.settings: dict = {}
        self.client: Optional[BybitClient] = None
        self.scanner: Optional[Scanner] = None
        self.market_data: Optional[MarketData] = None
        self.indicators: Optional[IndicatorEngine] = None
        self.regime: Optional[RegimeFilter] = None
        self.funding: Optional[FundingMonitor] = None
        self.scorer: Optional[Scorer] = None
        self.risk: Optional[RiskManager] = None
        self.orders: Optional[OrderManager] = None
        self.positions: Optional[PositionManager] = None
        self.tracker: Optional[TradeTracker] = None
        # track open trade DB ids: {symbol: trade_id}
        self._trade_ids: Dict[str, int] = {}

    # ── Lifecycle ───────────────────────────────────────────────────────

    def start(self) -> tuple:
        if self.state.running:
            return False, "Already running"
        try:
            self.settings = load_settings()
            self._init_modules()

            if not self.client.test_connection():
                return False, "Cannot connect to Bybit API. Check .env credentials."

            # Recover any open trades from DB that were open before shutdown
            self._recover_open_trades()

            self.state.running = True
            self.state.start_time = datetime.datetime.utcnow()
            self.state.loss_streak = 0
            self.state.is_post_resume = False

            threading.Thread(target=self._main_loop,    daemon=True, name="bot-main").start()
            threading.Thread(target=self._monitor_loop, daemon=True, name="bot-monitor").start()

            log.info("Bot started ✓")
            return True, "Bot started"
        except Exception as e:
            self.state.running = False
            log.error(f"Start failed: {e}", exc_info=True)
            return False, str(e)

    def stop(self) -> tuple:
        self.state.running = False
        self.state.paused = False
        log.info("Bot stopped by user")
        return True, "Bot stopped"

    def pause_manual(self) -> tuple:
        if not self.state.running:
            return False, "Bot not running"
        self.state.paused = True
        self.state.pause_reason = "Manual pause"
        self.state.pause_until = None
        log.info("Bot paused manually")
        return True, "Bot paused"

    def resume_manual(self) -> tuple:
        self.state.resume()
        return True, "Bot resumed"

    def _init_modules(self):
        s = self.settings
        self.client   = BybitClient(s)
        self.scanner  = Scanner(self.client, s)
        self.market_data = MarketData(self.client)
        self.indicators  = IndicatorEngine()
        self.regime      = RegimeFilter(s)
        self.funding     = FundingMonitor(self.client)
        self.scorer      = Scorer(s)
        self.risk        = RiskManager(self.client, s)
        self.orders      = OrderManager(self.client, s)
        self.positions   = PositionManager(self.client)
        self.tracker     = TradeTracker()

    # ── Main loop (15m candle-aligned) ──────────────────────────────────

    def _main_loop(self):
        log.info("[MAIN] Loop started")
        while self.state.running:
            try:
                self.state.check_pause_expiry()
                self.state.clean_expired()

                if not self.state.paused:
                    self._run_cycle()

                sleep_secs = self._seconds_to_next_candle(15)
                log.info(f"[MAIN] Next cycle in {sleep_secs:.0f}s")
                self._interruptible_sleep(sleep_secs)

            except Exception as e:
                log.error(f"[MAIN] Unhandled error: {e}", exc_info=True)
                time.sleep(30)

    def _run_cycle(self):
        self.settings = load_settings()  # hot-reload settings
        self.state.last_cycle_time = datetime.datetime.utcnow()
        log.info("[CYCLE] ── Starting new cycle ──")

        balance = self.client.get_balance()
        if balance is None:
            log.error("[CYCLE] Cannot get balance — skipping")
            return

        log.info(f"[CYCLE] Balance: ${balance:.2f} USDT")

        # Sync current positions first
        self.positions.sync()

        # Get blacklist + cooldowns
        manual_bl  = self.settings.get("blacklist", [])
        auto_bl    = {k: v for k, v in self.state.auto_blacklist.items()
                      if v > datetime.datetime.utcnow()}
        cooldowns  = {k: v for k, v in self.state.cooldown_pairs.items()
                      if v > datetime.datetime.utcnow()}

        pairs = self.scanner.get_top_pairs(
            blacklist=manual_bl,
            auto_blacklist=auto_bl,
            cooldown_pairs=cooldowns,
        )
        self.state.last_scan_pairs = pairs
        self.state.last_scan_time  = datetime.datetime.utcnow()

        for symbol in pairs:
            if not self.state.running or self.state.paused:
                break
            if self.orders.has_pending_order(symbol):
                log.debug(f"[CYCLE] {symbol}: pending order exists, skip")
                continue
            # No duplicate: skip if we already have an open position for this symbol
            if symbol in self.positions.get_all_records():
                log.debug(f"[CYCLE] {symbol}: position already open, skip")
                continue
            self._process_symbol(symbol, balance)

    def _process_symbol(self, symbol: str, balance: float):
        s = self.settings

        try:
            tfs = self.market_data.fetch_all_timeframes(symbol)
            df_15m, df_1h, df_4h = tfs["15m"], tfs["1h"], tfs["4h"]

            if df_15m is None or len(df_15m) < 55:
                return

            # Calculate indicators
            ind_15m = self.indicators.calculate_all(df_15m)
            ind_1h  = self.indicators.calculate_all(df_1h)  if df_1h  is not None else {}
            ind_4h  = self.indicators.calculate_all(df_4h)  if df_4h  is not None else {}

            raw_15m = ind_15m.get("raw", {})
            raw_1h  = ind_1h.get("raw", {})

            # Regime filter
            if not self.regime.passes(df_15m, raw_15m, s):
                log.debug(f"[CYCLE] {symbol}: regime filter fail")
                return

            # Funding modifier
            f_mod = self.funding.get_modifier(symbol, s)

            # Confidence score
            confidence, direction, breakdown = self.scorer.score(
                ind_15m, ind_1h, ind_4h, f_mod, s
            )
            log.info(f"[SCORE] {symbol}: {confidence:.1f} ({direction}) {breakdown}")

            threshold = s.get("confidence_threshold", 7.0)
            if confidence < threshold:
                return

            # ── Slot check: effective = open positions + pending (unfilled) orders ──
            # This prevents placing multiple simultaneous entries that all fill,
            # exceeding max_positions (the root cause of 7 positions instead of 3).
            open_positions = self.positions.get_open_positions()
            n_open      = len(open_positions)
            n_pending   = self.orders.pending_count()
            n_effective = n_open + n_pending
            max_pos     = s.get("max_positions", 3)

            log.info(f"[SLOT] {symbol}: {n_open} open + {n_pending} pending = {n_effective}/{max_pos}")

            if n_effective >= max_pos:
                # If pending orders are consuming slots, wait — don't replace yet
                if n_pending > 0:
                    log.info(f"[SLOT] {symbol}: {n_pending} pending orders filling slots, skip")
                    return
                # All slots filled by open positions — try replacing the worst loser
                worst = self.positions.get_worst_loser()
                if worst is None:
                    log.info(f"[SLOT] {symbol}: slots full, no losing position to replace")
                    return
                worst_sym = worst["symbol"]
                log.info(f"[SLOT] Replacing {worst_sym} (PnL={worst['unrealisedPnl']}) with {symbol}")
                worst_rec = self.positions.get_record(worst_sym)
                self.orders.close_position(worst_sym, worst)
                self._on_position_closed(worst_sym, worst, worst_rec, "Replaced")

            # ── Direction limit: include pending orders by direction ──
            open_same_dir    = sum(1 for p in open_positions
                                   if (p.get("side") == "Buy") == (direction == "long"))
            pending_same_dir = self.orders.pending_direction_count(direction)
            max_dir          = s.get("max_same_direction", 2)

            if open_same_dir + pending_same_dir >= max_dir:
                log.info(f"[SLOT] {symbol}: direction limit {direction} "
                         f"({open_same_dir} open + {pending_same_dir} pending >= {max_dir})")
                return

            # Risk calculation
            risk_params = self.risk.calculate(
                symbol, df_15m, df_1h, raw_15m, raw_1h,
                confidence, direction, balance, s
            )
            if risk_params is None:
                return

            # Place entry
            order_id = self.orders.place_entry(
                symbol, direction, risk_params, s,
                on_fill=self._on_fill,
                on_cancel=self._on_limit_cancel,
            )
            if order_id:
                log.info(f"[ENTRY] {symbol}: order placed {order_id}")

        except Exception as e:
            log.error(f"[CYCLE] {symbol} error: {e}", exc_info=True)

    # ── Monitor loop (every 30s) ────────────────────────────────────────

    def _monitor_loop(self):
        log.info("[MONITOR] Loop started")
        while self.state.running:
            try:
                self._monitor_positions()  # Always runs — even when paused
            except Exception as e:
                log.error(f"[MONITOR] Error: {e}", exc_info=True)
            time.sleep(30)

    def _monitor_positions(self):
        open_positions = self.positions.sync()
        s = self.settings

        # Build map for quick lookup
        open_map = {p["symbol"]: p for p in open_positions}
        open_syms = set(open_map.keys())

        # Detect closed positions
        for symbol, rec in list(self.positions.get_all_records().items()):
            if symbol not in open_syms:
                bybit_pos = {"symbol": symbol, "side": rec.get("side", "Buy"),
                             "size": "0", "unrealisedPnl": "0",
                             "markPrice": str(rec.get("entry_price", 0))}
                self._on_position_closed(symbol, bybit_pos, rec, "tp_sl_or_manual")
                self.positions.remove_record(symbol)
                continue

            bybit_pos = open_map[symbol]

            # TP1 detection
            if self.positions.check_tp1_hit(symbol):
                log.info(f"[MONITOR] {symbol}: TP1 hit -> moving SL to breakeven")
                be = rec.get("be_price", rec.get("entry_price"))
                self.orders.move_sl_to_breakeven(symbol, be)

            # Breakeven trigger
            if s.get("breakeven_enabled", True):
                if self.positions.check_breakeven_trigger(symbol):
                    be = rec.get("be_price", rec.get("entry_price"))
                    self.orders.move_sl_to_breakeven(symbol, be)

            # Trailing stop trigger
            if s.get("trailing_stop_enabled", True):
                if self.positions.check_trailing_trigger(symbol):
                    self.orders.activate_trailing_stop(
                        symbol,
                        rec.get("trailing_dist", 0),
                        rec.get("trail_activation", 0),
                    )

            # Funding cost tracking
            self.funding.update_cost(bybit_pos, s)

    # ── Callbacks ───────────────────────────────────────────────────────

    def _on_fill(self, symbol: str, params: dict):
        """Called when entry order fills."""
        log.info(f"[FILL] {symbol}: entry filled → setting up exit orders")
        self.positions.register_open(symbol, params)
        self.orders.setup_exit_orders(symbol, params, self.settings)

        trade_id = self.tracker.record_open(
            symbol=symbol,
            side=params["side"],
            entry_price=params["price"],
            quantity=params["qty"],
            leverage=params["leverage"],
            position_usd=params["position_usd"],
            confidence=params["confidence"],
        )
        self._trade_ids[symbol] = trade_id

    def _on_limit_cancel(self, symbol: str, params: dict):
        """Called when limit order times out. Re-evaluate and potentially market-enter."""
        log.info(f"[TIMEOUT] {symbol}: limit timed out, re-evaluating…")
        s = self.settings
        # Re-fetch and re-score
        try:
            df_15m = self.market_data.fetch(symbol, "15", 200)
            if df_15m is None:
                return
            ind = self.indicators.calculate_all(df_15m)
            f_mod = self.funding.get_modifier(symbol, s)
            confidence, direction, _ = self.scorer.score(ind, {}, {}, f_mod, s)
            if confidence >= s.get("confidence_threshold", 7.0):
                log.info(f"[TIMEOUT] {symbol}: re-score {confidence:.1f} still valid → market entry")
                # Force market entry by temporarily overriding entry_type in a copy
                market_settings = {**s, "entry_type": "market"}
                self.orders.place_entry(symbol, direction, params, market_settings,
                                        on_fill=self._on_fill)
        except Exception as e:
            log.error(f"[TIMEOUT] {symbol} re-score error: {e}")

    def _on_position_closed(self, symbol: str, position: dict, rec: Optional[dict], reason: str):
        """Handle any position close — get PnL, record, update streaks."""
        import time as _time

        mark_price = float(position.get("markPrice", 0))
        unrealised = float(position.get("unrealisedPnl", 0))

        # For manual closes: wait 2s for Bybit to settle before querying closed PnL
        pnl        = unrealised  # immediate fallback
        exit_price = mark_price

        if reason == "Manual":
            _time.sleep(2)

        closed_records = self.client.get_closed_pnl(symbol, limit=5)
        for cr in closed_records:
            try:
                settled_pnl  = float(cr.get("closedPnl", 0))
                settled_exit = float(cr.get("avgExitPrice", 0))
                if settled_exit > 0:
                    pnl        = settled_pnl
                    exit_price = settled_exit
                    break
            except Exception:
                pass

        # Determine the actual close reason when it was exchange-triggered (TP or SL)
        if reason == "tp_sl_or_manual":
            reason = self._resolve_close_reason(pnl, exit_price, rec)

        trade_id     = self._trade_ids.pop(symbol, -1)
        position_usd = float(rec.get("position_usd", 1)) if rec else 1
        tp1_hit      = rec.get("tp1_hit", False) if rec else False
        pnl_pct      = (pnl / position_usd * 100) if position_usd > 0 else 0

        log.info(f"[CLOSE] {symbol} reason={reason} pnl={pnl:.4f} exit={exit_price}")

        if trade_id > 0:
            self.tracker.record_close(
                trade_id=trade_id,
                symbol=symbol,
                exit_price=exit_price,
                pnl=pnl,
                pnl_pct=pnl_pct,
                close_reason=reason,
                tp1_hit=tp1_hit,
            )

        self.funding.clear(symbol)
        is_loss = pnl <= 0  # breakeven counts as loss

        if is_loss:
            self.state.loss_streak += 1
            log.warning(f"[STREAK] Loss #{self.state.loss_streak} — {symbol} PnL={pnl:.4f}")
            self._check_streak()
        else:
            self.state.loss_streak = 0
            if self.state.is_post_resume:
                self.state.post_resume_losses = 0

        # Per-pair auto-blacklist
        self.tracker.check_auto_blacklist(symbol, self.state, self.settings)

        # If manually closed: cooldown
        if reason == "Manual":
            self._handle_manual_close(symbol)


    def _resolve_close_reason(self, pnl: float, exit_price: float, rec: Optional[dict]) -> str:
        """
        Determine whether a position closed via TP1, TP2, SL, or breakeven.
        Compares exit price against our known levels (within 0.15% tolerance),
        falls back to PnL sign if no level matches.
        """
        if rec and exit_price > 0:
            def near(level):
                if not level or level == 0:
                    return False
                return abs(exit_price - level) / level < 0.0015  # 0.15% tolerance

            if near(rec.get("tp1_price")):
                return "TP1"
            if near(rec.get("tp2_price")):
                return "TP2"
            if near(rec.get("sl_price")) or near(rec.get("be_price")):
                return "SL"

        # Fallback: use PnL direction
        if pnl > 0.001:
            return "TP"
        elif pnl < -0.001:
            return "SL"
        else:
            return "Breakeven"

    def _check_streak(self):
        s = self.settings
        if not self.state.is_post_resume:
            if self.state.loss_streak >= s.get("loss_streak_pause", 3):
                self.state.pause(
                    f"{self.state.loss_streak} consecutive losses",
                    s.get("loss_streak_pause_hours", 3)
                )
                self.state.loss_streak = 0
                self.state.is_post_resume = True
                self.state.post_resume_losses = 0
        else:
            self.state.post_resume_losses += 1
            if self.state.post_resume_losses >= s.get("post_resume_loss_limit", 2):
                self.state.pause(
                    "2 losses after resume",
                    s.get("post_resume_pause_hours", 24)
                )
                self.state.is_post_resume = False
                self.state.post_resume_losses = 0
                self.state.loss_streak = 0

    def _handle_manual_close(self, symbol: str):
        hours = self.settings.get("manual_close_cooldown_hours", 1)
        self.orders.cancel_all_orders(symbol)
        self.state.cooldown_pairs[symbol] = (
            datetime.datetime.utcnow() + datetime.timedelta(hours=hours)
        )
        log.info(f"[MANUAL] {symbol}: {hours}h cooldown set")

    # ── Utilities ───────────────────────────────────────────────────────


    def _recover_open_trades(self):
        """
        On restart: reconcile DB open trades against live Bybit positions.
        - If still open on Bybit → restore _trade_ids tracking
        - If closed while bot was offline → fetch PnL and record close
        """
        open_db = self.tracker.get_open_trades()
        if not open_db:
            return

        bybit_positions = self.client.get_positions()
        bybit_symbols = {p["symbol"] for p in bybit_positions}

        for trade in open_db:
            symbol   = trade["symbol"]
            trade_id = trade["id"]

            if symbol in bybit_symbols:
                # Still open — restore tracking
                self._trade_ids[symbol] = trade_id
                log.info(f"[RECOVER] Restored tracking: {symbol} id={trade_id}")
            else:
                # Closed while offline — fetch PnL from Bybit and record
                closed = self.client.get_closed_pnl(symbol, limit=5)
                pnl = 0.0
                exit_price = float(trade.get("entry_price") or 0)

                for cr in closed:
                    try:
                        pnl        = float(cr.get("closedPnl", 0))
                        exit_price = float(cr.get("avgExitPrice", exit_price))
                        break
                    except Exception:
                        pass

                pos_usd = float(trade.get("position_usd") or 1)
                self.tracker.record_close(
                    trade_id    = trade_id,
                    symbol      = symbol,
                    exit_price  = exit_price,
                    pnl         = pnl,
                    pnl_pct     = pnl / max(pos_usd, 0.01) * 100,
                    close_reason= "Offline",
                    tp1_hit     = False,
                )
                log.info(f"[RECOVER] {symbol} closed while offline — PnL={pnl:.4f}")

    def _interruptible_sleep(self, seconds: float):
        """Sleep in 5s chunks so stop/pause is responsive."""
        slept = 0.0
        while slept < seconds and self.state.running:
            chunk = min(5.0, seconds - slept)
            time.sleep(chunk)
            slept += chunk
            self.state.check_pause_expiry()

    @staticmethod
    def _seconds_to_next_candle(interval_minutes: int) -> float:
        now = datetime.datetime.utcnow()
        total_mins = now.minute + now.second / 60 + now.microsecond / 60_000_000
        next_mark = (int(total_mins / interval_minutes) + 1) * interval_minutes
        wait = (next_mark - total_mins) * 60 + 2  # +2s buffer
        return max(5.0, wait)


# ── Global singleton ────────────────────────────────────────────────────────
bot = TradingBot()
