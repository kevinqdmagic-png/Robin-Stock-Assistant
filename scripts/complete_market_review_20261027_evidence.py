#!/usr/bin/env python3
"""Complete the 2026-10-27 evidence with prior-pool forward validation."""

from __future__ import annotations

import concurrent.futures
import json
import statistics
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
T = "2026-10-27"
BASE = ROOT / "docs/research/market-review-2026-10-27-evidence-base.json"
OUT = ROOT / "docs/research/market-review-2026-10-27-evidence.json"
PRIOR = ROOT / "docs/research/market-review-2026-10-26-evidence.json"
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
        "origin_date": "2026-10-26", "validation_date": T,
        "origin_close": base, "open": o, "high": h, "low": l, "close": c,
        "open_pct": pct(o, base), "mfe_pct": pct(h, base),
        "mae_pct": pct(l, base), "close_pct": pct(c, base),
        "minute_sequence_available": False,
        "execution_status": "price_observation_only_no_frozen_entry_trigger",
    }


def main():
    evidence = json.loads(BASE.read_text(encoding="utf-8"))
    prior = json.loads(PRIOR.read_text(encoding="utf-8"))["deep_pool"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        checked = list(pool.map(validate, prior))
    checked.sort(key=lambda x: x["code"])
    closes = [x["close_pct"] for x in checked]
    mfes = [x["mfe_pct"] for x in checked]
    maes = [x["mae_pct"] for x in checked]
    evidence["previous_pool_validation"] = checked
    evidence["previous_pool_statistics"] = {
        "origin_report_id": "market-review-20261026-close-v1",
        "sample_count": len(checked),
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
        "retrieved_at_cn": "2026-10-27T16:14:45+08:00",
        "items": [
            {"name": "上证指数", "close": 3648.30, "change_pct": -1.33, "high": 3708.20, "low": 3648.30},
            {"name": "深证成指", "close": 11245.73, "change_pct": -2.50, "high": 11633.30, "low": 11245.72},
            {"name": "创业板指", "close": 2548.15, "change_pct": -3.41, "high": 2670.47, "low": 2548.11},
            {"name": "科创50", "close": 1252.28, "change_pct": -4.81, "high": 1327.33, "low": 1249.76},
        ],
    }
    evidence["media_cross_check"] = {
        "cls_midday": {
            "limit_up": 46, "connected_boards": 13, "failed_boards": 13,
            "seal_rate_pct": 78, "highest_board": "上海九百5板",
            "source": "https://www.cls.cn/detail/2516200",
            "scope_note": "11:48午间快照，不冒充收盘统计。",
        },
        "close_ladder": {
            "connected_boards": 13, "highest_board": "上海九百5板",
            "four_boards": ["襄阳轴承", "赛福天", "多伦科技"],
            "source": "https://stockinsky.com/limit-ladder",
        },
        "scope_note": "媒体口径与本档普通非ST主板代理口径分别保存，不混算。",
    }
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(OUT.relative_to(ROOT)), "previous": evidence["previous_pool_statistics"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
