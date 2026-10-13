#!/usr/bin/env python3
"""Intraday research execution gate. No unsupported stock picks or archive writes.

Runs in GitHub Actions at 09:50/14:40 Beijing time. Produces an auditable
JSON outcome; actual selection requires a separately verified market-data
adapter, which is intentionally not fabricated here.
"""
import argparse
from datetime import datetime
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
    if not str(feed.get("source", "")).startswith("https://"):
        return "missing_source"
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
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                return "missing_market_evidence"
    return None


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
            outcome["snapshot"] = {"source": feed["source"], "as_of": feed["as_of"],
                                   "quote_count": len(feed["quotes"]),
                                   "validation": "format_and_freshness_only"}
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
