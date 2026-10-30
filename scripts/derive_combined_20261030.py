"""Recompute observations without changing any frozen signal or execution rule."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
import importlib.util
import copy
import gzip
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from learning_loop import is_session, nth_session_after
from prepare_completion_20261023 import snapshot, pct, stats
from collect_20261019_combined import summarize_seats

T = "2026-10-30"
PREV = "2026-10-29"
TD = date.fromisoformat(T)


def load(path):
    return json.loads((ROOT / path).read_text())


def board(code, name=""):
    if code.startswith(("900", "200")):
        return "B_share_not_A_excluded_from_A_statistics"
    if "ST" in name.upper() or "退" in name:
        return "risk_warning_or_delisting_separate"
    if code.startswith(("30", "68")):
        return "growth_star_20pct"
    if code.startswith(("4", "8", "92")):
        return "beijing_30pct"
    return "ordinary_main_10pct" if code.startswith(("00", "60")) else "other_security_regime_unverified"


def checkpoints(raw, reference):
    if not raw.get("date_verified"):
        return {"status": "missing_date_verified_minute_prices"}
    points = [p for p in raw["points"] if "0930" <= p["clock"] <= "1130" or "1300" <= p["clock"] <= "1500"]
    by = {p["clock"]: p for p in points}
    return {"source": raw["source"], "date": T, "price_point_count": len(points),
            "auction_0925": None,
            "points": {k: {**by[k], "return_vs_reference_pct": pct(by[k]["price"], reference)}
                       if k in by else None for k in ("0930", "0945", "0950", "1030", "1130", "1400", "1430", "1440", "1500")},
            "full_minute_ohlc": False, "verified_fill": False,
            "note": "Dated quote price points and cumulative volume/amount; no intra-minute sequence, order book, queue fill or auction evidence."}


def path_observation(code, name, bs, anchor, minute=None):
    by = {b["date"]: b for b in bs}
    a, cur = by.get(anchor), by.get(T)
    if not a or not cur:
        return {"code": code, "name": name, "board_regime": board(code, name), "status": "missing_anchor_or_current_bar"}
    return {"code": code, "name": name, "base_date": anchor, "validation_date": T,
            "base_close": a["close"], "daily": cur, "open_pct": pct(cur["open"], a["close"]),
            "close_pct": pct(cur["close"], a["close"]), "mfe_pct": pct(cur["high"], a["close"]),
            "mae_pct": pct(cur["low"], a["close"]), "board_regime": board(code, name),
            "minute_checkpoints": checkpoints(minute or {}, a["close"]),
            "status": "price_observed", "executed_trade": False, "executable_net_return_pct": None}


def main():
    raw = load("tmp/combined-20261030-raw.json")
    extension = ROOT / "tmp/combined-20261030-extension.json"
    if extension.exists():
        ext = json.loads(extension.read_text())
        raw["daily_histories"].update(ext.get("daily_histories", {}))
        raw["minute_price_points"].update(ext.get("minute_price_points", {}))
        raw["seat_queries"].update(ext.get("seat_queries", {}))
        raw["limit_up_pools"].update(ext.get("limit_up_pools", {}))
    daily = {c: v["bars"] for c, v in raw["daily_histories"].items() if v["ok"]}
    market = load("docs/research/market-review-2026-10-30-evidence.json")
    prev = json.loads(gzip.decompress((ROOT / "docs/research/combined-pair-20261029-evidence.json.gz").read_bytes()))
    report = load("backend/data/research.json")["items"]
    previous_quotes = {q["code"]: q for page in prev["sina_pages"].values()
                       for q in page.get("payload", [])}
    out = {"market_date": T, "calculated_at": datetime.now(timezone.utc).isoformat()}
    broad = []
    for q in market["broad_pool"]:
        c = q["code"]
        if c not in daily:
            continue
        s = snapshot(c, q["name"], daily[c])
        prior_turnover = float(previous_quotes[c]["turnoverratio"]) if c in previous_quotes else None
        s.update(turnover_pct=float(q["turnoverratio"]), amount_yi=float(q["amount"]) / 1e8,
                 prior_turnover_pct=prior_turnover,
                 turnover_change_pct_points=round(float(q["turnoverratio"])-prior_turnover,5) if prior_turnover is not None else None,
                 intraday_volume_ratio=None, board_regime=board(c, q["name"]),
                 quote_crosscheck_max_ohlc_difference=max(abs(s[k]-float(q["trade" if k == "close" else k]))
                                                       for k in ("open", "high", "low", "close")),
                 source=raw["daily_histories"][c]["source"],
                 minute_checkpoints=checkpoints(raw["minute_price_points"].get(c, {}), daily[c][-2]["close"])
                    if len(daily[c]) >= 2 else {"status": "missing_previous_daily_bar"})
        cp = s["minute_checkpoints"].get("points", {})
        a14, last = cp.get("1400"), cp.get("1500")
        s["tail_1400_close_pct"] = pct(s["close"], a14["price"]) if a14 else None
        s["tail_volume_share_pct"] = ((last["cumulative_volume_lots"]-a14["cumulative_volume_lots"])
                                        / last["cumulative_volume_lots"] * 100) if a14 and last and last["cumulative_volume_lots"] else None
        s["previous_20_session_high"] = max(b["high"] for b in daily[c][-21:-1]) if len(daily[c]) >= 21 else None
        s["break_above_previous_20_high"] = s["close"] > s["previous_20_session_high"] if s["previous_20_session_high"] else None
        s["daily_volume_ratio_vs_previous"] = daily[c][-1]["volume"] / daily[c][-2]["volume"] if len(daily[c]) >= 2 and daily[c][-2]["volume"] else None
        s["missing"] = ["auction_0925", "verified_order_book_and_queue_fill", "intraday_comparable_volume_ratio", "full_historical_daily_turnover_curve"]
        if len(daily[c]) < 120:
            s["missing"].append("full_120_session_history")
        broad.append(s)
    lookup = {s["code"]: s for s in broad}
    deep = [lookup[q["code"]] for q in market["deep_pool"] if q["code"] in lookup]
    out["broad_recomputed"] = broad
    out["deep_recomputed"] = deep
    out["crosscheck"] = {"expected_broad": 120, "recomputed_broad": len(broad), "deep": len(deep),
                          "ohlc_mismatches": [{"code": s["code"], "difference": s["quote_crosscheck_max_ohlc_difference"]}
                                              for s in broad if s["quote_crosscheck_max_ohlc_difference"] > .011]}
    vp = load("backend/data/volume_price_samples.json")["items"]
    cohort = next(v for v in vp if v.get("id") == "volume-price-20261029-close-v1-cohort")
    previous_pool = [path_observation(s["code"], s["name"], daily.get(s["code"], []), PREV,
                                     raw["minute_price_points"].get(s["code"], {})) for s in cohort["samples"]]
    out["previous_whole_pool"] = previous_pool
    out["previous_whole_pool_summary"] = stats([r.get("close_pct") for r in previous_pool]) | {
        "mean_mfe_pct": round(mean(r["mfe_pct"] for r in previous_pool if "mfe_pct" in r), 3),
        "mean_mae_pct": round(mean(r["mae_pct"] for r in previous_pool if "mae_pct" in r), 3),
        "mae_le_minus5_n": sum(r.get("mae_pct", 0) <= -5 for r in previous_pool),
        "executed_trade_count": 0, "origin_cohort_id": cohort["id"],
        "unique_date_count": 1, "return_basis": "T29 close to T30 price observation, not D30 entry P/L"}
    lows = load("backend/data/low_position_samples.json")["items"]
    lv = []
    for s in lows:
        c = s["code"]; bars = daily.get(c, []); origin = date.fromisoformat(s["date"]); ref = float(s["day0_close"])
        by = {b["date"]: b for b in bars}; anchor = by.get(s["date"]); cur = by.get(T)
        expected = []; day = origin + timedelta(days=1)
        while day <= TD:
            if is_session(day): expected.append(day.isoformat())
            day += timedelta(days=1)
        missing = [d for d in expected if d not in by]
        path = [b for b in bars if s["date"] < b["date"] <= T]
        match = anchor is not None and abs(anchor["close"] - ref) <= .011
        invalid = s.get("invalid_close_below")
        broken = [b["date"] for b in path if invalid is not None and b["close"] < invalid]
        peak = ref; drawdown = 0
        for b in path:
            peak = max(peak, b["close"]); drawdown = min(drawdown, b["close"] / peak - 1)
        cm = []
        for n in (1, 3, 5, 10, 15, 20, 30):
            target = origin + timedelta(days=n)
            available = [b for b in bars if b["date"] <= target.isoformat()]
            b = available[-1] if target <= TD and available else None
            cm.append({"day": n, "target_date": target.isoformat(), "quote_date": b["date"] if b else None,
                       "close_pct": pct(b["close"], ref) if b else None,
                       "status": "price_observed" if b else "pending" if target > TD else "missing"})
        tm = []
        for n in (5, 10, 20, 30):
            target = expected[n-1] if len(expected) >= n else None; b = by.get(target)
            tm.append({"session": n, "date": target, "close_pct": pct(b["close"], ref) if b else None,
                       "status": "observed" if b else "missing" if target else "pending"})
        lv.append({"id": s["id"] + "-close-20261030-v1", "origin_cohort_id": s["id"], "code": c, "name": s["name"],
            "date": T, "reference_date": s["date"], "reference_close": ref,
            "original_reference_matches_unadjusted_daily": match,
            "original_snapshot_verified": s.get("original_snapshot_verified", False),
            "eligible_for_model_statistics": bool(s.get("eligible_for_model_statistics") and match and not missing),
            "price_observation": cur, "close_return_pct": pct(cur["close"], ref) if cur else None,
            "path_mfe_pct": pct(max(b["high"] for b in path), ref) if path else None,
            "path_mae_pct": pct(min(b["low"] for b in path), ref) if path else None,
            "max_close_to_close_drawdown_pct": round(drawdown*100, 3),
            "elapsed_natural_days": (TD-origin).days, "elapsed_trading_sessions": len(expected),
            "observed_trading_sessions": len(path), "missing_sessions": missing,
            "thirty_natural_days_matured": (TD-origin).days >= 30, "thirty_sessions_matured": len(expected) >= 30,
            "first_verified_close_below_original_invalid": broken[0] if broken else None,
            "ever_verified_close_below_original_invalid": bool(broken), "original_invalid_close_below": invalid,
            "calendar_milestones": cm, "trading_milestones": tm,
            "current_structure": snapshot(c, s["name"], bars) if cur else None,
            "minute_checkpoints": checkpoints(raw["minute_price_points"].get(c, {}), ref),
            "report_ids": ["low-position-20261030-close-v1"], "executed_trade": False,
            "executable_net_return_pct": None, "full_validation_completed": bool(cur and not missing),
            "calculation_version": "low_price_observation_v3_including_anchor_in_close_drawdown",
            "evidence_status": "single_provider_unadjusted_daily_path",
            "sources": [raw["daily_histories"].get(c, {}).get("source")],
            "missing": ["historical_minute_OHLC", "order_and_fill_evidence"]})
    out["low_validations"] = lv
    out["low_summary"] = {"count": len(lv), "unique_codes": len({s["code"] for s in lv}),
                           "mature_calendar_30": sum(s["thirty_natural_days_matured"] for s in lv),
                           "eligible_mature_calendar_30": sum(s["thirty_natural_days_matured"] and s["eligible_for_model_statistics"] for s in lv),
                           "all_paths_complete": all(s["full_validation_completed"] for s in lv)}
    models = []
    for m in sorted({s.get("primary_model", "unknown") for s in lows}):
        ids = {s["id"] for s in lows if s.get("primary_model", "unknown") == m}
        rows = [s for s in lv if s["origin_cohort_id"] in ids]
        eligible = [s for s in rows if s["eligible_for_model_statistics"]]
        mature = [s for s in eligible if s["thirty_natural_days_matured"]]
        vals = [next(v["close_pct"] for v in s["calendar_milestones"] if v["day"] == 30) for s in mature]
        models.append({"model": m, "all_n": len(rows), "eligible_n": len(eligible),
                       "mature_30d_eligible_n": len(mature), "frozen_30d_close_statistics": stats(vals),
                       "current_variable_age_statistics_not_30d": stats([s["close_return_pct"] for s in rows]),
                       "ever_original_invalidation_broken_n": sum(s["ever_verified_close_below_original_invalid"] for s in rows)})
    out["low_model_statistics"] = models
    fetched = {(k.split(":")[0], k.split(":")[1]): v for k, v in raw["seat_queries"].items()}
    lhb_rows = raw["lhb_lists"][T]["payload"]["result"]["data"]
    selected = []
    ths_raw = load("tmp/combined-20261030-ths.json")
    ths = (ths_raw.get("tables") or [[], [], [], [], [], []])[5]
    out["seat_query_missing_or_not_disclosed"] = []
    for code in sorted({c for c, _ in fetched}):
        options = [r for r in lhb_rows if r["SECURITY_CODE"] == code]
        if not options or not all(fetched.get((code, side), {}).get("ok") for side in ("BUY", "SELL")):
            out["seat_query_missing_or_not_disclosed"].append({"code": code, "listed_on_T": bool(options), "buy_query_ok": fetched.get((code, "BUY"), {}).get("ok"), "sell_query_ok": fetched.get((code, "SELL"), {}).get("ok")})
            continue
        options.sort(key=lambda r: ("连续" in r["EXPLANATION"], str(r["TRADE_ID"])))
        s = summarize_seats(options[0], fetched)
        union = {(str(r.get("OPERATEDEPT_CODE")), r.get("BUY"), r.get("SELL"), str(r.get("TRADE_ID"))): r
                 for r in s["buy_seats_em"] + s["sell_seats_em"]}
        for tag, term in (("institution", "机构专用"), ("stock_connect", "股通")):
            rows = [r for r in union.values() if term in str(r.get("OPERATEDEPT_NAME", ""))]
            s[tag + "_net_wan"] = round(sum(float(r.get("BUY") or 0)-float(r.get("SELL") or 0) for r in rows)/1e4, 3)
        s["period"] = "multi_day" if "连续" in s["selected_period_reason"] else "single_day"
        period_label = "3日" if s["period"] == "multi_day" else ""
        summary = next((r for r in ths if len(r) >= 7 and str(r[1]).zfill(6) == code and (r[0] or "") == period_label), None)
        s["ths_same_period_summary"] = summary
        s["ths_close_match"] = summary is not None and abs(float(summary[3])-s["close"]) <= .011
        s["price_structure"] = snapshot(code, s["name"], daily[code])
        s["board_regime"] = board(code, s["name"])
        selected.append(s)
    out["dragon_selected"] = selected
    old_codes = {r["SECURITY_CODE"]: r for r in prev["lhb_lists"][PREV]["payload"]["result"]["data"]}
    previous_dragon = []
    for c, r in sorted(old_codes.items()):
        bars = daily.get(c, [])
        observation = path_observation(c, r["SECURITY_NAME_ABBR"], bars, PREV,
                                      raw["minute_price_points"].get(c, {}))
        # Some Beijing symbols expose only the current daily candle through Tencent.
        # The previous closing anchor was actually archived on T27 in the disclosure
        # list. Use it explicitly, without claiming an unavailable historical path.
        if observation["status"] != "price_observed" and bars and bars[-1]["date"] == T:
            ref = float(r["CLOSE_PRICE"]); cur = bars[-1]
            observation = {"code": c, "name": r["SECURITY_NAME_ABBR"], "base_date": PREV,
                "validation_date": T, "base_close": ref, "daily": cur,
                "open_pct": pct(cur["open"], ref), "close_pct": pct(cur["close"], ref),
                "mfe_pct": pct(cur["high"], ref), "mae_pct": pct(cur["low"], ref),
                "board_regime": board(c, r["SECURITY_NAME_ABBR"]), "status": "price_observed",
                "reference_source": "docs/research/combined-pair-20261029-evidence.json.gz:lhb_lists:2026-10-29:CLOSE_PRICE",
                "current_source": raw["daily_histories"][c]["source"],
                "historical_daily_path_available": False, "executed_trade": False,
                "executable_net_return_pct": None,
                "note": "T28 archived closing anchor plus dated T29 OHLC only; no multi-session sequence inferred."}
        previous_dragon.append(observation)
    out["dragon_previous_whole_disclosed_pool"] = previous_dragon
    old_focus = {r["code"] for r in prev["derived"]["dragon_selected"]}
    out["dragon_previous_focused_eight"] = [r for r in out["dragon_previous_whole_disclosed_pool"] if r["code"] in old_focus]
    out["dragon_previous_by_board"] = {}
    for b in sorted({r["board_regime"] for r in out["dragon_previous_whole_disclosed_pool"] if "board_regime" in r}):
        a = [r for r in out["dragon_previous_whole_disclosed_pool"] if r.get("board_regime") == b]
        out["dragon_previous_by_board"][b] = stats([r.get("close_pct") for r in a])
    raw["limit_up_pools"][PREV] = prev["limit_up_pools"][PREV]
    raw["limit_up_pools"]["2026-10-28"] = prev["limit_up_pools"]["2026-10-28"]
    pools = {d: copy.deepcopy((r.get("payload", {}).get("data") or {}).get("pool", [])) for d, r in raw["limit_up_pools"].items()}
    # T28's two independently verified omissions were published before T29.
    # Freeze that whole denominator, rather than looking back from today's winners.
    pools[PREV] += copy.deepcopy(prev["derived"]["limit_pool_reconciliation"]["added_records"])
    quote_check = load("tmp/combined-20261030-quote-upper-check.json")
    prior_pool = {r["c"]: r for r in pools[PREV]}
    additions = []
    vendor_codes = {r["c"] for r in pools[T]}
    for symbol, fs in sorted(quote_check["provider_fields"].items()):
        code=fs[2]
        if board(code,fs[1])!="ordinary_main_10pct" or not fs[30].startswith("20261030"):
            continue
        if not fs[47] or abs(float(fs[3])-float(fs[47]))>=.001 or code in vendor_codes:
            continue
        assert code in daily and abs(daily[code][-1]["close"] - float(fs[3])) < .001
        additions.append({"c": code, "n": fs[1], "p": round(float(fs[3])*1000),
            "lbc": int(prior_pool[code]["lbc"])+1 if code in prior_pool else 1,
            "fbt": None, "lbt": None, "zbc": None,
            "hs": float(raw["quotes"][code]["turnoverratio"]),
            "independent_correction": True, "verified_upper": float(fs[47]),
            "quote_timestamp": fs[30], "source": quote_check["source"]})
    out["limit_pool_reconciliation"] = {"original_provider_count": len(pools[T]),
        "added_records": additions, "original_pool_preserved": True,
        "basis": "T29 Tencent provider upper-price field 47 equals close, matched to Sina and dated unadjusted history; T28 denominator includes its already published independent corrections. Seal times/open counts remain unknown."}
    pools[T] = pools[T] + additions
    out["board_ladder"] = {}
    for d, pool in pools.items():
        ordinary = [r for r in pool if board(r["c"], r["n"]) == "ordinary_main_10pct"]
        grouped = {str(n): [{"code": r["c"], "name": r["n"], "consecutive_boards": r["lbc"],
                             "close": r["p"]/1000, "first_seal": r["fbt"], "last_seal": r["lbt"],
                             "open_count_provider": r["zbc"], "turnover_pct": r["hs"]}
                            for r in ordinary if (r["lbc"] == n if n < 5 else r["lbc"] >= 5)] for n in range(1, 6)}
        out["board_ladder"][d] = {"ordinary_main_count": len(ordinary), "layers": grouped,
            "source": raw["limit_up_pools"][d]["source"], "provider_qdate": raw["limit_up_pools"][d]["payload"]["data"].get("qdate"),
            "period_warning": "qdate is retrieval-day metadata even for historical queries; prices are independently checked against requested-session bars."}
    current = {r["c"]: r for r in pools[T]}
    progression = {}
    for n in (1, 2, 3, 4, 5, 6):
        denominator = [r for r in pools[PREV] if r["lbc"] == n and board(r["c"], r["n"]) == "ordinary_main_10pct"]
        rows = []
        for r in denominator:
            c = r["c"]; by = {v["date"]: v for v in daily.get(c, [])}; a, cur = by.get(PREV), by.get(T)
            match = a is not None and abs(a["close"] - r["p"]/1000) <= .011
            status = "advanced" if match and c in current and current[c]["lbc"] == n+1 else "broken" if match and cur else "missing"
            rows.append({"code": c, "name": r["n"], "prior_boards": n, "prior_close_price_verified": match,
                         "status": status, "T_close": cur["close"] if cur else None})
        count = Counter(r["status"] for r in rows)
        progression[f"{n}_to_{n+1}"] = {"prior_full_denominator": len(rows), "advanced": count["advanced"],
              "broken": count["broken"], "missing": count["missing"], "rows": rows,
              "verified_advancement_pct": round(count["advanced"]/(count["advanced"]+count["broken"])*100, 3)
                    if count["advanced"]+count["broken"] else None,
              "origin": "T28 full-pool archive including previously published corrections, frozen before T29 outcomes; never reverse inferred from today's winners"}
    out["progression_main_10pct"] = progression
    repeats = {}
    prev_dates = []; d = TD-timedelta(days=1)
    while len(prev_dates) < 10:
        if is_session(d):prev_dates.append(d.isoformat())
        d -= timedelta(days=1)
    for n in (5, 10):
        existing = [r for r in report if r.get("task_id") == "market_review" and r.get("eligible_for_integrated_research") is True and r.get("codes") and r["date"] in prev_dates[:n]]
        seen = {c for r in existing for c in r["codes"]}
        overlap = sorted({r["code"] for r in deep} & seen)
        repeats[str(n)] = {"requested_dates": prev_dates[:n], "covered_dates": sorted({r["date"] for r in existing}),
                           "coverage_complete": len({r["date"] for r in existing}) == n,
                           "overlap_codes": overlap, "available_archive_overlap_pct": round(len(overlap)/len(deep)*100, 3),
                           "strict_window_repeat_rate": None if len({r["date"] for r in existing}) < n else round(len(overlap)/len(deep)*100, 3)}
    out["repeat_audit"] = repeats
    path = ROOT / "tmp/combined-20261030-derived.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(path.relative_to(ROOT)), "crosscheck": out["crosscheck"],
        "previous_pool": out["previous_whole_pool_summary"], "low": out["low_summary"],
        "seat_reconciliation": [(s["code"], s["period"], s["institution_net_wan"], s["stock_connect_net_wan"], s["seat_reconciliation"]["matched"], s["ths_close_match"]) for s in selected],
        "progression": {k: {q: v for q, v in r.items() if q not in ("rows", "origin")} for k, r in progression.items()},
        "low_compare": [{k: s.get(k) for k in ("code", "name", "close", "range_position_pct", "distance_ma20_pct", "rvol", "clv")}
                        for s in broad if s["code"] in ["603007", "603331", "001219", "603719", "002991", "688096"]]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
