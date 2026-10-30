#!/usr/bin/env python3
"""Daily 18:10 Beijing evidence-based scan of candidate accumulation shapes.

Never synthesizes ticker suggestions, trading signals, or market-wide coverage.
Only today's completed day-K data counts. The same classifier is used by the
existing manual per-code capital-behavior endpoint.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import requests
from capital_behavior import classify
from capital_watch import STAGES, validate_archive, verify_append_only
from daily_providers import tencent_daily
from research_archive import load_document
from quote_providers import tencent_quotes, stock_symbol
from trading_calendar import session_state, completed_bars

CN = ZoneInfo("Asia/Shanghai")
MAX_UNIVERSE = 110
MIN_FRESH = 5
TOP = 5


def universe():
    from collect_intraday_feed import eastmoney_leaders, sina_leaders, local_universe
    candidates = local_universe()
    origins = ["historical_research_codes"]
    errors = []
    try:
        leaders, url = eastmoney_leaders()
        candidates.extend(code for code in leaders if code not in candidates)
        origins.append(url)
    except (requests.RequestException, ValueError, TypeError) as exc:
        errors.append("eastmoney_discovery:" + type(exc).__name__)
    try:
        from_sina = sina_leaders(limit=65)
        candidates.extend(code for code in from_sina if code not in candidates)
        origins.append("sina_turnover_leaders")
    except (requests.RequestException, ValueError, TypeError) as exc:
        errors.append("sina_discovery:" + type(exc).__name__)
    # Shenzhen/SSE common-stock scope. BJ and funds use different rules.
    codes = [c for c in candidates if re.fullmatch(r"[0-9]{6}", c)
             and c.startswith(("00", "30", "60", "68"))]
    return codes[:MAX_UNIVERSE], origins, errors


def assess(code, day, now, loader=None):
    if loader is None:
        loader = tencent_daily
    try:
        bars = loader(code, limit=125, adjust="1")
        completed = completed_bars(bars, now)
        if len(completed) < 61 or completed[-1]["date"] != day:
            return "stale_or_insufficient", None
        result = classify(completed)
    except (requests.RequestException, ValueError, TypeError, KeyError, IndexError) as exc:
        return type(exc).__name__, None
    status = "examined"
    if result["stage"] not in STAGES or result["exploratory_score"] < 55:
        return status, None
    obs = result["observations"]
    return status, {
        "code": code, "name": None, "as_of": result["as_of"],
        "stage": result["stage"], "stage_title": result["stage_title"],
        "score": result["exploratory_score"],
        "source": "tencent_qfq_daily",
        "evidence": result["evidence"][:6], "risk": result["risks"][:4],
        "close_location": obs["close_location"],
        "price_location60": obs["price_location60"],
        "relative_volume20": obs["relative_volume20"],
        "validation": result["validation"],
        "signal_identity_verified": False,
    }


def eligible_completed_day(now):
    """Trading date eligible for a real, point-in-time scan.

    GitHub scheduled jobs sometimes start after Beijing midnight. Until 09:00
    the next calendar day, allow the immediately preceding verified trading
    session, but retain the *actual* scan/publish time. Never replay an
    older session or scan after the next trading session has opened.
    """
    now = now.astimezone(CN)
    state = session_state(now)
    if state["code"] == "after_close" and (now.hour, now.minute) >= (15, 10):
        return now.date().isoformat()
    if now.hour < 9:
        prior_close = (now - timedelta(days=1)).replace(hour=16, minute=0, second=0)
        if session_state(prior_close)["code"] == "after_close":
            return prior_close.date().isoformat()
    return None


def scan(now=None, pool=None, loader=None, workers=6):
    now = (now or datetime.now(CN)).astimezone(CN)
    eligible_day = eligible_completed_day(now)
    day = eligible_day or now.date().isoformat()
    run_base = {
        "date": day, "as_of": now.isoformat(timespec="seconds"),
        "model": "capital_behavior_daily_v1", "scanned": 0, "valid_daily": 0,
        "candidates": [], "universe": "historical_research_plus_public_activity_leaders",
        "universe_sources": [], "provider_errors": {},
        "coverage": "partial_universe_not_a_share_full_market",
    }
    if eligible_day is None:
        return {**run_base, "status": "skipped", "note": "非已确认的交易日收盘后时段"}
    supplied_pool = pool is not None
    if pool is None:
        pool, origins, discovery_errors = universe()
    else:
        origins, discovery_errors = ["unit_test_supplied_universe"], []
    pool = list(dict.fromkeys(pool))[:MAX_UNIVERSE]
    failures = Counter(discovery_errors)
    results = []
    qualifying = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as executor:
        futures = {executor.submit(assess, code, day, now, loader): code for code in pool}
        for future in as_completed(futures):
            try:
                status, found = future.result()
            except Exception as exc:
                status, found = type(exc).__name__, None
            if status == "examined":
                results.append(futures[future])
            else:
                failures[status] += 1
            if found is not None:
                qualifying.append(found)
    # No fallback to prior trading days and no synthetic filler candidates.
    qualifying.sort(key=lambda row: (-row["score"], row["code"]))
    selected = qualifying[:TOP]
    # Names are security metadata, not trading evidence; never substitute
    # a quote's price for the completed K-line analysis.
    if selected and not supplied_pool:
        known_names = {}
        for filename in ("research_stocks.json", "recommendations.json"):
            try:
                doc = load_document(filename)
                known_names.update({str(x["code"]): str(x["name"]) for x in doc["items"]
                                    if x.get("code") and x.get("name")})
            except (OSError, ValueError, TypeError, KeyError):
                pass
        try:
            rows = tencent_quotes([stock_symbol(x["code"]) for x in selected])
            known_names.update({str(x["code"]): str(x["name"]) for x in rows
                                if x.get("code") and x.get("name")})
        except (requests.RequestException, ValueError, TypeError) as exc:
            failures["security_name_lookup:" + type(exc).__name__] += 1
        for item in selected:
            item["name"] = known_names.get(item["code"])
        # Unknown or risk-label/security-special-treatment names cannot be
        # presented as fully checked, independently researched candidates.
        selected = [x for x in selected if x.get("name") and
                    "ST" not in x["name"].upper() and "退" not in x["name"]]
    if len(results) < MIN_FRESH:
        status = "blocked"
        note = "同日有效日线不足5只，不能形成可核验的自动观察名单"
        selected = []
    elif not selected:
        status = "no_matches"
        note = "部分扫描池当日没有符合限定形态的候选，不强行推荐"
    else:
        status = "completed"
        note = "只代表量价模型观察候选，非真实主力持仓、非已验证交易策略"
    return {
        **run_base, "status": status, "note": note,
        "scanned": len(pool), "valid_daily": len(results),
        "candidates": selected, "universe_sources": origins,
        "provider_errors": dict(failures),
        "matching_before_limit": len(qualifying),
    }


def append_snapshot(doc, run, run_id, published_at=None):
    now = (published_at or datetime.now(CN)).astimezone(CN)
    if not str(run_id).isdigit():
        raise ValueError("invalid_github_run_id")
    if run["status"] == "skipped":
        return doc, False
    if run["date"] != eligible_completed_day(now):
        raise ValueError("late_publish_outside_verified_session_window")
    key = "capital-watch-" + run["date"].replace("-", "") + "-" + str(run_id)
    if any(x.get("id") == key for x in doc["items"]):
        return doc, False
    item = {
        **run, "id": key, "run_id": "github-actions-" + str(run_id),
        "published_at": now.isoformat(timespec="seconds"),
        "timezone": "Asia/Shanghai",
        "research_only": True, "selection_validated": False,
        "delayed_publication": run["date"] != now.date().isoformat(),
        "sources": ["https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/actions/runs/" + str(run_id)],
    }
    updated = {**doc, "items": [*doc["items"], item]}
    validate_archive(updated)
    verify_append_only(doc, updated)
    return updated, True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--archive", default=str(ROOT / "backend/data/capital_watch.json"))
    parser.add_argument("--result", default="capital_watch_status.json")
    args = parser.parse_args()
    outcome = scan()
    path = Path(args.archive)
    current = validate_archive(json.loads(path.read_text(encoding="utf-8")))
    updated, changed = append_snapshot(current, outcome, args.run_id)
    if changed:
        path.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    info = {"changed": changed, "status": outcome["status"],
            "date": outcome["date"], "scanned": outcome["scanned"],
            "valid_daily": outcome["valid_daily"],
            "candidate_count": len(outcome["candidates"]),
            "errors": outcome["provider_errors"]}
    Path(args.result).write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(info, ensure_ascii=False))
    return 0 if outcome["status"] in ("completed", "no_matches", "skipped") else 2


if __name__ == "__main__":
    raise SystemExit(main())
