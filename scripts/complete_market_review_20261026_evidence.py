#!/usr/bin/env python3
"""Complete the 2026-10-26 market-review evidence with T+1 validation."""

from __future__ import annotations

import concurrent.futures
import json
import statistics
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
T = "2026-10-26"
BASE = ROOT / "docs/research/market-review-2026-10-26-evidence-base.json"
OUT = ROOT / "docs/research/market-review-2026-10-26-evidence.json"
KLINE = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param={symbol},day,,,30"


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as fh:
        return json.load(fh)


def pct(value: float, base: float):
    return round((value / base - 1) * 100, 3)


def validate(sample: dict):
    symbol = sample["symbol"]
    payload = get_json(KLINE.format(symbol=symbol))
    block = payload["data"][symbol]
    rows = block.get("day") or block.get("qfqday") or []
    row = next(x for x in rows if x[0] == T)
    o, c, h, l = map(float, row[1:5])
    base = float(sample["trade"])
    return {
        "code": sample["code"], "name": sample["name"],
        "origin_date": "2026-10-23", "validation_date": T,
        "origin_close": base, "open": o, "high": h, "low": l, "close": c,
        "open_pct": pct(o, base), "mfe_pct": pct(h, base),
        "mae_pct": pct(l, base), "close_pct": pct(c, base),
        "minute_sequence_available": False,
        "execution_status": "price_observation_only_no_frozen_entry_trigger",
    }


def main():
    evidence = json.loads(BASE.read_text())
    ledger = json.loads((ROOT / "backend/data/volume_price_samples.json").read_text())
    cohort = next(x for x in ledger["items"] if x.get("id") == "volume-price-20261023-close-v1-cohort")
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        previous = list(pool.map(validate, cohort["samples"]))
    previous.sort(key=lambda x: x["code"])
    closes = [x["close_pct"] for x in previous]
    mfes = [x["mfe_pct"] for x in previous]
    maes = [x["mae_pct"] for x in previous]
    evidence["previous_pool_validation"] = previous
    evidence["previous_pool_statistics"] = {
        "origin_cohort_id": cohort["id"], "sample_count": len(previous),
        "positive_close_count": sum(x > 0 for x in closes),
        "mean_close_pct": round(statistics.fmean(closes), 3),
        "median_close_pct": round(statistics.median(closes), 3),
        "mean_mfe_pct": round(statistics.fmean(mfes), 3),
        "mean_mae_pct": round(statistics.fmean(maes), 3),
        "mae_le_minus5_count": sum(x <= -5 for x in maes),
        "executed_trade_count": 0,
        "note": "All 28 daily bars verified; no minute trigger sequence or executable return inferred.",
    }
    evidence["index_quotes"] = {
        "source": "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688",
        "items": [
            {"name": "上证指数", "close": 3697.52, "change_pct": 0.19, "high": 3699.01, "low": 3664.82},
            {"name": "深证成指", "close": 11534.38, "change_pct": -1.19, "high": 11638.79, "low": 11432.29},
            {"name": "创业板指", "close": 2638.23, "change_pct": -1.71, "high": 2671.81, "low": 2601.09},
            {"name": "科创50", "close": 1315.50, "change_pct": -2.23, "high": 1335.92, "low": 1305.61},
        ],
    }
    evidence["media_cross_check"] = {
        "eastmoney": {"turnover_yi": 16100, "decrease_yi": 3475, "decliners_over": 3100},
        "cls": {"limit_up": 55, "connected_boards": 15, "three_plus_boards": 7,
                "prior_connected_boards": 12, "advancement_pct": 58.33,
                "limit_down_over": 20, "highest_board": "上海九百4板"},
        "scope_note": "媒体全市场口径与本档普通非ST主板代理口径分别保存，不混算。",
    }
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"path": str(OUT.relative_to(ROOT)), "previous": evidence["previous_pool_statistics"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
