"""Railway resident intraday scheduler: real timestamps, not guaranteed alpha.

The API process drives 09:50/14:40 Beijing windows, independent of delayed GitHub cron.
A Railway persistent volume preserves original dated observations across deploys.
Zero ticker candidates is a legitimate outcome; backtesting is still outstanding.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, time as clock
from pathlib import Path
import json
import logging
import math
import os
import re
import tempfile
import threading
import time

import requests
from capital_behavior import classify
from daily_providers import tencent_daily
from quote_providers import tencent_quotes, stock_symbol
from research_archive import load_document
from trading_calendar import CN_TZ, completed_bars, session_state

log = logging.getLogger("robin-intraday-service")
STORE = Path(os.environ.get("ROBIN_INTRADAY_STORE", "/var/lib/robin/intraday.json"))
SLOTS = {"early_pair": (9, 50), "late_pair": (14, 40)}
MAX_AGE = 180
_guard = threading.RLock()
_running = set()
_started = False


def storage_ready():
    """Probe write access without creating fake trades or research receipts."""
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=STORE.parent,
                                         prefix=".storage-probe-", delete=False) as sample:
            sample.write("probe\n")
            name = sample.name
        os.unlink(name)
        return True
    except OSError as exc:
        log.warning("INTRADAY_STORE_NOT_WRITABLE %s: %s", STORE.parent, exc)
        return False


def _store():
    if not STORE.exists():
        return {"schema_version": 1, "items": []}
    doc = json.loads(STORE.read_text(encoding="utf-8"))
    if doc.get("schema_version") != 1 or not isinstance(doc.get("items"), list):
        raise ValueError("invalid_intraday_store")
    return doc


def persist(row):
    """Atomic append-only or same-run retry replacement; never alter finalized observations."""
    with _guard:
        doc = _store()
        items = doc["items"]
        found = next((i for i, old in enumerate(items)
                      if old["date"] == row["date"] and old["task_id"] == row["task_id"]), None)
        if found is not None:
            old = items[found]
            if old["status"] in ("observed", "no_signal", "missed"):
                return False
            # Retry attempts on the same date may refine an earlier blocked outcome.
            if row["attempt"] <= old["attempt"]:
                return False
            items[found] = row
        else:
            items.append(row)
        if len(items) > 600:
            # Preserve history rather than silently evicting auditable records.
            raise ValueError("intraday_store_capacity_reached")
        STORE.parent.mkdir(parents=True, exist_ok=True)
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=STORE.parent,
                                          prefix=".intraday-", delete=False) as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
            tmp = f.name
        os.replace(tmp, STORE)
        return True


def latest(slot=None, limit=20, now=None):
    if slot is not None and slot not in SLOTS:
        raise ValueError("unknown_intraday_slot")
    now = (now or datetime.now(CN_TZ)).astimezone(CN_TZ)
    with _guard:
        doc = _store()
    rows = [x for x in doc["items"] if slot is None or x["task_id"] == slot]
    rows.sort(key=lambda x: (x["date"], x["started_at"]), reverse=True)
    item = rows[0] if rows else None
    today = now.date().isoformat()
    state = session_state(now)
    scheduled_time = SLOTS[slot or "late_pair"]
    current_minutes = now.hour * 60 + now.minute
    planned = scheduled_time[0] * 60 + scheduled_time[1]
    if slot and state["code"] == "trading" and current_minutes < planned:
        current_status = "scheduled"
    elif slot and now.date().isoformat() != (item or {}).get("date") and current_minutes >= planned + 18:
        current_status = "missed" if state["date"] == today and state["code"] != "closed" else "closed"
    elif item and item["date"] == today:
        current_status = item["status"]
    else:
        current_status = "no_record"
    return {
        "ok": True, "time_cn": now.isoformat(timespec="seconds"),
        "slot": slot, "current_status": current_status,
        "latest": item, "items": rows[:max(1, min(limit, 100))],
        "total": len(rows), "storage": "railway_persistent_volume",
        "scheduler_started": _started,
        "store_writable": storage_ready(),
        "volume_mount_detected": os.path.ismount(STORE.parent),
        "publication": "original_time_stamped_partial_universe",
        "research_model": "intraday_low_chase_shadow_v2",
        "strategy_validated": False, "recommendation_executable": False,
    }


def target_universe(client=requests):
    """Discovered turnover leaders + existing app research stock catalog."""
    codes = []
    names = {}
    for archive in ("research_stocks.json", "recommendations.json"):
        try:
            rows = load_document(archive)["items"]
        except (OSError, ValueError):
            continue
        for item in rows:
            code = str(item.get("code") or "")
            if re.fullmatch(r"\d{6}", code) and code.startswith(("00", "30", "60", "68")):
                if code not in codes:
                    codes.append(code)
                if item.get("name"):
                    names[code] = str(item["name"])
    errors = []
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": 1, "pz": 90, "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2, "fid": "f6",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f12,f14,f6",
    }
    for host in (url, url.replace("push2.", "push2delay.")):
        try:
            resp = client.get(host, params=params, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://quote.eastmoney.com/",
            }, timeout=(3, 4))
            resp.raise_for_status()
            data = resp.json().get("data") or {}
            records = data.get("diff") or []
            if isinstance(records, dict):
                records = list(records.values())
            if not isinstance(records, list):
                raise ValueError("invalid_market_rank_response")
            for q in records:
                if not isinstance(q, dict):
                    continue
                code = str(q.get("f12", ""))
                if re.fullmatch(r"\d{6}", code) and code.startswith(("00", "30", "60", "68")):
                    if code not in codes:
                        codes.append(code)
                    if q.get("f14"):
                        names[code] = str(q["f14"])
            if records:
                break
        except (requests.RequestException, ValueError, TypeError) as exc:
            errors.append("eastmoney_rank:" + type(exc).__name__)
    codes = [c for c in codes if "ST" not in names.get(c, "").upper()
             and "退" not in names.get(c, "")]
    return codes[:150], names, errors


def _fresh_quotes(codes, now):
    good = []
    errors = []
    for begin in range(0, len(codes), 45):
        chunk = [stock_symbol(c) for c in codes[begin:begin+45]]
        try:
            quote_rows = tencent_quotes(chunk)
            for q in quote_rows:
                try:
                    stamp = datetime.fromisoformat(q["as_of"])
                    age = (now - stamp.astimezone(CN_TZ)).total_seconds()
                    if stamp.tzinfo is None or stamp.astimezone(CN_TZ).date() != now.date():
                        continue
                    if not -45 <= age <= MAX_AGE:
                        continue
                    if "ST" in q["name"].upper() or "退" in q["name"]:
                        continue
                    if not math.isfinite(float(q["price"])) or not math.isfinite(float(q["pct"])):
                        continue
                    good.append(q)
                except (ValueError, KeyError, TypeError, OverflowError):
                    continue
        except (requests.RequestException, ValueError, TypeError) as exc:
            errors.append("tencent_quote_batch:" + type(exc).__name__)
    return good, errors


def _candidate(q, day, now):
    """Low-chase shadow hypothesis v2; NEVER a verified buy signal.

    All technical features use only completed prior-session bars. Thresholds
    are pre-registered research assumptions, not fitted profitability claims.
    """
    code = q["code"]
    pct = float(q["pct"])
    growth_board = code.startswith(("30", "68"))
    lower, upper = (1.5, 8.0) if growth_board else (0.8, 5.5)
    vr, turnover_ratio = q.get("volume_ratio"), q.get("turnover")
    if not lower <= pct <= upper or vr is None or turnover_ratio is None:
        return None
    if not 1.15 <= float(vr) <= 6 or not 1.2 <= float(turnover_ratio) <= 22:
        return None
    bars = tencent_daily(code, limit=100, adjust="1")
    complete = completed_bars(bars, now)
    if len(complete) < 61 or complete[-1]["date"] >= day:
        raise ValueError("daily_history_stale_or_incomplete")
    if any(b.get("volume", 0) <= 0 for b in complete[-61:]):
        return None
    price = float(q["price"])
    prior = complete[-20:]
    prior60 = complete[-60:]
    highest20 = max(b["high"] for b in prior)
    lowest60 = min(b["low"] for b in prior60)
    highest60 = max(b["high"] for b in prior60)
    ma20 = sum(b["close"] for b in prior) / 20
    distance20_pct = (price / ma20 - 1) * 100
    prior10_pct = (complete[-1]["close"] / complete[-11]["close"] - 1) * 100
    position60 = (price - lowest60) / (highest60 - lowest60) if highest60 > lowest60 else 1
    breakout20_pct = (price / highest20 - 1) * 100
    limit_distance = 16 if growth_board else 12
    limit_prior10 = 26 if growth_board else 19
    # Unlike v1, an extended rally is not rewarded with additional points.
    if (distance20_pct < -3 or distance20_pct > limit_distance
            or prior10_pct > limit_prior10
            or breakout20_pct > 3
            or (position60 > 0.94 and distance20_pct > 6)):
        return None
    if not -0.12 <= position60 <= 1.12:
        return None
    score = round(
        min(float(vr), 3.5) * 2.0 +
        min(float(turnover_ratio), 12) * 0.45 +
        max(0, 3.5 - abs(pct - (3.3 if growth_board else 2.5))) +
        (2 if price >= highest20 else 0) -
        max(0, distance20_pct - 4) * 0.9 -
        max(0, prior10_pct - 10) * 0.35 -
        max(0, position60 - 0.82) * 12, 2)
    risk_tags = []
    if distance20_pct > 7:
        risk_tags.append("above_ma20_7pct")
    if prior10_pct > 12:
        risk_tags.append("prior_10day_extension")
    if position60 > 0.85:
        risk_tags.append("near_60day_high")
    return {
        "code": code, "name": q["name"], "price": q["price"],
        "pct": q["pct"], "volume_ratio": vr, "turnover_ratio": turnover_ratio,
        "as_of": q["as_of"], "daily_cutoff": complete[-1]["date"],
        "quote_source": q["source"], "daily_source": "tencent_qfq_daily",
        "score": score, "prior20_high": round(highest20, 3),
        "prior20_ma": round(ma20, 3),
        "ma20_distance_pct": round(distance20_pct, 3),
        "prior10_return_pct": round(prior10_pct, 3),
        "position60": round(position60, 3),
        "breakout20_pct": round(breakout20_pct, 3),
        "risk_tags": risk_tags,
        "hypothesis": "moderate_volume_accumulation_vs_extended_momentum",
        "model_version": "intraday_low_chase_shadow_v2",
        "notes": ["低中位温和放量、前一交易日已完成K线位置",
                  "过热与均线乖离限制为待验证研究假设"],
        "risk": "仅为实时观察；无盘口承接/行业同步/当时可成交/次日溢价的完整验证，不得视为买入建议",
        "signal_validated": False, "buy_order_allowed": False,
    }

def _momentum_controls(quotes, excluded):
    """Frozen quote-level v1-style controls; never buy suggestions."""
    rows = []
    for q in quotes:
        code = q["code"]
        if code in excluded or code.startswith(("4", "8", "92")):
            continue
        growth = code.startswith(("30", "68"))
        pct = float(q["pct"])
        vr, turn = q.get("volume_ratio"), q.get("turnover")
        if (not ((4 if growth else 2.5) <= pct <= (18 if growth else 8.9))
                or vr is None or turn is None):
            continue
        if not (1.25 <= float(vr) <= 100 and 2 <= float(turn) <= 34):
            continue
        score = round(pct * 2 + min(float(vr), 10) * 1.8 +
                      min(float(turn), 20) * 0.35, 2)
        rows.append({
            "code": code, "name": q["name"], "price": q["price"],
            "pct": pct, "volume_ratio": vr, "turnover_ratio": turn,
            "score": score, "as_of": q["as_of"],
            "quote_source": q["source"],
            "model_version": "intraday_momentum_quote_control_v1",
            "control_only": True, "signal_validated": False,
            "risk": "旧涨幅优先的对照观察，未完成日线复核；绝非买点",
        })
    rows.sort(key=lambda x: (-x["score"], x["code"]))
    return rows[:2]


def execute(slot, now=None, universe_loader=None, quote_loader=None, candidate_loader=None):
    if slot not in SLOTS:
        raise ValueError("invalid_intraday_slot")
    now = (now or datetime.now(CN_TZ)).astimezone(CN_TZ)
    start = SLOTS[slot][0] * 60 + SLOTS[slot][1]
    minutes = now.hour * 60 + now.minute
    if session_state(now)["code"] != "trading" or not start <= minutes < start + 18:
        return None
    date = now.date().isoformat()
    base = {
        "date": date, "task_id": slot, "started_at": now.isoformat(timespec="seconds"),
        "status": "blocked", "reason_code": "insufficient_evidence",
        "candidates": [], "scanned": 0, "fresh_quotes": 0,
        "daily_checked": 0, "source": "tencent_quote_and_prior_completed_qfq_daily",
        "coverage": "partial_watchlist_plus_discoverable_activity_leaders",
        "full_market_coverage": False, "strategy_validated": False,
        "model_version": "intraday_low_chase_shadow_v2",
        "momentum_control": [], "provider_errors": [],
    }
    try:
        codes, names, errors = (universe_loader or target_universe)()
        base["scanned"] = len(codes)
        base["provider_errors"].extend(errors)
        if len(codes) < 5:
            base["reason_code"] = "universe_too_small"
            return base
        quotes, errors = (quote_loader or _fresh_quotes)(codes, now)
        base["fresh_quotes"] = len(quotes)
        base["provider_errors"].extend(errors)
        if len(quotes) < 5:
            base["reason_code"] = "insufficient_fresh_quotes"
            return base
        # Prefer moderate strength/volume, never today's biggest gainers by default.
        short = [q for q in quotes if
                 0.8 <= float(q.get("pct", 0)) <= 8.0 and
                 q.get("turnover") is not None and
                 q.get("volume_ratio") is not None and
                 1 <= float(q["turnover"]) <= 28 and
                 1 <= float(q["volume_ratio"]) <= 12]
        short.sort(key=lambda q: (
            abs(float(q["pct"]) - 2.8),
            abs(float(q["volume_ratio"]) - 2),
            -min(float(q["turnover"]), 12), q["code"]))
        short = short[:30]
        results = []
        attempted = 0
        daily_failures = 0
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(candidate_loader or _candidate, q, date, now): q for q in short}
            for future in as_completed(futures):
                attempted += 1
                try:
                    item = future.result()
                    if item:
                        results.append(item)
                except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
                    daily_failures += 1
                    base["provider_errors"].append("daily_validation:" + type(exc).__name__)
        base["daily_checked"] = max(0, attempted - daily_failures)
        base["daily_attempted"] = attempted
        if attempted and daily_failures == attempted:
            base["status"] = "blocked"
            base["reason_code"] = "daily_validation_unavailable"
            return base
        results.sort(key=lambda x: (-x["score"], x["code"]))
        base["candidates"] = results[:2]
        base["momentum_control"] = _momentum_controls(
            quotes, {x["code"] for x in base["candidates"]})
        base["status"] = "observed" if results else "no_signal"
        base["reason_code"] = "low_chase_shadow_not_backtested" if results else "no_eligible_low_chase_candidate"
        return base
    except Exception as exc:
        log.exception("Intraday %s execution error", slot)
        base["reason_code"] = "unexpected_exception:" + type(exc).__name__
        return base


def _run_if_due(now=None):
    now = (now or datetime.now(CN_TZ)).astimezone(CN_TZ)
    current = session_state(now)
    if current["code"] != "trading":
        return False
    for slot, (hour, minute) in SLOTS.items():
        target = hour * 60 + minute
        value = now.hour * 60 + now.minute
        if not target <= value < target + 18:
            continue
        key = (now.date().isoformat(), slot)
        with _guard:
            if key in _running:
                continue
            previous = next((row for row in _store()["items"]
                             if row["date"] == key[0] and row["task_id"] == slot), None)
            if previous and previous["status"] in ("observed", "no_signal", "missed"):
                continue
            if previous:
                last = datetime.fromisoformat(previous["started_at"])
                if (now - last).total_seconds() < 120:
                    continue
            _running.add(key)
        def work():
            try:
                result = execute(slot)
                if result is None:
                    return
                with _guard:
                    prior = next((row for row in _store()["items"] if
                                  row["date"] == result["date"] and row["task_id"] == slot), None)
                    result["attempt"] = prior["attempt"] + 1 if prior else 1
                result["finished_at"] = datetime.now(CN_TZ).isoformat(timespec="seconds")
                persist(result)
                log.info("INTRADAY_EXECUTE %s status=%s scanned=%s quotes=%s candidates=%s",
                         slot, result["status"], result["scanned"], result["fresh_quotes"],
                         len(result["candidates"]))
            except Exception:
                log.exception("Intraday %s scheduling failed", slot)
            finally:
                with _guard:
                    _running.discard(key)
        threading.Thread(target=work, daemon=True, name="intraday-" + slot).start()
        return True
    return False


def start_scheduler():
    global _started
    with _guard:
        if _started:
            return
        _started = True
    if not storage_ready():
        log.error("INTRADAY_PERSISTENCE_UNAVAILABLE store=%s", STORE)
    def loop():
        log.warning("INTRADAY_SCHEDULER_STARTED Beijing 09:50/14:40, store=%s", STORE)
        while True:
            try:
                _run_if_due()
            except Exception:
                log.exception("INTRADAY_SCHEDULER_LOOP_FAILED")
            time.sleep(15)
    threading.Thread(target=loop, daemon=True, name="robin-live-intraday").start()
