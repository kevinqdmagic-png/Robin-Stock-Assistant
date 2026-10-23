#!/usr/bin/env python3
"""Collect append-only evidence for the 2026-10-23 volume/price study."""

from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
T = "2026-10-23"


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def symbol(code):
    return ("sh" if code.startswith(("5", "6", "9")) else "sz") + code


def fetch_daily(code):
    sym = symbol(code)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param={sym},day,,,180"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))
    block = payload["data"][sym]
    raw = block.get("day") or block.get("qfqday")
    rows = []
    for row in raw:
        if row[0] > T:
            continue
        rows.append({"date": row[0], "open": float(row[1]), "close": float(row[2]),
                     "high": float(row[3]), "low": float(row[4]), "volume": float(row[5])})
    if not rows or rows[-1]["date"] != T:
        raise RuntimeError(f"missing {T} bar for {code}")
    return url, rows


def pct(value, base):
    return round((value / base - 1) * 100, 3)


def main():
    market = load("docs/research/low-dragon-2026-10-23-market-scan.json")
    ledger = load("backend/data/volume_price_samples.json")
    cohort = next(x for x in ledger["items"] if x.get("id") == "volume-price-20261022-close-v1-cohort")
    prior = []
    errors = {}
    for sample in cohort["samples"]:
        code = sample["code"]
        try:
            url, bars = fetch_daily(code)
            current = bars[-1]
            base = float(sample["trade"])
            prior.append({
                "code": code, "name": sample["name"], "origin_cohort_id": cohort["id"],
                "status": "verified_closed_daily", "prior_close": base, **current,
                "open_pct": pct(current["open"], base), "mfe_pct": pct(current["high"], base),
                "mae_pct": pct(current["low"], base), "close_pct": pct(current["close"], base),
                "source": url, "executed_trade": False, "executable_net_return_pct": None,
                "missing": ["auction", "full_minute_OHLC", "trigger_order", "verified_fill", "legal_exit"],
            })
        except Exception as exc:
            errors[code] = f"{type(exc).__name__}: {exc}"
    if errors or len(prior) != len(cohort["samples"]):
        raise RuntimeError(json.dumps({"errors": errors, "verified": len(prior)}, ensure_ascii=False))

    values = [x["close_pct"] for x in prior]
    stats = {
        "count": len(prior), "positive_close_count": sum(x > 0 for x in values),
        "mean_close_pct": round(statistics.mean(values), 3),
        "median_close_pct": round(statistics.median(values), 3),
        "mean_mfe_pct": round(statistics.mean(x["mfe_pct"] for x in prior), 3),
        "mean_mae_pct": round(statistics.mean(x["mae_pct"] for x in prior), 3),
        "mae_le_minus5_count": sum(x["mae_pct"] <= -5 for x in prior),
    }
    now = datetime.now(timezone.utc)
    evidence = {
        "market_date": T,
        "retrieved_at_utc": now.isoformat(timespec="seconds"),
        "recorded_at": now.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "market_source_file": "docs/research/low-dragon-2026-10-23-market-scan.json",
        "coverage": market["coverage"], "market": market["market"],
        "broad_pool": market["broad_pool"], "deep_pool": market["deep_pool"],
        "previous_cohort_id": cohort["id"], "previous_pool_validation": prior,
        "previous_pool_statistics": stats,
        "method": {
            "rule_version": "volume_price_close_v4",
            "observation_return": "T close/open/high/low relative to frozen T-1 close",
            "mfe_mae_warning": "daily extrema are price observations; without minute order and fill they are not executable trade returns",
            "relative_volume": "current completed daily volume divided by mean of prior completed 5/10/20 sessions",
            "clv": "(close-low)/(high-low); N/A when high equals low",
        },
        "limitations": [
            "No complete 09:25 auction record or full one-minute OHLC for the full prior cohort.",
            "Snapshot price points cannot prove intraday trigger order or an executable fill.",
            "No Level-2/order-book data and no inference of trader identity.",
            "No calibrated strategy probability; no automatic rule or weight change.",
        ],
        "sources": market["sources"] + sorted({x["source"] for x in prior}),
    }
    out = ROOT / "docs/research/volume-price-20261023-close-evidence.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), "previous": stats, "deep": len(market["deep_pool"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
