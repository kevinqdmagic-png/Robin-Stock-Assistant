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
        "store_writable": os.access(STORE.parent, os.W_OK),
        "publication": "original_time_stamped_partial_universe",
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
    code = q["code"]
    pct = float(q["pct"])
    upper = 18.0 if code.startswith(("30", "68")) else 8.9
    lower = 4.0 if code.startswith(("30", "68")) else 2.5
    vr, turnover_ratio = q.get("volume_ratio"), q.get("turnover")
    if not lower <= pct <= upper or vr is None or turnover_ratio is None:
        return None
    if not 1.25 <= float(vr) <= 100 or not 2 <= float(turnover_ratio) <= 34:
        return None
    bars = tencent_daily(code, limit=90, adjust="1")
    complete = completed_bars(bars, now)
    if len(complete) < 61 or complete[-1]["date"] >= day:
        raise ValueError("daily_history_stale_or_incomplete")
    if any(b.get("volume", 0) <= 0 for b in complete[-61:]):
        return None
    prior = complete[-20:]
    highs = max(b["high"] for b in prior)
    ma20 = sum(b["close"] for b in prior) / 20
    if float(q["price"]) < ma20 * 0.99:
        return None
    # Level-1 alone cannot identify order-book support or guaranteed next-day premium.
    score = round(
        pct * 2 + min(float(vr), 10) * 1.8 +
        min(float(turnover_ratio), 20) * 0.35 +
        (5 if float(q["price"]) >= highs else 0), 2)
    return {
        "code": code, "name": q["name"], "price": q["price"],
        "pct": q["pct"], "volume_ratio": vr, "turnover_ratio": turnover_ratio,
        "as_of": q["as_of"], "daily_cutoff": complete[-1]["date"],
        "quote_source": q["source"], "daily_source": "tencent_qfq_daily",
        "score": score, "prior20_high": round(highs, 3),
        "prior20_ma": round(ma20, 3),
        "notes": ["近期放量或成交活跃代理指标", "当前价对过去20日均价及高点的关系"],
        "risk": "未验证盘口封单、同板块强弱、真实买点和T+1收益，不能视为买入信号",
        "signal_validated": False,
    }


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
        "provider_errors": [],
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
        short = sorted(quotes, key=lambda q: float(q.get("pct", 0)), reverse=True)
        short = [q for q in short if 2 <= float(q.get("pct", 0)) <= 19][:18]
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
        base["status"] = "observed" if results else "no_signal"
        base["reason_code"] = "partial_level1_watch_not_backtested" if results else "no_eligible_candidate"
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
    def loop():
        log.warning("INTRADAY_SCHEDULER_STARTED Beijing 09:50/14:40, store=%s", STORE)
        while True:
            try:
                _run_if_due()
            except Exception:
                log.exception("INTRADAY_SCHEDULER_LOOP_FAILED")
            time.sleep(15)
    threading.Thread(target=loop, daemon=True, name="robin-live-intraday").start()
