#!/usr/bin/env python3
"""Complete 2026-10-29 market evidence with prior-pool validation and indices."""

from __future__ import annotations

import concurrent.futures
import json
import statistics
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
T = "2026-10-29"
BASE = ROOT / "docs/research/market-review-2026-10-29-evidence-base.json"
OUT = ROOT / "docs/research/market-review-2026-10-29-evidence.json"
PRIOR = ROOT / "docs/research/market-review-2026-10-28-evidence.json"
KLINE = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param={symbol},day,,,30"
INDEX_URL = "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688"


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
        "origin_date": "2026-10-28", "validation_date": T,
        "origin_close": base, "open": o, "high": h, "low": l, "close": c,
        "open_pct": pct(o, base), "mfe_pct": pct(h, base),
        "mae_pct": pct(l, base), "close_pct": pct(c, base),
        "minute_sequence_available": False,
        "execution_status": "price_observation_only_no_frozen_entry_trigger",
        "source": KLINE.format(symbol=symbol),
    }


def fetch_indices():
    req = urllib.request.Request(INDEX_URL, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=40).read().decode("gbk")
    items = []
    for line in raw.strip().splitlines():
        fields = line.split('="', 1)[1].rsplit('"', 1)[0].split("~")
        items.append({
            "name": fields[1], "close": float(fields[3]),
            "change_pct": float(fields[32]), "high": float(fields[33]),
            "low": float(fields[34]), "quote_time": fields[30],
        })
    return items


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
        "origin_report_id": "market-review-20261028-close-v1",
        "sample_count": len(checked),
        "positive_close_count": sum(x > 0 for x in closes),
        "mean_close_pct": round(statistics.fmean(closes), 3),
        "median_close_pct": round(statistics.median(closes), 3),
        "mean_mfe_pct": round(statistics.fmean(mfes), 3),
        "mean_mae_pct": round(statistics.fmean(maes), 3),
        "mae_le_minus5_count": sum(x <= -5 for x in maes),
        "executed_trade_count": 0,
        "note": "All prior daily bars verified; no minute trigger sequence or executable return inferred.",
    }
    evidence["index_quotes"] = {
        "source": INDEX_URL,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "items": fetch_indices(),
    }
    evidence["media_cross_check"] = {
        "close_board_snapshot": {
            "limit_up": 40, "failed_boards": 23, "seal_rate_pct": 63,
            "highest_board": "青岛食品、光洋股份4板",
            "first_to_second": "7/57", "second_to_third": "3/5", "high_level": "2/3",
            "source": "https://www.kanpanba.com/limit",
        },
        "market_close_snapshot": {
            "turnover_cny": 1_570_000_000_000,
            "turnover_change_cny": -71_300_000_000,
            "strong_sectors": ["航天装备", "核电", "风电", "银行"],
            "weak_sectors": ["元件", "半导体", "通信设备", "机器人", "消费电子"],
            "source": "https://fund.eastmoney.com/a/202610293913948829.html",
        },
        "scope_note": "媒体全市场口径与本档普通非ST主板代理口径分别保存，不混算。",
    }
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(OUT.relative_to(ROOT)), "previous": evidence["previous_pool_statistics"], "indices": evidence["index_quotes"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
