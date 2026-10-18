"""Strict read-only partial confirmation of structured A-share recommendation rules.

Never convert a quote or bar into an asserted fill or a fully verified order.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import math

CN = ZoneInfo("Asia/Shanghai")
NEEDED = {"entry_sequence_required", "entry_window_cn", "auction_open_range",
          "pullback_range", "pullback_floor", "reclaim", "hold_minute_price_points",
          "peer_codes", "peers_each_min_change_pct", "at_least_one_peer_positive",
          "same_scope_advance_min", "ordinary_mainboard_limit_down_max"}


def timestamp(value):
    try:
        at = datetime.fromisoformat(str(value))
        return at.astimezone(CN) if at.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def fresh(at, now, max_age=120):
    return at is not None and at.date() == now.date() and 0 <= (now - at).total_seconds() <= max_age


def quote_valid(q, now):
    if not isinstance(q, dict) or not fresh(timestamp(q.get("as_of")), now):
        return False
    try:
        return float(q["price"]) > 0 and math.isfinite(float(q["pct"]))
    except (ValueError, TypeError, KeyError):
        return False


def minute_rows(payload, now):
    if (not isinstance(payload, dict) or not payload.get("ok") or payload.get("stale")
            or payload.get("refreshing") or payload.get("source") != "eastmoney_trends"):
        return []
    rows = []
    for item in payload.get("bars") or []:
        if not isinstance(item, dict) or item.get("ohlc_verified") is False:
            return []
        stamp = timestamp(str(item.get("time", "")).replace(" ", "T") + "+08:00")
        if stamp is None or stamp.date() != now.date():
            return []
        try:
            op, hi, lo, cl, vol = [float(item[k]) for k in
                                   ("open", "high", "low", "close", "volume")]
        except (ValueError, TypeError, KeyError):
            return []
        if (not all(math.isfinite(v) for v in (op, hi, lo, cl, vol))
                or min(op, hi, lo, cl) <= 0 or vol < 0 or hi < max(op, cl, lo)
                or lo > min(op, cl, hi)):
            return []
        rows.append((stamp, op, hi, lo, cl, vol))
    if (not rows or not fresh(rows[-1][0], now, 150)
            or len({r[0] for r in rows}) != len(rows)
            or rows != sorted(rows, key=lambda row: row[0])):
        return []
    return rows


def sequential(rows):
    return all((rows[i][0] - rows[i-1][0]) == timedelta(minutes=1)
               for i in range(1, len(rows)))


def volume_reclaim_sequence(bars, rules):
    try:
        begin, end = [datetime.strptime(str(t), "%H:%M").time()
                      for t in rules["entry_window_cn"]]
        low, high = map(float, rules["pullback_range"])
        floor, reclaim = float(rules["pullback_floor"]), float(rules["reclaim"])
        hold = int(rules["hold_minute_price_points"])
        if not (time(9, 30) < begin < end <= time(15) or False):
            return False
        if not (0 < floor <= low <= high < reclaim and 2 <= hold <= 12):
            return False
    except (KeyError, ValueError, TypeError):
        return False

    # Fully dated, contiguous, positive-volume 5m push -> 5m quieter
    # pullback -> N contiguous reclaim points. Never interpolate a missing bar.
    for i in range(5, len(bars) - 5 - hold + 1):
        push, pull = bars[i-5:i], bars[i:i+5]
        if not (sequential(push) and sequential(pull)
                and all(r[5] > 0 for r in push + pull)):
            continue
        if not (begin <= pull[0][0].time() <= pull[-1][0].time() <= end):
            continue
        if (max(r[2] for r in push) < reclaim
                or min(r[3] for r in pull) < floor
                or not any(low <= r[4] <= high for r in pull)
                or max(r[4] for r in pull) > high
                or sum(r[5] for r in pull) >= sum(r[5] for r in push)):
            continue
        for j in range(i+5, len(bars)-hold+1):
            held = bars[j:j+hold]
            if (not sequential(held) or
                    not begin <= held[0][0].time() <= held[-1][0].time() <= end
                    or held[0][0] - pull[-1][0] > timedelta(minutes=20)):
                continue
            if (all(r[4] >= reclaim and r[5] > 0 for r in held)
                    and min(r[3] for r in bars[i:j+hold]) >= floor):
                return True
    return False


def assess(row, current_quote, minute, peer_quotes, market, now):
    now = now.astimezone(CN)
    rules = row.get("rules") or {}
    if (not isinstance(rules, dict) or rules.get("version") != "combined_limitup_watch_v5"
            or not NEEDED.issubset(rules) or rules.get("entry_sequence_required") is not True):
        return {"supported": False, "technical_confirmed": False,
                "all_conditions_verified": False,
                "gates": [{"key": "frozen_rules", "status": "unknown",
                            "detail": "推荐条件未全部结构化，无法自动确认"}]}

    gates = []
    def add(key, passes, success, unavailable):
        gates.append({"key": key, "status": "passed" if passes else "unknown",
                      "detail": success if passes else unavailable})

    bars = minute_rows(minute, now)
    try:
        open_bar = next((b for b in bars if b[0].time() == time(9, 30)), None)
        lo, hi = map(float, rules["auction_open_range"])
        opening = bool(open_bar and lo <= open_bar[1] <= hi)
        start, end = [datetime.strptime(s, "%H:%M").time()
                      for s in rules["entry_window_cn"]]
    except (ValueError, TypeError, KeyError):
        opening, start, end = False, time(0), time(0)
    add("open", opening, "开盘分钟价符合范围", "9:30有效开盘数据/竞价范围未核实")

    sequence = volume_reclaim_sequence(bars, rules) if bars else False
    add("minute_volume_reclaim", sequence,
        "连续5分钟缩量回踩 + 规则要求的分钟数站回确认价",
        "未获得完整且新鲜的先上冲、缩量回踩、再站回分钟序列")

    indexed = {q.get("code"): q for q in (peer_quotes or []) if isinstance(q, dict)}
    peers = [indexed.get(c) for c in rules["peer_codes"]]
    peers_ok = (bool(peers) and all(quote_valid(q, now) for q in peers)
                and all(float(q["pct"]) >= float(rules["peers_each_min_change_pct"])
                        for q in peers))
    if peers_ok and rules["at_least_one_peer_positive"]:
        peers_ok = any(float(q["pct"]) > 0 for q in peers)
    add("peers", peers_ok,
        "冻结名单的板块对照行情达标", "板块对照未达标或报价时效不足")

    window_ok = quote_valid(current_quote, now) and start <= now.time() <= end
    add("window", window_ok, "仍在规定观察时间段",
        "不在规定观察窗口或现价来源已过期")
    # Market cache often covers only a capped subset. Never treat it as all-A.
    market_ok = (bool((market or {}).get("breadth_complete"))
                 and fresh(timestamp((market or {}).get("time_cn")), now)
                 and int((market or {}).get("advance", -1)) >=
                     int(rules["same_scope_advance_min"]))
    add("breadth", market_ok, "全市场红盘覆盖达标",
        "全A覆盖、时效或红盘数量尚不足")
    add("mainboard_limitdown", False, "",
        "普通主板跌停家数缺少经过核验的全量数据")
    add("auction", False, "", "9:25竞价成交价未留存可信快照")
    add("trade_validity", False, "", "停牌、风险警示、除权、真实涨停价与可成交性待核实")

    # Technical *subset* only. Insufficient authority to claim buy/full signal.
    subset = bool(opening and sequence and peers_ok and window_ok)
    return {"supported": True, "technical_confirmed": subset,
            "all_conditions_verified": False, "gates": gates}
