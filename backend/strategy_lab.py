"""Conservative strategy laboratory: transparent shadow evidence, not orders.

A daily open proxy is useful for *research only*. Without exchange-security
master data and order/fill records, we do not claim executable profitability.
"""
from collections import Counter
from datetime import date, datetime, time
from statistics import mean, median
from zoneinfo import ZoneInfo

from analytics import clean_bars, limit_fraction
from learning_loop import nth_session_after, is_session

CN = ZoneInfo("Asia/Shanghai")
HORIZONS = (1, 2, 5, 10)
MIN_FEATURED_SAMPLES = 36
MIN_UNIQUE_DATES = 20


def summarize_snapshot(snapshot):
    """Deduplicate identical date+symbol outcomes across overlapping research tracks."""
    rows = snapshot.get("evaluations") or []
    by_symbol_date = {}
    duplicates = 0
    for item in rows:
        if item.get("status") not in {"observed", "partially_observed"}:
            continue
        code, day = item.get("code"), item.get("signal_date")
        if not (code and day):
            continue
        key = (str(code), str(day))
        if key in by_symbol_date:
            duplicates += 1
        else:
            by_symbol_date[key] = item
    horizons = {}
    for horizon in HORIZONS:
        pool = []
        for entry in by_symbol_date.values():
            observation = next((p for p in entry.get("horizons", [])
                                if p.get("h") == horizon and p.get("status") == "observed"), None)
            if observation is not None:
                pool.append((entry, observation))
        vals = [float(p["close_pct"]) for _, p in pool]
        adverse = [float(p["mae_pct"]) for _, p in pool if p.get("mae_pct") is not None]
        horizons[str(horizon)] = {
            "sample_count": len(vals),
            "unique_signal_dates": len({r["signal_date"] for r, _ in pool}),
            "positive_pct": round(100 * sum(v > 0 for v in vals) / len(vals), 2) if vals else None,
            "average_price_change_pct": round(mean(vals), 3) if vals else None,
            "median_price_change_pct": round(median(vals), 3) if vals else None,
            "adverse_below_minus_5_pct": round(100 * sum(v <= -5 for v in adverse) / len(adverse), 2) if adverse else None,
            "source": "signal_day_unadjusted_close_price_only",
            "net_trading_return": None,
        }
    mature = horizons["2"]
    enough = (mature["sample_count"] >= MIN_FEATURED_SAMPLES and
              mature["unique_signal_dates"] >= MIN_UNIQUE_DATES)
    return {
        "ok": True, "snapshot_date": snapshot.get("date"),
        "status": "shadow_observation_only",
        "raw_signal_rows": len(rows),
        "distinct_signal_date_symbols": len(by_symbol_date),
        "overlap_rows_excluded": duplicates,
        "horizons": horizons,
        "research_gate": {
            "min_samples": MIN_FEATURED_SAMPLES,
            "min_independent_dates": MIN_UNIQUE_DATES,
            "enough_price_observations_to_evaluate": enough,
            "model_promotion_authorized": False,
            "reasons": ["missing_verified_order_fills",
                        "missing_transaction_calibration",
                        "requires_chronological_holdout_and_human_approval"],
        },
        "actual_trades_verified": 0,
        "app_auto_trading_enabled": False,
        "automatic_weight_updates": False,
        "warning": "价格观察不是买入后的净收益，同日或同股票重复信号已按股票-日期去重。"
    }


def _safe_master(meta, code, anchor):
    """Historical risk/IPO/corporate-action status must be independently supplied."""
    if (not isinstance(meta, dict) or meta.get("verified") is not True
            or meta.get("code") != code or meta.get("as_of") != anchor
            or meta.get("risk_warning") is not False
            or meta.get("ipo_unlimited") is not False
            or meta.get("corporate_action_checked") is not True
            or meta.get("tradable") is not True):
        return False
    try:
        return abs(float(meta["price_limit_fraction"]) - limit_fraction(code)) < 0.00001
    except (ValueError, TypeError, KeyError):
        return False


def simulate_daily_open_proxy(signal, daily_bars, *, security_master=None,
                              capital=10000, commission_bps=3,
                              min_commission=5, sell_tax_bps=5,
                              slippage_bps=5, hold_sessions=1):
    """Reproducible T+1 paper fill assumption; NEVER an actual order or executed P&L.

    Uses only published signal before next market open; no intraday prices can
    establish actual queue priority. Historical security master must be verified
    externally for the signal date before a proxy is computed.
    """
    result = {
        "ok": True, "status": "blocked", "method": "daily_open_paper_proxy_v1",
        "verified_order_fill": False, "actual_strategy_net_return_pct": None,
        "real_money_order": False, "signal_id": signal.get("id"),
        "code": signal.get("code"),
    }
    code, raw_day = str(signal.get("code") or ""), str(signal.get("date") or "")
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return {**result, "reason": "invalid_code"}
    try:
        start = date.fromisoformat(raw_day)
        published = datetime.fromisoformat(str(signal.get("published_at", ""))).astimezone(CN)
        if is_session(start) is not True or published.tzinfo is None:
            return {**result, "reason": "invalid_signal_date"}
        entry_day = nth_session_after(start, 1)
        if entry_day is None or published >= datetime.combine(entry_day, time(9, 30), CN):
            return {**result, "reason": "signal_not_published_before_entry"}
        if not _safe_master(security_master, code, raw_day):
            return {**result, "reason": "historical_security_master_unverified"}
        if (hold_sessions not in (1, 2, 3, 5)
                or not 0 < float(capital) <= 100000000
                or not 0 <= float(commission_bps) <= 100
                or not 0 <= float(min_commission) <= 1000
                or not 0 <= float(sell_tax_bps) <= 100
                or not 0 <= float(slippage_bps) <= 100):
            return {**result, "reason": "invalid_assumptions"}
        rows = clean_bars(daily_bars)
        data = {r["date"]: r for r in rows}
        anchor = data.get(raw_day)
        entry = data.get(entry_day.isoformat())
        if not anchor or not entry or not anchor.get("volume") or not entry.get("volume"):
            return {**result, "reason": "missing_or_suspended_entry_session"}
        bound = round(anchor["close"] * (1 + float(security_master["price_limit_fraction"])), 2)
        if entry["open"] >= bound - 0.005:
            return {**result, "status": "no_entry", "reason": "opening_limit_up_queue_unverified",
                    "entry_date": entry_day.isoformat()}
        assumed_entry = entry["open"] * (1 + slippage_bps / 10000)
        shares = int(capital // (assumed_entry * 100)) * 100
        if shares <= 0:
            return {**result, "status": "no_entry", "reason": "below_one_lot"}
        target = nth_session_after(entry_day, hold_sessions)
        if target is None:
            return {**result, "reason": "calendar_unverified"}
        day = target
        delayed = 0
        while True:
            candle = data.get(day.isoformat())
            previous_day = nth_session_after(day, -1) if False else None
            # Exact previous EXCHANGE session close, not the preceding available stock bar.
            from datetime import timedelta
            prev_date = day - timedelta(days=1)
            while is_session(prev_date) is False:
                prev_date -= timedelta(days=1)
            if is_session(prev_date) is not True or candle is None or not candle.get("volume"):
                return {**result, "status": "pending_exit",
                        "reason": "missing_or_suspended_exit_session",
                        "entry_date": entry_day.isoformat(), "target_exit_date": day.isoformat(),
                        "delayed_exit_sessions": delayed}
            prev = data.get(prev_date.isoformat())
            if prev is None:
                return {**result, "status": "pending_exit",
                        "reason": "previous_exchange_session_missing"}
            low_limit = round(prev["close"] * (1 - float(security_master["price_limit_fraction"])), 2)
            if candle["open"] > low_limit + 0.005:
                break
            delayed += 1
            day = nth_session_after(day, 1)
            if day is None or delayed > 10:
                return {**result, "status": "pending_exit",
                        "reason": "opening_limit_down_exit_unverified",
                        "delayed_exit_sessions": delayed}
        assumed_exit = candle["open"] * (1 - slippage_bps / 10000)
        buy_notional = shares * assumed_entry
        sell_notional = shares * assumed_exit
        commissions = (max(min_commission, buy_notional * commission_bps / 10000)
                       + max(min_commission, sell_notional * commission_bps / 10000))
        tax = sell_notional * sell_tax_bps / 10000
        gross = (sell_notional - buy_notional) / buy_notional * 100
        paper_net = (sell_notional - buy_notional - commissions - tax) / buy_notional * 100
        return {**result, "status": "paper_proxy_complete",
                "reason": "assumed_next_open_paper_trade_not_real_fill",
                "entry_date": entry_day.isoformat(), "exit_date": day.isoformat(),
                "hold_sessions": hold_sessions, "delayed_exit_sessions": delayed,
                "paper_entry_price": round(assumed_entry, 4),
                "paper_exit_price": round(assumed_exit, 4),
                "paper_shares": shares,
                "paper_gross_pct": round(gross, 3),
                "paper_net_pct": round(paper_net, 3),
                "commission_and_tax_yuan": round(commissions + tax, 2),
                "assumptions": {"capital": capital, "commission_bps": commission_bps,
                                "min_commission": min_commission,
                                "sell_tax_bps": sell_tax_bps, "slippage_bps": slippage_bps},
                "caveat": "已确认证券规则仅是纸面模拟前提，OHLC不能证明成交、排队或滑点。"}
    except (TypeError, ValueError, KeyError, OverflowError):
        return {**result, "reason": "invalid_or_inconsistent_price_evidence"}
