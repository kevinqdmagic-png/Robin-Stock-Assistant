"""Versioned, append-only intraday shadow price tracking (NOT trading P&L).

A resident Railway volume stores each same-day quote before outcomes are known.
Post-close review only appends a horizon once its completed session has occurred;
missing quotes, splits and missing daily bars are not guessed or scored as wins.
"""
from datetime import datetime, date
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
import json
import math
import os
import tempfile

from daily_providers import tencent_daily
from learning_loop import nth_session_after
from trading_calendar import CN_TZ, completed_bars, session_state

HORIZONS = (1, 2, 5, 10)
COHORTS = (("candidates", "low_chase"), ("momentum_control", "momentum_control"))
VERSION = "intraday_forward_price_only_v1"


def _read(path):
    if not path.exists():
        return {"schema_version": 1, "items": []}
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("schema_version") != 1 or not isinstance(obj.get("items"), list):
        raise ValueError("invalid_forward_ledger")
    return obj


def _write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8",
                                     prefix=".forward-", dir=path.parent,
                                     delete=False) as file:
        json.dump(document, file, ensure_ascii=False, indent=2)
        file.write("\n")
        tmp = file.name
    os.replace(tmp, path)


def _eligible_observations(runs):
    for run in runs:
        if run.get("status") != "observed" or run.get("task_id") not in ("early_pair", "late_pair"):
            continue
        try:
            day = date.fromisoformat(run["date"])
        except (KeyError, TypeError, ValueError):
            continue
        for field, cohort in COHORTS:
            for item in run.get(field) or []:
                try:
                    observed = datetime.fromisoformat(item["as_of"])
                    price = float(item["price"])
                    if observed.tzinfo is None or not math.isfinite(price) or price <= 0:
                        continue
                    if observed.astimezone(CN_TZ).date() != day:
                        continue
                    code = item["code"]
                    if len(code) != 6 or not code.isascii() or not code.isdigit():
                        continue
                except (TypeError, ValueError, KeyError):
                    continue
                yield {
                    "signal_date": day.isoformat(), "task_id": run["task_id"],
                    "code": code, "name": item.get("name"),
                    "cohort": cohort, "model_version": item.get("model_version", "legacy_unversioned"),
                    "signal_time": observed.astimezone(CN_TZ).isoformat(),
                    "signal_quote": price, "signal_quote_source": item.get("quote_source"),
                }


def update_forward(runs, path, now=None, daily_loader=tencent_daily):
    """Append matured T+h unadjusted-price outcomes; idempotent and fail-closed."""
    now = (now or datetime.now(CN_TZ)).astimezone(CN_TZ)
    if session_state(now)["code"] != "after_close" or now.hour * 60 + now.minute < 930:
        return {"ok": True, "status": "not_after_verified_close", "appended": 0}
    doc = _read(path)
    seen = {x["id"] for x in doc["items"]}
    fresh = []
    errors = []
    cache = {}
    attempted = 0
    for sig in _eligible_observations(runs):
        day = date.fromisoformat(sig["signal_date"])
        for horizon in HORIZONS:
            target = nth_session_after(day, horizon)
            if target is None or target > now.date():
                continue
            key = "-".join((sig["signal_date"], sig["task_id"],
                            sig["cohort"], sig["code"], str(horizon)))
            if key in seen:
                continue
            attempted += 1
            if sig["code"] not in cache:
                try:
                    # UNadjusted prices match contemporaneous trading quotes.
                    raw = daily_loader(sig["code"], limit=120, adjust="0")
                    cache[sig["code"]] = {
                        r["date"]: r for r in completed_bars(raw, now)
                        if r.get("volume", 0) > 0
                    }
                except (ValueError, TypeError, KeyError, OSError, Exception) as exc:
                    # Provider outages remain missing, never retroactively fabricated.
                    cache[sig["code"]] = None
                    errors.append(type(exc).__name__)
            bars = cache[sig["code"]]
            if bars is None:
                continue
            anchor = bars.get(sig["signal_date"])
            actual = bars.get(target.isoformat())
            if anchor is None or actual is None:
                continue
            anchor_close = float(anchor["close"])
            close = float(actual["close"])
            if not (math.isfinite(anchor_close) and math.isfinite(close) and
                    anchor_close > 0 and close > 0):
                continue
            # Data-adjustment mismatches and extreme corporate actions require
            # separate security-master verification before counting this sample.
            if abs(anchor_close / sig["signal_quote"] - 1) > 0.25:
                errors.append("signal_quote_anchor_mismatch")
                continue
            if abs(close / anchor_close - 1) > 3:
                errors.append("corporate_action_or_price_source_unverified")
                continue
            fresh.append({
                "id": key, "signal_date": sig["signal_date"],
                "task_id": sig["task_id"], "code": sig["code"],
                "name": sig["name"], "cohort": sig["cohort"],
                "model_version": sig["model_version"],
                "signal_time": sig["signal_time"],
                "signal_quote": sig["signal_quote"],
                "signal_quote_source": sig["signal_quote_source"],
                "horizon": horizon, "target_date": target.isoformat(),
                "target_unadjusted_close": round(close, 4),
                "anchor_unadjusted_close": round(anchor_close, 4),
                "price_change_from_quote_pct": round(
                    (close / sig["signal_quote"] - 1) * 100, 3),
                "observed_at": now.isoformat(timespec="seconds"),
                "daily_source": "tencent_unadjusted_daily",
                "method": VERSION,
                "executed_trade": False, "net_trade_return_pct": None,
                "caveat": "以原盘中报价至T+h收盘的价格观察；不是当时成交、可卖出净收益或盘中回撤路径",
            })
            seen.add(key)
    if fresh:
        doc["items"] += fresh
        _write(path, doc)
    return {"ok": True, "status": "observed" if fresh else
            ("pending_or_data_gaps" if attempted else "no_new_matured_signals"),
            "appended": len(fresh), "attempted": attempted,
            "provider_errors": errors[:20],
            "sample_count_total": len(doc["items"]), "observation_only": True}


def forward_summary(path, slot=None, limit=100):
    """Read-only grouped comparisons; never mix multiple horizons or strategy versions."""
    if slot not in (None, "early_pair", "late_pair"):
        raise ValueError("unknown_intraday_slot")
    entries = _read(path)["items"]
    if slot:
        entries = [x for x in entries if x.get("task_id") == slot]
    entries.sort(key=lambda x: (x["target_date"], x["id"]), reverse=True)
    groups = defaultdict(list)
    for r in entries:
        groups[(r["task_id"], r["cohort"], r["model_version"], r["horizon"])].append(r)
    series = []
    for (task, cohort, model, horizon), items in sorted(groups.items()):
        vals = [float(x["price_change_from_quote_pct"]) for x in items]
        series.append({
            "task_id": task, "cohort": cohort, "model_version": model,
            "horizon": horizon, "sample_count": len(vals),
            "distinct_signal_days": len({x["signal_date"] for x in items}),
            "positive_price_observation_pct": round(100 * sum(v > 0 for v in vals) / len(vals), 2),
            "mean_price_change_pct": round(mean(vals), 3),
            "median_price_change_pct": round(median(vals), 3),
            "below_minus_5_pct": round(100 * sum(v <= -5 for v in vals) / len(vals), 2),
            "strategy_profitable_verified": False,
        })
    return {
        "ok": True, "status": "forward_price_observations_only",
        "version": VERSION, "items": entries[:max(1, min(int(limit), 200))],
        "total": len(entries), "groups": series,
        "min_evaluation_signal_days": 20, "min_evaluation_samples": 36,
        "strategy_validated": False, "automatic_strategy_promotion": False,
        "executed_trades_verified": 0,
        "warning": "观察收益不等于买卖净收益；同股不同时间点可能相关；须按交易日、股票簇、规则版本样本外比较并验证成交。",
    }
