#!/usr/bin/env python3
"""Reproducible Oct 16 evidence; no fills inferred from daily or price points."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import json
from pathlib import Path
import statistics

import pandas as pd
import collect_20261015_combined as helper

ROOT = Path(__file__).resolve().parents[1]
T, PREV = "2026-10-16", "2026-10-15"
helper.T, helper.T_COMPACT = T, "20261016"
TARGET = ROOT / "docs/research/combined-pair-2026-10-16-evidence.json"


def load(path):
    return json.loads((ROOT / path).read_text())


def validate(codes, histories, minutes):
    rows = []
    for code in codes:
        bars = histories.get(code) or []
        base, current = helper.by_date(bars, PREV), helper.by_date(bars, T)
        if not base or not current:
            rows.append({"code": code, "status": "missing_target_or_reference_bar"})
            continue
        rows.append({
            "code": code, "reference_date": PREV, "validation_date": T,
            "reference_close": base["close"], "open": current["open"],
            "high": current["high"], "low": current["low"], "close": current["close"],
            "open_return_pct": helper.pct(current["open"], base["close"]),
            "high_observation_pct": helper.pct(current["high"], base["close"]),
            "low_observation_pct": helper.pct(current["low"], base["close"]),
            "close_return_pct": helper.pct(current["close"], base["close"]),
            "minute_checkpoints": helper.minute_checkpoints(
                (minutes.get(code) or {}).get("20261016", []), base["close"]),
            "trigger_status": "no_uniform_frozen_trigger_or_not_verified",
            "observation_type": "price_observation", "executed_trade": False,
            "executable_net_return_pct": None,
            "source_urls": [f"{helper.DAILY}?param={helper.symbol(code)},day,,,180,none",
                            f"{helper.FIVE_DAY}?code={helper.symbol(code)}"],
        })
    return rows


def stats(rows):
    valid = [r for r in rows if "close_return_pct" in r]
    out = {"expected": len(rows), "verified": len(valid), "executable_sample_count": 0,
           "positive_close_count": sum(r["close_return_pct"] > 0 for r in valid),
           "strategy_win_rate": None, "net_return_pct": None}
    for field in ("open_return_pct", "close_return_pct", "high_observation_pct", "low_observation_pct"):
        vals = [r[field] for r in valid]
        out["mean_" + field] = helper.mean(vals)
        out["median_" + field] = helper.median(vals)
    return out


def main():
    started_at_utc = datetime.now(timezone.utc).isoformat()
    market = load("docs/research/market-review-2026-10-16-evidence.json")
    prior = load("docs/research/combined-pair-2026-10-15-evidence.json")
    low_doc = load("backend/data/low_position_samples.json")
    prior_volume = [r["code"] for r in prior["volume_price"]["deep_samples"]]
    prior_dragon = [r["code"] for r in prior["dragon_tiger"]["selected_observations"]]
    low_codes = [r["code"] for r in low_doc["items"]]

    failures = {}
    lhb_rows, tables = [], []
    try:
        payload = helper.request_json(helper.LHB_EM, {
            "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW", "columns": "ALL",
            "filter": "(TRADE_DATE='2026-10-16')", "pageNumber": 1, "pageSize": 500,
            "source": "WEB", "client": "WEB"})
        lhb_rows = (payload.get("result") or {}).get("data") or []
        if not lhb_rows:
            failures["lhb_eastmoney"] = "empty_same_day_list"
    except Exception as exc:
        failures["lhb_eastmoney"] = f"{type(exc).__name__}:{exc}"
    try:
        html = helper.request_bytes("https://data.10jqka.com.cn/market/longhu/date/2026-10-16/", timeout=40)
        tables = pd.read_html(BytesIO(html))
    except Exception as exc:
        failures["lhb_ths"] = f"{type(exc).__name__}:{exc}"

    listed_codes = [r["SECURITY_CODE"] for r in lhb_rows
                    if r.get("SECURITY_CODE", "").startswith(("00", "30", "60", "68"))]
    codes = sorted(set([r["code"] for r in market["deep_pool"]] + prior_volume +
                       prior_dragon + low_codes + listed_codes + ["600825", "300450", "000973", "002812"]))
    qfq, qfq_errors = helper.fetch_parallel(codes, lambda c: helper.daily_bars(c, True), workers=8)
    raw, raw_errors = helper.fetch_parallel(codes, lambda c: helper.daily_bars(c, False), workers=8)
    minute_codes = sorted(set(prior_volume + prior_dragon + [r["code"] for r in market["deep_pool"]]))
    minutes, minute_errors = helper.fetch_parallel(minute_codes, helper.five_day_minutes, workers=3)

    deep = helper.enrich_deep(market["deep_pool"], qfq)
    prior_map = {r["code"]: r for r in prior["volume_price"]["deep_samples"]}
    for row in deep:
        bars = qfq[row["code"]]
        row["distance_ma20_pct"] = helper.pct(row["close"], row["ma"]["20"])
        rate = Decimal("0.20") if row["code"].startswith(("30", "68")) else Decimal("0.10")
        expected_upper = float((Decimal(str(row["previous_close"])) * (1 + rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        row["board_limit_regime"] = "20%" if rate == Decimal("0.20") else "10%"
        row["calculated_upper_reference"] = expected_upper
        row["calculated_upper_verified_exchange_quote"] = False
        if abs(row["close"] - expected_upper) < .011:
            row["structure"] = "封板观察/次日普通成交待核验"
        elif row["clv"] < .65 or (row.get("tail_return_1400_to_1500_pct") is not None and row["tail_return_1400_to_1500_pct"] < -1.5):
            row["structure"] = "放量冲高回落/承接不足"
        elif row["rvol"]["20"] >= 3 and row["distance_ma20_pct"] > 20:
            row["structure"] = "高乖离高量/分歧风险"
        elif row["range_position_pct"].get("120") is not None and row["range_position_pct"]["120"] <= 55:
            row["structure"] = "低中位放量推进/待次日承接"
        else:
            row["structure"] = "放量推进/待次日承接"
        row["moving_average_alignment"] = "MA5>MA20>MA60" if row["ma"]["5"] > row["ma"]["20"] > row["ma"]["60"] else "not_full_bullish_alignment"
        previous = prior_map.get(row["code"])
        row["turnover_change_pct_points"] = round(row["turnover_pct"] - previous["turnover_pct"], 3) if previous else None
        row["intraday_volume_ratio"] = None
        row["intraday_volume_ratio_note"] = "收盘RVOL与盘中量比分开；无同一时点量比快照"
        row["minute_checkpoints"] = helper.minute_checkpoints(
            (minutes.get(row["code"]) or {}).get("20261016", []), row["previous_close"])
        row["daily_crosscheck"] = {"source":"Sina archived full-market close versus Tencent unadjusted daily",
                                   "max_ohlc_difference": max(abs(row[k] - raw[row["code"]][-1][k]) for k in ("open", "high", "low", "close")) if raw.get(row["code"]) else None}
        row["prior5_high"] = max(r["high"] for r in bars[-6:-1])
        row["prior20_low"] = min(r["low"] for r in bars[-21:-1])

    volume_validation = validate(prior_volume, raw, minutes)
    dragon_validation = validate(prior_dragon, raw, minutes)
    low_validation = helper.low_validations(low_doc["items"], raw)
    for row in low_validation:
        row["report_ids"] = ["low-position-20261016-close-v1"]

    # Use a mechanically selected comparison set for detailed seats, not a recommendation.
    net_ranked = sorted(lhb_rows, key=lambda x: float(x.get("BILLBOARD_NET_AMT") or 0), reverse=True)
    chosen = []
    deep_codes = {r["code"] for r in deep}
    for row in net_ranked:
        code = row.get("SECURITY_CODE")
        if code in deep_codes and code not in chosen:
            chosen.append(code)
        if len(chosen) == 5:
            break
    if tables and lhb_rows:
        lhb = helper.summarize_lhb(lhb_rows, tables, chosen)
        for row in lhb["selected_observations"]:
            bars = qfq.get(row["code"], [])
            if bars:
                current = bars[-1]
                row["range_position_pct"] = {str(n): helper.range_position(bars, n) for n in (20, 60, 120)}
                row["rvol20"] = round(current["volume"] / helper.volume_mean(bars, 20), 3) if helper.volume_mean(bars,20) else None
                row["clv"] = round((current["close"]-current["low"])/(current["high"]-current["low"]),3) if current["high"]>current["low"] else None
    else:
        lhb = {"raw_reason_rows":len(lhb_rows),"selected_observations":[],"complete":False}

    combined = validate(["000973", "002812"], raw, minutes)
    for row in combined:
        pts = (minutes.get(row["code"]) or {}).get("20261016", [])
        if row["code"] == "000973":
            row["trigger_status"] = "not_triggered_required_12_20_reclaim_absent" if row.get("high",99)<12.20 else "unverified"
        elif pts:
            pullback = next((p for p in pts if 47.40 <= p["price"] <= 47.90), None)
            later = [p for p in pts if pullback and p["clock"] > pullback["clock"]]
            row["pullback_first_point"] = pullback
            row["max_price_after_pullback"] = max([p["price"] for p in later], default=None)
            row["trigger_status"] = "not_triggered_price_points_no_reclaim_after_pullback" if later and max(p["price"] for p in later)<48.60 else "unverified"
        row["minute_evidence_limit"] = "价格点不是OHLC；点间瞬时触发仍无逐笔证据，不认定成交"

    result = {
        "market_date": T, "previous_trading_day": PREV,
        "collection_started_at_utc": started_at_utc,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_market_evidence": "docs/research/market-review-2026-10-16-evidence.json",
        "market_review_reused": {"report_id":"market-review-20261016-close-v1", "coverage":market["coverage"]},
        "volume_price": {"rule_version":"volume_price_close_v3","deep_samples":deep,"deep_expected":28,
                         "previous_cohort_id":"volume-price-20261015-close-v1-cohort",
                         "previous_validations":volume_validation,"previous_statistics":stats(volume_validation)},
        "low_position": {"rule_version":"low_position_30d_v1","existing_expected":len(low_doc["items"]),
                         "existing_validations":low_validation,
                         "new_candidates":helper.choose_new_low(deep,set(low_codes))},
        "dragon_tiger": {**lhb,"rule_version":"dragon_tiger_close_v2",
                         "previous_validations":dragon_validation,"previous_statistics":stats(dragon_validation),
                         "raw_reason_rows_data":lhb_rows},
        "prior_combined": combined,
        "raw_daily_histories":raw,"qfq_daily_histories":qfq,"minute_price_paths":minutes,
        "provider_failures":{**failures,"qfq":qfq_errors,"raw":raw_errors,"minutes":minute_errors},
        "sources":["docs/research/market-review-2026-10-16-evidence.json",helper.DAILY,helper.FIVE_DAY,
                   helper.LHB_EM,"https://data.10jqka.com.cn/market/longhu/date/2026-10-16/"],
        "limits":["No auction/verified OHLC/order-book/ticks/fills; no executable return inferred",
                  "Public seats are channels, not beneficial-owner or fund-identity proof",
                  "No missing day backfill is presented as a contemporaneous intraday recommendation"]}
    TARGET.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"file":str(TARGET),"deep":len(deep),"prior_volume":stats(volume_validation),
                      "low_validated":len(low_validation),"new_low":[r["code"] for r in result["low_position"]["new_candidates"]],
                      "lhb_rows":len(lhb_rows),"lhb_selected":chosen,"failures":result["provider_failures"]},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
