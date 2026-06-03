# CONFIG.md — All Settings Reference

All settings live in `data/settings.json` and are editable via the web UI (Settings tab).
Settings are hot-reloaded each trading cycle — no restart needed.

---

## Signal & Scanning

**confidence_threshold**
- Type: float | Default: 7.0 | Range: 1.0–10.0
- Minimum confidence score required to open a trade.
- Lower = more trades, lower quality. Recommended 7–8 for live.

**scan_top_n**
- Type: int | Default: 15 | Range: 5–30
- How many top pairs to scan per cycle (sorted by 24H USDT turnover).

**adx_threshold**
- Type: float | Default: 20.0 | Range: 10–40
- Minimum ADX value to consider a market as trending.
- ADX < threshold = pair skipped entirely. Lower for more trades, higher for quality.

---

## Position Limits

**max_positions**
- Type: int | Default: 3 | Range: 1–10
- Maximum concurrent open positions.

**max_same_direction**
- Type: int | Default: 2 | Range: 1–5
- Maximum positions in the same direction (long or short) simultaneously.

**base_trade_pct**
- Type: float | Default: 0.10 | Range: 0.01–0.50
- Base position size as fraction of capital (0.10 = 10%).
- At confidence_threshold, this is the exact size used.

**max_trade_pct**
- Type: float | Default: 0.14 | Range: 0.01–0.50
- Maximum position size as fraction of capital (0.14 = 14%).
- Reached at confidence = 10.

**min_trade_usd**
- Type: float | Default: 5.0
- Hard floor on position size in USD. Never trades smaller than this.

**max_trade_usd**
- Type: float | Default: 500.0
- Hard ceiling on position size in USD.

---

## Leverage

**leverage_mode**
- Type: string | Default: "dynamic" | Options: "dynamic", "fixed"
- dynamic: leverage calculated from ATR-based projected move.
- fixed: always uses fixed_leverage value.

**fixed_leverage**
- Type: int | Default: 5 | Range: 1–15
- Used only when leverage_mode = "fixed".

**leverage_cap**
- Type: int | Default: 10 | Range: 1–15
- Hard ceiling on dynamic leverage. Dynamic formula can never exceed this.

**leverage_target_return**
- Type: float | Default: 30.0 | Range: 10–100
- Target return % per trade used in dynamic leverage formula.
- Formula: leverage = round(leverage_target_return / projected_move_pct)

---

## Risk / Reward

**rr_ratio**
- Type: float | Default: 3.0 | Options: 2.0, 3.0 (or any float)
- Risk:Reward ratio for TP2 (final target).
- TP2_distance = SL_distance × rr_ratio

**tp1_rr**
- Type: float | Default: 1.5
- Risk:Reward ratio for TP1 (partial close target).
- TP1_distance = SL_distance × tp1_rr

**tp1_size_pct**
- Type: float | Default: 0.50 | Range: 0.1–0.9
- Fraction of position to close at TP1. 0.5 = close 50% at TP1.

**atr_sl_multiplier**
- Type: float | Default: 1.5 | Range: 0.5–5.0
- Stop loss distance = ATR(14) × this multiplier.

**max_sl_pct**
- Type: float | Default: 5.0 | Range: 0.5–20.0
- Maximum stop loss as % of entry price. Caps the SL distance.

**max_tp_pct**
- Type: float | Default: 20.0 | Range: 1.0–100.0
- Maximum take profit as % of entry price. Caps the TP distance.

---

## Trailing & Breakeven

**trailing_stop_enabled**
- Type: bool | Default: true
- Enable Bybit native trailing stop on remaining position after TP1.

**trailing_activation_pct**
- Type: float | Default: 1.0
- Activate trailing stop when profit reaches this % of entry price.

**trailing_distance_pct**
- Type: float | Default: 0.8
- Trailing stop distance as % of current price.

**breakeven_enabled**
- Type: bool | Default: true
- Move SL to entry price when profit reaches breakeven_activation_rr × SL_distance.

**breakeven_activation_rr**
- Type: float | Default: 1.0
- Trigger breakeven when price moves X × SL_distance in our favor.

---

## Order Settings

**entry_type**
- Type: string | Default: "limit" | Options: "limit", "market", "smart"
- limit: try limit order first, timeout after limit_timeout_seconds then re-evaluate
- market: always use market orders
- smart: limit with fallback to market if re-score still valid after timeout

**limit_timeout_seconds**
- Type: int | Default: 300 (5 minutes) | Range: 30–3600
- How long to wait for limit order to fill before cancelling and re-evaluating.

---

## Loss Streak Protection

**loss_streak_pause**
- Type: int | Default: 3
- Number of consecutive losses before first automatic pause.

**loss_streak_pause_hours**
- Type: float | Default: 3.0
- Duration of first pause in hours.

**post_resume_loss_limit**
- Type: int | Default: 2
- Consecutive losses after first resume before 24h pause triggers.

**post_resume_pause_hours**
- Type: float | Default: 24.0
- Duration of second (extended) pause in hours.

**manual_close_cooldown_hours**
- Type: float | Default: 1.0
- Cooldown applied to a pair after user manually closes its position.

---

## Indicator Weights

All weights are relative. Higher weight = more influence on confidence score.

| Key | Default | Description |
|---|---|---|
| weights.ema_cross | 20 | EMA 20/50 crossover |
| weights.macd | 20 | MACD histogram |
| weights.volume | 20 | Volume vs 20-period average |
| weights.rsi | 15 | RSI(14) |
| weights.adx | 15 | ADX direction and strength |
| weights.bbands | 10 | Bollinger Band position |

---

## Session Filter

**session_filter_enabled**
- Type: bool | Default: false
- Only trade within allowed UTC hours. Useful to avoid low-liquidity windows.

**session_allowed_hours_utc**
- Type: [int, int] | Default: [6, 22]
- [start_hour, end_hour] in UTC. Example: [6, 22] = trade from 6 AM to 10 PM UTC.

---

## Funding Rate

**funding_modifier_enabled**
- Type: bool | Default: true
- Reduce confidence score by 1 when funding rate is extreme in the trade direction.

**funding_extreme_threshold**
- Type: float | Default: 0.001
- Funding rate above this absolute value is considered "extreme" (0.001 = 0.1% per 8h).

---

## Auto Blacklist

**auto_blacklist_enabled**
- Type: bool | Default: true

**auto_blacklist_losses**
- Type: int | Default: 4
- Trigger blacklist if pair lost this many times in the last N trades.

**auto_blacklist_window**
- Type: int | Default: 5
- Look-back window (number of recent trades) for auto-blacklist check.

**auto_blacklist_hours**
- Type: float | Default: 24.0
- How long to auto-blacklist the pair.
