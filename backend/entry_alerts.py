"""Conservative, date-bound price-zone alerts for published A-share recommendations.

Reaching a price zone is *not* proof that a textual execution plan has passed.
No signal is called fully confirmed until all frozen execution conditions have
time-stamped evidence; this module deliberately does not make that claim.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

CN_TZ = ZoneInfo("Asia/Shanghai")
STRATEGY_RANK = {
    "combined_limitup_watch": 0,
    "limitup_single_v1": 1,
    "market_review_conditional": 2,
    "late_pair": 3,
}


def _range(row):
    raw = row.get("entry_price_condition_range") or row.get("reference_entry_range")
    if not isinstance(raw, (tuple, list)) or len(raw) != 2:
        return None
    try:
        low, high = float(raw[0]), float(raw[1])
        if not (0 < low <= high):
            return None
        return low, high
    except (TypeError, ValueError):
        return None


def scheduled_recommendations(items, day):
    """Only contemporaneous recommendations valid for today's entry session."""
    selected = {}
    for row in items:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code", ""))
        if (len(code) != 6 or not code.isascii() or not code.isdigit()
                or row.get("planned_entry_date") != day
                or row.get("provenance") != "contemporaneous"
                or row.get("strategy") not in STRATEGY_RANK
                or not _range(row) or not row.get("id")):
            continue
        former = selected.get(code)
        key = (STRATEGY_RANK[row["strategy"]], str(row.get("published_at", "")))
        if former is None or key[0] < STRATEGY_RANK[former["strategy"]] or (
                key[0] == STRATEGY_RANK[former["strategy"]] and key[1] > former.get("published_at", "")):
            selected[code] = row
    return list(selected.values())[:20]


def evaluate_entry_alerts(recommendations, quotes, now=None, session_live=False):
    """Require same-session, age-bounded vendor quotes and an intact price zone."""
    now = (now or datetime.now(CN_TZ)).astimezone(CN_TZ)
    day = now.date().isoformat()
    result = []
    if not session_live:
        return result
    indexed = {q.get("code"): q for q in quotes if isinstance(q, dict)}
    for row in recommendations:
        if row.get("planned_entry_date") != day:
            continue
        price_range = _range(row)
        quote = indexed.get(row.get("code"))
        if price_range is None or not quote:
            continue
        try:
            price = float(quote["price"])
            stamp = datetime.fromisoformat(str(quote["as_of"]))
            if stamp.tzinfo is None:
                continue
            stamp = stamp.astimezone(CN_TZ)
            age = (now - stamp).total_seconds()
            invalid = row.get("operational_invalid_price", row.get("invalid_level"))
            if invalid is not None and price <= float(invalid):
                continue
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
        if (stamp.date().isoformat() != day or not 0 <= age <= 120
                or not price_range[0] <= price <= price_range[1]):
            continue
        result.append({
            "id": str(row["id"]),
            "code": str(row["code"]),
            "name": str(row.get("name") or quote.get("name") or ""),
            "date_cn": day,
            "strategy": row["strategy"],
            "level": "price_zone",
            "all_conditions_verified": False,
            "price": round(price, 3),
            "pct": quote.get("pct"),
            "range_low": price_range[0],
            "range_high": price_range[1],
            "as_of": stamp.isoformat(timespec="seconds"),
            "source": quote.get("source", ""),
            "trigger": str(row.get("trigger") or ""),
            "invalid": str(row.get("invalid") or ""),
            "warning": "仅已进入计划建仓价位区间；竞价、回踩缩量、连续成交、板块和盘口等完整条件仍须核验，不能据此直接下单。",
        })
    return result
