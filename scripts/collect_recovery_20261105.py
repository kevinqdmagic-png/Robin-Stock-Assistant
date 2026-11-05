#!/usr/bin/env python3
"""Collect reproducible, date-exact daily/5m evidence for the manual recovery.

This collector never creates signals, trades or retrospectively frozen samples.
Sina bars are checked against the independently archived BaoStock daily bars.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-11-05"
OUT = ROOT / "docs/research/recovery-20261105-bars.json"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch(code, scale):
    symbol = ("sh" if code.startswith("6") else "sz") + code
    url = ("https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_recovery=/"
           f"CN_MarketDataService.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen=150" )
    if scale == 5:
        url = url.replace("datalen=150", "datalen=240")
    proc = subprocess.run(["curl", "-fsSL", "--max-time", "14", "-A", "Mozilla/5.0",
                           "-H", "Referer: https://finance.sina.com.cn/", url],
                          capture_output=True, text=True, timeout=17)
    if proc.returncode:
        raise ValueError(f"curl_exit_{proc.returncode}:{proc.stderr[:100]}")
    match = re.search(r"=\((\[.*\])\)\s*;?\s*$", proc.stdout, re.S)
    if not match:
        raise ValueError("invalid_sina_jsonp")
    raw = json.loads(match.group(1))
    bars = []
    seen = set()
    for row in raw:
        stamp = row["day"]
        if stamp[:10] > DAY or (scale == 5 and stamp[:10] != DAY):
            continue
        if stamp in seen:
            raise ValueError("duplicate_timestamp")
        seen.add(stamp)
        item = {k: float(row[k]) for k in ("open", "high", "low", "close", "volume")}
        if "amount" in row:
            item["amount"] = float(row["amount"])
        if not all(math.isfinite(v) for v in item.values()):
            raise ValueError("nonfinite_bar")
        if not 0 < item["low"] <= min(item["open"], item["close"]) <= max(item["open"], item["close"]) <= item["high"]:
            raise ValueError("invalid_ohlc")
        if item["volume"] < 0 or item.get("amount", 0) < 0:
            raise ValueError("negative_volume_amount")
        bars.append({"date": stamp[:10], "time": stamp, **item})
    bars.sort(key=lambda x: x["time"])
    if not bars or bars[-1]["date"] != DAY:
        raise ValueError("no_exact_day_bars")
    if scale == 240 and len(bars) < 121:
        raise ValueError("insufficient_daily_history_121")
    return {"code": code, "scale": scale, "provider": "Sina public K-line",
            "url": url, "retrieved_at": now(), "response_sha256": hashlib.sha256(proc.stdout.encode()).hexdigest(),
            "adjustment": "none", "volume_unit": "shares", "bars": bars}


def validate_minutes(item, daily):
    bars = item["bars"]
    expected = [f"{DAY} {m//60:02d}:{m%60:02d}:00" for start, end in
                ((575, 690), (785, 900)) for m in range(start, end+1, 5)]
    canonical = [b["time"] for b in bars] == expected
    agg = {"open": bars[0]["open"], "close": bars[-1]["close"],
           "high": max(b["high"] for b in bars), "low": min(b["low"] for b in bars),
           "volume": sum(b["volume"] for b in bars),
           "amount": sum(b.get("amount", 0) for b in bars)}
    differences = {k: abs(agg[k] - float(daily[k])) for k in ("open", "close", "high", "low")}
    vol_error = abs(agg["volume"] / daily["volume"] - 1) if daily["volume"] else None
    amount_error = abs(agg["amount"] / daily["amount"] - 1) if daily["amount"] else None
    return {"count": len(bars), "canonical_48": canonical, "aggregated": agg,
            "ohlc_abs_difference": differences, "volume_relative_error": vol_error,
            "amount_relative_error": amount_error,
            "verified": canonical and max(differences.values()) <= .011 and
            vol_error is not None and vol_error <= .01 and amount_error is not None and amount_error <= .01}


def main():
    started = now()
    ev = json.loads((ROOT / "docs/research/volume-price-20261105-evidence.json").read_text())
    snap = json.loads((ROOT / "backend/data/baostock/2026-11-05.json").read_text())
    daily = {r["code"].split(".")[-1]: r for r in snap["rows"]}
    broad = [r["code"] for r in ev["broad_pool"]]
    event_codes = ["002578","603381","301697","002529","002309","603212","002506","002487",
                   "002081","600641","600206","002409","002156","603657","003033","603955",
                   "000700","300709","000017","605339","000995","605188","002329","000603",
                   "600988","000426","002192","002240"]
    lhb_watch = ["002131","002565","002164","300709","300071","600261","002343","300049",
                 "688316","002088","688109","002708","000603","600857"]
    codes = sorted(set(broad + event_codes + lhb_watch) & set(daily))
    minute_codes = sorted(set([r["code"] for r in ev["deep_pool"]] + event_codes + lhb_watch) & set(daily))
    requests = [(c, 240) for c in codes] + [(c, 5) for c in minute_codes]
    results, errors = {"daily": {}, "five_minute": {}}, {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = {pool.submit(fetch, c, scale): (c, scale) for c, scale in requests}
        for future in as_completed(jobs):
            code, scale = jobs[future]
            try:
                item = future.result()
                if scale == 5:
                    item["validation"] = validate_minutes(item, daily[code])
                else:
                    item["daily_close_crosscheck_abs"] = abs(item["bars"][-1]["close"] - daily[code]["close"])
                results["five_minute" if scale == 5 else "daily"][code] = item
            except Exception as exc:
                errors[f"{code}:{scale}"] = str(exc)[:200]
    output = {"market_date": DAY, "manual_recovery": True, "started_at": started,
              "completed_at": now(), "daily_requested": codes, "minute_requested": minute_codes,
              **results, "errors": errors, "not_original_intraday_signal": True,
              "not_fill_evidence": True, "benchmark": "backend/data/baostock/2026-11-05.json"}
    OUT.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"daily": len(results["daily"]), "minute": len(results["five_minute"]),
                      "minute_verified": sum(r["validation"]["verified"] for r in results["five_minute"].values()),
                      "errors": errors, "completed_at": output["completed_at"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
