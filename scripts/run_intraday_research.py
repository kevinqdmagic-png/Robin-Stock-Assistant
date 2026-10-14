#!/usr/bin/env python3
"""Intraday research execution gate. Live observed candidates, not trading picks.

Runs in GitHub Actions at 09:50/14:40 Beijing time. Produces an auditable
JSON outcome; actual selection requires a separately verified market-data
adapter, which is intentionally not fabricated here.
"""
import argparse
from datetime import datetime
import math
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from trading_calendar import session_state

CN_TZ = ZoneInfo("Asia/Shanghai")
SLOTS = {"early_pair": (9, 50), "late_pair": (14, 40)}


def validate_feed(feed, now):
    """Check snapshot format and recency; never treat it as proof of a trade."""
    if not isinstance(feed, dict) or not isinstance(feed.get("quotes"), list):
        return "invalid_feed"
    source = feed.get("source")
    if not isinstance(source, str) or not source.startswith("https://"):
        return "missing_source"
    # Explicitly reject illustrative, loopback and reserved documentation hosts.
    # An HTTPS URL alone never proves the market quote is genuine.
    from urllib.parse import urlparse
    from ipaddress import ip_address
    host = urlparse(source).hostname
    if not host or host == "localhost" or host.endswith((".localhost", ".example", ".test", ".invalid")) or host in ("example.com", "example.org", "example.net"):
        return "untrusted_source"
    try:
        address = ip_address(host)
        if not address.is_global:
            return "untrusted_source"
    except ValueError:
        pass
    try:
        timestamp = datetime.fromisoformat(feed["as_of"])
    except (KeyError, TypeError, ValueError):
        return "invalid_timestamp"
    if timestamp.tzinfo is None:
        return "missing_timezone"
    age = (now - timestamp.astimezone(CN_TZ)).total_seconds()
    if timestamp.astimezone(CN_TZ).date() != now.date() or not 0 <= age <= 300:
        return "stale_or_future_snapshot"
    if not feed["quotes"]:
        return "empty_quotes"
    seen = set()
    for quote in feed["quotes"]:
        if not isinstance(quote, dict) or not isinstance(quote.get("code"), str) or not (
            len(quote["code"]) == 6 and quote["code"].isdigit()
        ):
            return "invalid_code"
        code = quote["code"]
        if code in seen:
            return "duplicate_quote_code"
        seen.add(code)
        price = quote.get("price")
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not 0 < price < 100000:
            return "invalid_price"
        # A single price is not enough to assess limit-up eligibility or
        # next-session premium. These fields must be present for later screening.
        if quote.get("market") not in ("SH", "SZ", "BJ"):
            return "missing_exchange"
        if not isinstance(quote.get("name"), str) or not quote["name"].strip():
            return "missing_security_name"
        for key in ("previous_close", "volume", "turnover"):
            value = quote.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                return "missing_market_evidence"
        for key in ("pct", "turnover_ratio"):
            value = quote.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                return "missing_market_evidence"
        if not -35 <= quote["pct"] <= 35 or not 0 <= quote["turnover_ratio"] <= 100:
            return "incompatible_market_evidence"
        actual_pct = (price / quote["previous_close"] - 1) * 100
        if abs(actual_pct - quote["pct"]) > 0.4:
            return "incompatible_market_evidence"
        try:
            qt = datetime.fromisoformat(quote["as_of"])
        except (KeyError, TypeError, ValueError):
            return "invalid_quote_timestamp"
        if qt.tzinfo is None:
            return "invalid_quote_timestamp"
        delta = (now - qt.astimezone(CN_TZ)).total_seconds()
        if not 0 <= delta <= 300 or qt.astimezone(CN_TZ).date() != now.date():
            return "stale_or_future_snapshot"
    return None


def watch_candidates(quotes):
    """Explicit reproducible heuristic, never represented as a validated alpha model."""
    eligible = []
    for q in quotes:
        code = q["code"]
        if code.startswith(("4", "8", "92")):  # BSE: different limit/liquidity rules
            continue
        pct = q["pct"]
        board_max = 20 if code.startswith(("30", "68")) else 10
        minimum = 3 if board_max == 10 else 4
        maximum = board_max - 1.0
        if not minimum <= pct <= maximum:
            continue
        if (q["turnover"] < 80000000 or q.get("turnover_ratio", 0) < 2 or
                q.get("turnover_ratio", 0) > 35):
            continue
        vr = q.get("volume_ratio")
        if vr is not None and vr < 1.1:
            continue
        ranked = round(pct * 2 + min(q["turnover"] / 100000000, 50) * 0.3 +
                       min(q.get("turnover_ratio") or 0, 30) * 0.2 +
                       min(vr or 0, 10) * 1.5, 2)
        eligible.append({
            "code": code, "name": q["name"], "price": q["price"],
            "pct": pct, "amount_yi": round(q["turnover"] / 1e8, 2),
            "turnover_ratio": q.get("turnover_ratio"), "volume_ratio": vr,
            "as_of": q["as_of"], "source": q["source"],
            "heuristic_score": ranked,
            "note": "部分股票池中涨幅、成交额及换手筛选，仅为观察候选；未核验板块情绪、盘口承接、涨停价、可成交性或样本外胜率，禁止视为买点。",
        })
    eligible.sort(key=lambda r: (-r["heuristic_score"], r["code"]))
    return eligible[:5]


def evaluate(slot, now=None, feed=None):
    if slot not in SLOTS:
        raise ValueError("invalid_intraday_slot")
    now = (now or datetime.now(CN_TZ)).astimezone(CN_TZ)
    state = session_state(now)
    hour, minute = SLOTS[slot]
    minutes_late = (now.hour * 60 + now.minute) - (hour * 60 + minute)
    outcome = {
        "task_id": slot, "checked_at": now.isoformat(), "market_date": now.date().isoformat(),
        "market_state": state["code"], "recommendations": [],
        "market_data_verified": False,
    }
    if state["code"] != "trading":
        outcome.update(status="skipped", reason="not_a_verified_trading_session")
    elif not 0 <= minutes_late <= 25:
        outcome.update(status="skipped", reason="outside_intraday_execution_window")
    else:
        feed_issue = validate_feed(feed, now) if feed is not None else "no_live_feed_supplied"
        outcome.update(status="insufficient_evidence",
                       reason=feed_issue or "snapshot_only_no_verified_selection_model")
        if feed_issue is None:
            outcome["candidate_watch"] = watch_candidates(feed["quotes"])
            outcome["reason"] = "screened_watch_not_validated_strategy"
            outcome["snapshot"] = {"source": feed["source"], "as_of": feed["as_of"],
                                   "quote_count": len(feed["quotes"]),
                                   "validation": "format_and_freshness_only",
                                   "coverage": feed.get("scope", "unknown"),
                                   "full_market_coverage": False,
                                   "requested_count": feed.get("requested_count"),
                                   "provider_errors": feed.get("provider_errors", [])}
    return outcome


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", required=True, choices=sorted(SLOTS))
    parser.add_argument("--output", default="intraday_outcome.json")
    parser.add_argument("--feed-file", help="Optional externally supplied quote snapshot")
    args = parser.parse_args()
    feed = json.loads(Path(args.feed_file).read_text(encoding="utf-8")) if args.feed_file else None
    result = evaluate(args.slot, feed=feed)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
