#!/usr/bin/env python3
"""Retroactively verify REAL T=2026-11-02 day bars for T30 frozen study pools.

This is not a historical signal generator or proof of 09:50/14:40 trades.
The universe is exactly the published pre-existing T30 broad, deep, low-position
and shadow cohorts, never selected by 11/02 winners or today's quotes.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
from pathlib import Path
import sys
from statistics import mean, median
from urllib.parse import quote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from daily_providers import tencent_daily
from quote_providers import stock_symbol

T = "2026-10-30"
D = "2026-11-02"
CN = ZoneInfo("Asia/Shanghai")
EVIDENCE = ROOT / "docs/research/market-review-2026-10-30-evidence.json"
LOWS = ROOT / "backend/data/low_position_samples.json"
SHADOW = ROOT / "docs/research/shadow-experiments-20261102-v1.json"
DEST = ROOT / "docs/research/frozen-price-observation-20261102.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def stock_codes(snapshot, low_samples, shadows):
    broad = {str(q["code"]): q for q in snapshot["broad_pool"]}
    deep = {str(q["code"]) for q in snapshot["deep_pool"]}
    low = {str(q["code"]) for q in low_samples["items"] if q.get("code")}
    shadow = {str(q["code"]) for q in shadows["signals"]}
    codes = sorted(set(broad) | low | shadow)
    return codes, broad, deep, low, shadow


def observe(code, provider=tencent_daily):
    # No forward-adjusted bar can be used to compare with a raw frozen close.
    bars = provider(code, limit=180, adjust="0")
    dated = {bar["date"]: bar for bar in bars}
    if T not in dated or D not in dated:
        raise ValueError("missing_exact_T_or_D_day_bar")
    a, b = dated[T], dated[D]
    if a["close"] <= 0 or b["volume"] < 0:
        raise ValueError("invalid_price_volume")
    return {
        "code": code, "prev": a, "current": b,
        "close_pct": round((b["close"] / a["close"] - 1) * 100, 5),
        "open_pct": round((b["open"] / a["close"] - 1) * 100, 5),
        "daily_high_excursion_pct": round((b["high"] / a["close"] - 1) * 100, 5),
        "daily_low_excursion_pct": round((b["low"] / a["close"] - 1) * 100, 5),
        "clv": round((b["close"] - b["low"]) / (b["high"] - b["low"]), 5) if b["high"] > b["low"] else None,
        "source": "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=" +
                  quote(stock_symbol(code) + ",day,,,180,none", safe=""),
    }


def collect(provider=tencent_daily, workers=6):
    snapshot, lows, shadow_doc = load(EVIDENCE), load(LOWS), load(SHADOW)
    assert snapshot["market_date"] == T and shadow_doc["T"] == T and shadow_doc["planned_D"] == D
    codes, broad, deep, low, shadow = stock_codes(snapshot, lows, shadow_doc)
    # The freeze must be pre-D, not reconstructed using retrospective performance.
    assert datetime.fromisoformat(shadow_doc["frozen_at"]).date().isoformat() == T
    rows, failures = [], {}
    with ThreadPoolExecutor(max_workers=min(workers, 8)) as pool:
        jobs = {pool.submit(observe, code, provider): code for code in codes}
        for future in as_completed(jobs):
            code = jobs[future]
            try:
                record = future.result()
                record["groups"] = ([name for name, ok in (
                    ("frozen_broad_120", code in broad),
                    ("frozen_deep_28", code in deep),
                    ("preexisting_low_position_52", code in low),
                    ("T30_frozen_shadow_3", code in shadow)) if ok])
                original = broad.get(code, {})
                anchor = float(original["trade"]) if original.get("trade") else None
                record["T30_frozen_quote_close"] = anchor
                record["anchor_match_within_0_03"] = (
                    abs(record["prev"]["close"] - anchor) <= 0.03 if anchor is not None else None)
                rows.append(record)
            except Exception as exc:
                failures[code] = type(exc).__name__ + ": " + str(exc)[:110]
    rows.sort(key=lambda x: x["code"])
    def summarize(name, subset):
        eligible = [x for x in subset if x["anchor_match_within_0_03"] is not False]
        closes = [x["close_pct"] for x in eligible]
        return {"group": name, "verified_daily_n": len(subset), "anchor_consistent_n": len(eligible),
                "mean_close_pct": round(mean(closes), 4) if closes else None,
                "median_close_pct": round(median(closes), 4) if closes else None,
                "mean_high_excursion_pct": round(mean(x["daily_high_excursion_pct"] for x in eligible), 4) if eligible else None,
                "mean_low_excursion_pct": round(mean(x["daily_low_excursion_pct"] for x in eligible), 4) if eligible else None,
                "close_up_n": sum(x["close_pct"] > 0 for x in eligible),
                "close_down_n": sum(x["close_pct"] < 0 for x in eligible),
                "proxy_only_not_executable_return": True}
    report = {"schema_version": 1, "target_session": D, "frozen_session": T,
              "frozen_at": shadow_doc["frozen_at"],
              "retrieved_at": datetime.now(CN).isoformat(timespec="seconds"),
              "research_scope": "retrospective_daybar_observations_for_pre_frozen_T30_universe_only",
              "source_provider": "tencent_unadjusted_daybars_adjust_0",
              "source_url": "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
              "expected": {"broad": len(broad), "deep": len(deep), "low": len(low), "shadow": len(shadow),
                           "unique": len(codes)},
              "success": len(rows), "failure": len(failures), "errors": failures,
              "summary": [
                  summarize("broad", [x for x in rows if "frozen_broad_120" in x["groups"]]),
                  summarize("deep", [x for x in rows if "frozen_deep_28" in x["groups"]]),
                  summarize("low", [x for x in rows if "preexisting_low_position_52" in x["groups"]]),
                  summarize("shadow", [x for x in rows if "T30_frozen_shadow_3" in x["groups"]]),
              ],
              "observations": rows,
              "analysis_completed": False,
              "original_T11_02_research_completed": False,
              "eligible_for_integrated_research": False,
              "backfill_is_forward_signal": False,
              "verified_buy_fills": 0,
              "intraday_entry_trigger_verified": False,
              "missing": ["all_A_share_universe_for_T20261102", "dated_exchange_seat_full_list",
                          "2026-11-02_full_minute_OHLC", "real_0925_auction",
                          "original_frozen_time_on_T20261102", "verified_order_fills"],
              "note": "These prices existed on 11/02, but were recovered on 11/03. Do not claim publication on 11/02, full original research, or tradable P&L."}
    DEST.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    r = collect()
    print(json.dumps({"retrieved_at": r["retrieved_at"], "expected": r["expected"],
                      "success": r["success"], "failure": r["failure"],
                      "summary": r["summary"], "errors": r["errors"]},
                     ensure_ascii=False))
    # Below 60% would be too weak to interpret the frozen-pool distribution.
    return 0 if r["success"] >= max(30, int(r["expected"]["unique"] * 0.6)) else 2


if __name__ == "__main__":
    raise SystemExit(main())
