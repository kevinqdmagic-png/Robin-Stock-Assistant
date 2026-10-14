#!/usr/bin/env python3
"""Fetch a timestamped partial A-share candidate universe; no simulated prices.

Universe consists of versioned app research/watch stocks + recent historical
recommendation codes, supplemented by Eastmoney and Sina turnover leaders.
Independent Tencent spot quotes are required to validate every observed row.
A partial universe is NEVER advertised as a whole-market scan.
"""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from quote_providers import stock_symbol
import requests

CN = ZoneInfo("Asia/Shanghai")
SOURCE = "https://qt.gtimg.cn/q="
SINA = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
EASTMONEY = ("https://push2.eastmoney.com/api/qt/clist/get",
             "https://push2delay.eastmoney.com/api/qt/clist/get")
MARKET_SCOPE = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"



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


def eastmoney_leaders(client=requests, limit=100):
    """Discovery candidates only; no Eastmoney price is used without fresh Tencent verification.

    The public website endpoints can return HTTP 502 or IP-based throttling.
    We only request one page from a preferred and a failover hostname.
    """
    params = {
        "pn": 1, "pz": limit, "po": 1, "np": 1, "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2, "fid": "f6", "fs": MARKET_SCOPE,
        "fields": "f12,f14,f6",
    }
    failures = []
    for url in EASTMONEY:
        try:
            response = client.get(url, params=params, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://quote.eastmoney.com/",
            }, timeout=(3, 4))
            response.raise_for_status()
            data = response.json().get("data") or {}
            records = data.get("diff") or []
            if isinstance(records, dict):
                records = list(records.values())
            if not isinstance(records, list) or not records:
                raise ValueError("eastmoney_no_candidate_rows")
            codes = [str(item.get("f12") or "") for item in records if isinstance(item, dict)]
            selected = list(dict.fromkeys(c for c in codes if re.fullmatch(r"[0-9]{6}", c)))
            if selected:
                return selected, url
            raise ValueError("eastmoney_no_valid_codes")
        except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
            failures.append(type(exc).__name__)
    raise ValueError("eastmoney_unavailable:" + ",".join(failures))


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



def parse_eastmoney(records, requested, url):
    """Live Eastmoney quote: field f124 is the provider's Unix timestamp.

    f5=hands (100 shares), f6=CNY, f8=turnover percentage, f18=previous close.
    Never substitute response/collection time for an absent quote timestamp.
    """
    rows = []
    for item in records:
        if not isinstance(item, dict):
            continue
        code = str(item.get("f12") or "")
        if code not in requested or not re.fullmatch(r"\d{6}", code):
            continue
        name = str(item.get("f14") or "").strip()
        if not name or "ST" in name.upper() or "退" in name:
            continue
        try:
            price, prev, pct, amount, lots, turnover = [
                float(item[k]) for k in ("f2", "f18", "f3", "f6", "f5", "f8")]
            stamp = datetime.fromtimestamp(int(item["f124"]), CN)
            vr = None
            try:
                vr = float(item.get("f10"))
                if not 0 <= vr <= 1000:
                    vr = None
            except (ValueError, TypeError):
                pass
        except (KeyError, ValueError, TypeError, OverflowError, OSError):
            continue
        if not all(math.isfinite(z) for z in (price, prev, pct, amount, lots, turnover)):
            continue
        if not (0 < price < 100000 and 0 < prev < 100000
                and amount > 0 and lots > 0 and 0 <= turnover <= 100):
            continue
        if abs((price / prev - 1) * 100 - pct) > 0.4:
            continue
        symbol = stock_symbol(code)
        secid = ("1." if symbol.startswith("sh") else "0.") + code
        rows.append({
            "code": code, "name": name, "market": symbol[:2].upper(),
            "price": round(price, 3), "previous_close": round(prev, 3),
            "volume": lots * 100, "turnover": amount,
            "turnover_ratio": round(turnover, 2), "pct": round(pct, 2),
            "volume_ratio": vr, "as_of": stamp.isoformat(timespec="seconds"),
            "source": url + "?secids=" + secid,
        })
    return rows


def eastmoney_batch(client, codes):
    """Fallback across main and delayed endpoints; no synthesized quotes."""
    params = {
        "secids": ",".join(("1." if stock_symbol(c).startswith("sh") else "0.") + c for c in codes),
        "fltt": 2, "invt": 2,
        "fields": "f2,f3,f5,f6,f8,f10,f12,f14,f18,f124",
    }
    failures = []
    for endpoint in EASTMONEY:
        url = endpoint.replace("/clist/get", "/ulist.np/get")
        try:
            response = client.get(url, params=params,
                  headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
                  timeout=(3, 5))
            response.raise_for_status()
            data = response.json().get("data") or {}
            records = data.get("diff") or []
            if isinstance(records, dict):
                records = list(records.values())
            if not isinstance(records, list):
                raise ValueError("wrong_quote_schema")
            rows = parse_eastmoney(records, set(codes), url)
            if rows:
                return rows
            raise ValueError("eastmoney_quote_empty")
        except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
            failures.append(type(exc).__name__)
    raise ValueError("eastmoney_quote_unavailable:" + ",".join(failures))

def gather(now=None, client=requests, root=ROOT):
    now = (now or datetime.now(CN)).astimezone(CN)
    errors = []
    codes = local_universe(root)
    local_count = len(codes)
    discovery_sources = ["versioned_stock_research_and_prior_recommendations"]
    try:
        eastmoney, discovery_host = eastmoney_leaders(client)
        codes.extend(code for code in eastmoney if code not in codes)
        discovery_sources.append(discovery_host)
    except (requests.RequestException, ValueError, TypeError) as exc:
        errors.append("eastmoney_discovery:" + type(exc).__name__)
    try:
        leaders = sina_leaders(client)
        discovery_sources.append(SINA)
        codes.extend(code for code in leaders if code not in codes)
    except (requests.RequestException, ValueError, TypeError) as exc:
        errors.append("sina_discovery:" + type(exc).__name__)
    codes = codes[:180]
    symbols = [stock_symbol(code) for code in codes]
    by_code, corroborated, conflicts = {}, set(), set()
    source_counts = {"tencent": 0, "eastmoney": 0}
    for i in range(0, len(symbols), 60):
        batch = symbols[i:i+60]
        codes_batch = [s[-6:] for s in batch]
        feeds = {}
        try:
            response = client.get(SOURCE + ",".join(batch), headers={
                "User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"
            }, timeout=(4, 7))
            response.raise_for_status()
            response.encoding = "gb18030"
            feeds["tencent"] = parse_tencent(response.text, batch)
        except (requests.RequestException, ValueError) as exc:
            errors.append("tencent_batch:" + type(exc).__name__)
        try:
            feeds["eastmoney"] = eastmoney_batch(client, codes_batch)
        except (requests.RequestException, ValueError) as exc:
            errors.append("eastmoney_quote_batch:" + type(exc).__name__)

        fresh = {}
        for provider, values in feeds.items():
            for q in values:
                asof = datetime.fromisoformat(q["as_of"])
                seconds = (now - asof).total_seconds()
                if asof.date() == now.date() and 0 <= seconds <= 300:
                    fresh.setdefault(q["code"], {})[provider] = q
        for code, witnesses in fresh.items():
            t, e = witnesses.get("tencent"), witnesses.get("eastmoney")
            if t and e:
                separation = abs((datetime.fromisoformat(t["as_of"]) -
                                  datetime.fromisoformat(e["as_of"])).total_seconds())
                if separation <= 30:
                    difference = abs(t["price"] - e["price"]) / max(t["price"], e["price"])
                    if difference > 0.006:
                        conflicts.add(code)
                        continue
                    corroborated.add(code)
            # Choose the newest independently timestamped quote in the allowed window.
            chosen = max(witnesses.values(), key=lambda q: q["as_of"])
            chosen["cross_checked"] = code in corroborated
            by_code[code] = chosen
            source_counts["tencent" if chosen["source"].startswith(SOURCE) else "eastmoney"] += 1

    # Exclude conflicting same-time quotes, never claim complete market coverage.
    valid = [q for code, q in by_code.items() if code not in conflicts]
    return {
        "source": valid[0]["source"] if valid else SOURCE,
        "as_of": max((q["as_of"] for q in valid), default=now.isoformat(timespec="seconds")),
        "quotes": valid, "scope": "research_watchlist_plus_optional_eastmoney_and_sina_turnover_leaders",
        "discovery_sources": discovery_sources,
        "local_universe_count": local_count, "requested_count": len(codes),
        "fresh_count": len(valid),
        "fresh_coverage_pct": round(len(valid) * 100 / len(codes), 1) if codes else 0,
        "corroborated_count": len(corroborated),
        "provider_quote_counts": source_counts,
        "provider_disagreements": len(conflicts),
        "full_market_coverage": False, "provider_errors": errors,
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
