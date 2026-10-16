#!/usr/bin/env python3
"""Append 2026-10-16 validations to the market-review evidence file."""

import json
import subprocess
from pathlib import Path


def symbol(code):
    return ("sh" if code.startswith(("5", "6", "9")) else "sz") + code


def quote_map(codes):
    syms = [symbol(c) for c in codes]
    raw = subprocess.check_output(
        ["curl", "-fsS", "--max-time", "40", "https://qt.gtimg.cn/q=" + ",".join(syms)]
    ).decode("gbk", "replace")
    out = {}
    for line in raw.splitlines():
        if '="' not in line:
            continue
        vals = line.split('="', 1)[1].rstrip('";').split("~")
        if len(vals) < 35:
            continue
        out[vals[2]] = {
            "name": vals[1], "close": float(vals[3]), "previous_close": float(vals[4]),
            "open": float(vals[5]), "high": float(vals[33]), "low": float(vals[34]),
            "quote_time": vals[30],
        }
    return out


def main():
    prior = json.load(open("docs/research/market-review-2026-10-15-evidence.json"))
    current_path = Path("docs/research/market-review-2026-10-16-evidence-base.json")
    current = json.load(open(current_path))
    deep = prior["deep_pool"]
    q = quote_map([x["code"] for x in deep] + ["000973", "002812", "600316"])
    validations = []
    for x in deep:
        z = q[x["code"]]
        ref = float(x["trade"])
        validations.append({
            "code": x["code"], "name": x["name"], "reference_close": ref,
            "open": z["open"], "high": z["high"], "low": z["low"], "close": z["close"],
            "open_pct": (z["open"] / ref - 1) * 100,
            "mfe_pct": (z["high"] / ref - 1) * 100,
            "mae_pct": (z["low"] / ref - 1) * 100,
            "close_pct": (z["close"] / ref - 1) * 100,
            "status": "daily_price_observation_only",
        })
    current["coverage"]["previous_pool_verified"] = len(validations)
    current["previous_pool_validation"] = validations
    current["previous_formal_conditions"] = {
        "000973": {
            "result": "not_triggered", "open": q["000973"]["open"], "high": q["000973"]["high"],
            "low": q["000973"]["low"], "close": q["000973"]["close"],
            "minute_evidence": "09:45 reached 11.80 support but session high 12.05; required 12.20 reclaim never occurred; no fill inferred",
        },
        "002812": {
            "result": "not_triggered_and_invalidated", "open": q["002812"]["open"], "high": q["002812"]["high"],
            "low": q["002812"]["low"], "close": q["002812"]["close"],
            "minute_evidence": "open 48.99; pullback reached 47.88 at 09:31 then never reclaimed 48.60; later fell below 46.35 invalidation; no fill inferred",
        },
        "600316": {
            "result": "prior_trigger_T_plus_1_exit_levels_observed", "open": q["600316"]["open"], "high": q["600316"]["high"],
            "low": q["600316"]["low"], "close": q["600316"]["close"],
            "minute_evidence": "first minute point >=36.20 at 09:41 (36.24); first >=37.50 at 09:51 (37.50). Frozen plan did not specify split weights, so no executable net return is invented.",
        },
    }
    current["sources"].extend([
        "https://qt.gtimg.cn/q=sz000973,sz002812,sh600316",
        "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=sz000973",
        "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=sz002812",
        "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=sh600316",
    ])
    final = Path("docs/research/market-review-2026-10-16-evidence.json")
    final.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n")
    vals = validations
    print(json.dumps({
        "path": str(final), "n": len(vals),
        "positive_close": sum(x["close_pct"] > 0 for x in vals),
        "avg_close": sum(x["close_pct"] for x in vals) / len(vals),
        "median_close": sorted(x["close_pct"] for x in vals)[len(vals)//2-1:len(vals)//2+1],
        "avg_mfe": sum(x["mfe_pct"] for x in vals) / len(vals),
        "avg_mae": sum(x["mae_pct"] for x in vals) / len(vals),
        "mae_le_minus5": sum(x["mae_pct"] <= -5 for x in vals),
        "formal": current["previous_formal_conditions"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
