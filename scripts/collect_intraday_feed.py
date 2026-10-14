#!/usr/bin/env python3
"""Fetch a timestamped partial A-share candidate universe; no simulated prices.

Universe consists of versioned app research/watch stocks + recent historical
recommendation codes, optionally supplemented by Sina turnover leaders.
Independent Tencent spot quotes are required to validate every observed row.
A partial universe is NEVER advertised as a whole-market scan.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from quote_providers import stock_symbol
import requests

CN = ZoneInfo("Asia/Shanghai")
SOURCE = "https://qt.gtimg.cn/q="
SINA = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"


def local_universe(root=ROOT):
    codes = []
    for filename in ("research_stocks.json", "recommendations.json"):
        try:
            data = json.loads((root / "backend" / "data" / filename).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for item in data.get("items", []):
            code = str(item.get("code", ""))
            if re.fullmatch(r"[0-9]{6}", code) and code not in codes:
                codes.append(code)
    return codes


def sina_leaders(client=requests, limit=80):
    # Discovery only: quoted securities must subsequently pass Tencent evidence.
    params = {"page": 1, "num": limit, "sort": "amount", "asc": 0, "node": "hs_a"}
    response = client.get(SINA, params=params, headers={
        "User-Agent": "Mozilla/5.0", "Referer": "https://vip.stock.finance.sina.com.cn/"
    }, timeout=(4, 7))
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        raise ValueError("sina_leaders_wrong_schema")
    return list(dict.fromkeys(str(item.get("code") or str(item.get("symbol", ""))[-6:])
                              for item in rows if isinstance(item, dict)
                              and re.fullmatch(r"[0-9]{6}", str(item.get("code") or str(item.get("symbol", ""))[-6:]))))


def parse_tencent(raw, symbols):
    rows = []
    valid = set(symbols)
    for match in re.finditer(r'v_((?:sh|sz|bj)\d{6})="([^"]*)"', raw):
        symbol, payload = match.groups()
        if symbol not in valid:
            continue
        f = payload.split("~")
        if len(f) <= 38 or f[2] != symbol[-6:]:
            continue
        if not f[1].strip() or any(label in f[1].upper() for label in ("ST", "退")):
            continue
        try:
            ts = datetime.strptime(f[30], "%Y%m%d%H%M%S").replace(tzinfo=CN)
            price = float(f[3]); prev = float(f[4]); volume = float(f[6])
            amount = float(f[37]) * 10000  # Tencent amount in ten-thousand CNY.
            turnover = float(f[38])
            if not (0 < price < 100000 and 0 < prev < 100000 and volume > 0
                    and amount > 0 and 0 <= turnover <= 100):
                continue
            pct = (price / prev - 1) * 100
            # Reject incompatible quote fields and halted/zero-volume rows.
            if abs(float(f[32]) - pct) > 0.4:
                continue
            vr = None
            if len(f) > 49:
                try:
                    vr = float(f[49])
                    if not 0 <= vr <= 1000:
                        vr = None
                except ValueError:
                    pass
        except (ValueError, IndexError, OverflowError):
            continue
        rows.append({
            "code": f[2], "name": f[1], "market": symbol[:2].upper(),
            "price": round(price, 3), "previous_close": round(prev, 3),
            "volume": volume, "turnover": amount, "turnover_ratio": round(turnover, 2),
            "pct": round(pct, 2), "volume_ratio": vr,
            "as_of": ts.isoformat(timespec="seconds"),
            "source": SOURCE + symbol,
        })
    return rows


def gather(now=None, client=requests, root=ROOT):
    now = (now or datetime.now(CN)).astimezone(CN)
    errors = []
    codes = local_universe(root)
    local_count = len(codes)
    try:
        leaders = sina_leaders(client)
        codes.extend(code for code in leaders if code not in codes)
    except (requests.RequestException, ValueError, TypeError) as exc:
        errors.append("sina_discovery:" + type(exc).__name__)
    codes = codes[:140]
    symbols = [stock_symbol(code) for code in codes]
    rows = []
    for i in range(0, len(symbols), 60):
        batch = symbols[i:i+60]
        try:
            response = client.get(SOURCE + ",".join(batch), headers={
                "User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"
            }, timeout=(4, 7))
            response.raise_for_status()
            response.encoding = "gb18030"
            rows.extend(parse_tencent(response.text, batch))
        except (requests.RequestException, ValueError) as exc:
            errors.append("tencent_batch:" + type(exc).__name__)
    # Every row is independently time-checked, not just the freshest quote.
    fresh = []
    for row in rows:
        asof = datetime.fromisoformat(row["as_of"])
        age = (now - asof).total_seconds()
        if asof.date() == now.date() and 0 <= age <= 300:
            fresh.append(row)
    # No optimistic use of a partially stale basket.
    unique = {row["code"]: row for row in fresh}
    filtered = list(unique.values())
    return {
        "source": SOURCE + ",".join(symbols[:60]), "as_of": max(
            (r["as_of"] for r in filtered), default=now.isoformat(timespec="seconds")),
        "quotes": filtered,
        "scope": "research_watchlist_plus_optional_sina_turnover_leaders",
        "local_universe_count": local_count, "requested_count": len(codes),
        "fresh_count": len(filtered), "full_market_coverage": False,
        "provider_errors": errors,
        "collection_checked_at": now.isoformat(timespec="seconds")
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="intraday_feed.json")
    args = parser.parse_args()
    data = gather()
    Path(args.output).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in data.items() if k != "quotes" and k != "source"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
