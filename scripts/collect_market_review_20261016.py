#!/usr/bin/env python3
"""Collect reproducible 2026-10-16 market-review evidence from public endpoints."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path


MARKET_DATE = "2026-10-16"
SINA = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "Market_Center.getHQNodeData?page={page}&num=100&sort=symbol&asc=1&"
    "node=hs_a&symbol=&_s_r_a=page"
)
TENCENT_K = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,120,qfq"
TENCENT_M = "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={symbol}"


def get_json(url: str, timeout: int = 45):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return json.load(fh)


def page(n: int):
    try:
        return get_json(SINA.format(page=n))
    except Exception as exc:
        return {"error": repr(exc), "page": n}


def f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def enrich_bar(row: dict):
    out = dict(row)
    high, low, close = f(row.get("high")), f(row.get("low")), f(row.get("trade"))
    out["clv"] = None if high == low else (close - low) / (high - low)
    out["score"] = (
        f(row.get("changepercent")) * 2.1
        + min(f(row.get("turnoverratio")), 25) * 0.55
        + math.log10(max(f(row.get("amount")), 1)) * 1.8
        + (out["clv"] or 0) * 8
    )
    return out


def fetch_kline(row: dict):
    out = dict(row)
    symbol = row["symbol"]
    try:
        payload = get_json(TENCENT_K.format(symbol=symbol))
        block = payload["data"][symbol]
        bars = block.get("qfqday") or block.get("day") or []
        parsed = [
            {"date": b[0], "open": f(b[1]), "close": f(b[2]), "high": f(b[3]), "low": f(b[4]), "volume": f(b[5])}
            for b in bars
        ]
        current = next((b for b in reversed(parsed) if b["date"] == MARKET_DATE), None)
        prior = [b for b in parsed if b["date"] < MARKET_DATE]
        if current:
            vol = current["volume"]
            out["bar_date"] = current["date"]
            out["vol"] = vol
            for n in (5, 10, 20):
                seq = prior[-n:]
                out[f"rvol{n}"] = vol / (sum(x["volume"] for x in seq) / len(seq)) if seq else None
            for n in (20, 60, 120):
                seq = prior[-n:]
                out[f"ma{n}"] = sum(x["close"] for x in seq) / len(seq) if seq else None
                out[f"high{n}"] = max((x["high"] for x in seq), default=None)
                out[f"low{n}"] = min((x["low"] for x in seq), default=None)
            ma20 = out.get("ma20")
            out["dist_ma20"] = ((f(row["trade"]) / ma20) - 1) * 100 if ma20 else None
            out["tech_score"] = out["score"] + min(out.get("rvol20") or 0, 5) * 4
        else:
            out["kline_error"] = "market-date bar absent"
    except Exception as exc:
        out["kline_error"] = repr(exc)
    return out


def fetch_minute(row: dict):
    out = dict(row)
    try:
        payload = get_json(TENCENT_M.format(symbol=row["symbol"]))
        raw = payload["data"][row["symbol"]]["data"]["data"]
        points = []
        for line in raw:
            p = line.split()
            points.append((p[0], f(p[1]), f(p[2]), f(p[3])))
        wanted = {}
        for mark in ("0930", "0945", "1030", "1130", "1400", "1430", "1500"):
            eligible = [x for x in points if x[0] <= mark]
            wanted[mark] = eligible[-1][1] if eligible else None
        p1400 = wanted.get("1400")
        close = f(row["trade"])
        out["tail_1400_close_pct"] = (close / p1400 - 1) * 100 if p1400 else None
        total_vol = points[-1][2] if points else 0
        before = max((x[2] for x in points if x[0] <= "1400"), default=0)
        out["tail_volume_share"] = (total_vol - before) / total_vol if total_vol else None
        out["price_points"] = wanted
    except Exception as exc:
        out["minute_error"] = repr(exc)
    return out


def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=28) as pool:
        pages = list(pool.map(page, range(1, 61)))
    errors = [x for x in pages if isinstance(x, dict)]
    rows = [r for chunk in pages if isinstance(chunk, list) for r in chunk]
    unique = {r["symbol"]: r for r in rows}
    valid = [enrich_bar(r) for r in unique.values() if f(r.get("trade")) > 0 and f(r.get("settlement")) > 0]
    valid.sort(key=lambda x: x["symbol"])

    ranked = sorted(valid, key=lambda x: x["score"], reverse=True)
    prepool = [x for x in ranked if f(x.get("amount")) >= 80_000_000 and f(x.get("turnoverratio")) >= 1.0]
    broad_base = prepool[:160]
    with concurrent.futures.ThreadPoolExecutor(max_workers=28) as pool:
        enriched = list(pool.map(fetch_kline, broad_base))
    enriched.sort(key=lambda x: x.get("tech_score", x["score"]), reverse=True)
    broad = enriched[:120]

    # Diversified deep review: retain liquid positive structures plus selected pullbacks.
    positive = [x for x in broad if -1.5 <= f(x.get("changepercent")) <= 11.5 and (x.get("clv") or 0) >= 0.45]
    deep = positive[:28]
    if len(deep) < 28:
        used = {x["symbol"] for x in deep}
        deep.extend(x for x in broad if x["symbol"] not in used)
        deep = deep[:28]
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        deep = list(pool.map(fetch_minute, deep))

    main_board = [
        x for x in valid
        if "ST" not in x["name"].upper()
        and (x["symbol"].startswith("sh60") or x["symbol"].startswith(("sz000", "sz001", "sz002", "sz003")))
    ]
    sealed = [x for x in main_board if f(x.get("changepercent")) >= 9.5]
    touched = [x for x in main_board if f(x["high"]) / f(x["settlement"]) >= 1.095]
    failed = [x for x in touched if x not in sealed]
    down = [x for x in main_board if f(x.get("changepercent")) <= -9.5]
    market = {
        "advance": sum(f(x.get("changepercent")) > 0 for x in valid),
        "decline": sum(f(x.get("changepercent")) < 0 for x in valid),
        "flat": sum(f(x.get("changepercent")) == 0 for x in valid),
        "amount_yuan_full_scan": sum(f(x.get("amount")) for x in valid),
        "standard_non_st_limit_up_sealed": len(sealed),
        "standard_non_st_limit_up_touched": len(touched),
        "standard_non_st_failed_boards": len(failed),
        "standard_non_st_limit_down": len(down),
        "top_gainers": [{k: x.get(k) for k in ("code", "name", "changepercent", "amount", "turnoverratio")} for x in sorted(valid, key=lambda x: f(x.get("changepercent")), reverse=True)[:30]],
        "top_decliners": [{k: x.get(k) for k in ("code", "name", "changepercent", "amount", "turnoverratio")} for x in sorted(valid, key=lambda x: f(x.get("changepercent")))[:30]],
    }
    evidence = {
        "market_date": MARKET_DATE,
        "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "coverage": {"full_scan": len(valid), "raw_records": len(unique), "page_errors": errors, "broad_pool": len(broad), "deep_pool": len(deep)},
        "market": market,
        "broad_pool": broad,
        "deep_pool": deep,
        "sources": [SINA.format(page=1), TENCENT_K.format(symbol="CODE"), TENCENT_M.format(symbol="CODE")],
    }
    path = Path("docs/research/market-review-2026-10-16-evidence-base.json")
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"path": str(path), "coverage": evidence["coverage"], "market": {k: v for k, v in market.items() if not k.startswith("top_")}, "deep": [(x["code"], x["name"], x["changepercent"], x.get("rvol20"), x.get("tail_1400_close_pct")) for x in deep]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
