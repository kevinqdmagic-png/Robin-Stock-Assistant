"""Collect dated inputs for the four independent studies and T27/D28 decisions.

This is evidence collection, not a recommendation engine. Preserve failures and
provider periods. All current-session candles must be closed before collection.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import gzip
import json

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp"
T = "2026-10-28"
PREV = "2026-10-27"
START = "2026-10-28T09:44:14+00:00"
OUT = TMP / "combined-20261028-raw.json"
SINA = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
EM = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def stamp():
    return datetime.now(timezone.utc).isoformat()


def get(url, params=None, post=False, timeout=20):
    if params and not post:
        url += "?" + urlencode(params)
    req = Request(url, data=urlencode(params).encode() if post else None,
                  headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.cninfo.com.cn/"})
    try:
        with urlopen(req, timeout=timeout) as r:
            raw = r.read()
        payload = json.loads(raw)
        return {"ok": True, "source": url, "retrieved_at": stamp(), "payload": payload}
    except Exception as exc:
        return {"ok": False, "source": url, "retrieved_at": stamp(),
                "error": type(exc).__name__ + ": " + str(exc)}


def parallel(fn, args, workers=4):
    result = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(fn, a): a for a in args}
        for job in as_completed(jobs):
            result[str(jobs[job])] = job.result()
    return result


def symbol(c):
    return ("bj" if c.startswith(("4", "8", "92")) else "sh" if c.startswith(("5", "6", "9")) else "sz") + c


def daily(c):
    s = symbol(c)
    r = get("https://web.ifzq.gtimg.cn/appstock/app/kline/kline", {"param": f"{s},day,,,180"})
    if r["ok"]:
        block = r["payload"].get("data", {}).get(s, {})
        rows = block.get("day", [])  # No adjusted fallback for raw reference comparisons.
        r["bars"] = [{"date": b[0], "open": float(b[1]), "close": float(b[2]),
                      "high": float(b[3]), "low": float(b[4]), "volume": float(b[5])}
                     for b in rows if b[0] <= T]
        r["latest_date"] = r["bars"][-1]["date"] if r["bars"] else None
        r["adjustment"] = "unadjusted"
        r["volume_unit"] = "provider_lots; compare same-series ratios; Sina shares/100 cross-check"
        if r["latest_date"] != T:
            r["ok"] = False
            r["error"] = "No current completed unadjusted daily bar"
    return r


def minute(c):
    s = symbol(c)
    r = get("https://web.ifzq.gtimg.cn/appstock/app/minute/query", {"code": s})
    if r["ok"]:
        block = r["payload"].get("data", {}).get(s, {})
        data = block.get("data", {})
        r["provider_date"] = str(data.get("date", ""))
        r["points"] = []
        for line in data.get("data", []):
            a = line.split()
            r["points"].append({"clock": a[0], "price": float(a[1]),
                                "cumulative_volume_lots": float(a[2]),
                                "cumulative_amount_cny": float(a[3]) if len(a) > 3 else None})
        r["date_verified"] = r["provider_date"].replace("-", "") == T.replace("-", "")
        r["full_minute_ohlc"] = False
        r["verified_fill"] = False
        if not r["date_verified"]:
            r["ok"] = False
            r["error"] = "Minute date not verified as T"
    return r


def lhb(day):
    return get(EM, {"reportName": "RPT_DAILYBILLBOARD_DETAILS", "columns": "ALL",
                    "filter": f"(TRADE_DATE='{day}')", "pageSize": 500, "pageNumber": 1,
                    "sortColumns": "SECURITY_CODE", "sortTypes": 1, "source": "WEB", "client": "WEB"})


def page(n):
    return get(SINA, {"page": n, "num": 100, "sort": "symbol", "asc": 1,
                      "node": "hs_a", "symbol": "", "_s_r_a": "page"})


def seat(key):
    c, side = key.split(":")
    r = get(EM, {"reportName": "RPT_BILLBOARD_DAILYDETAILS" + side, "columns": "ALL",
                 "filter": f'''(TRADE_DATE='{T}')(SECURITY_CODE="{c}")''',
                 "pageSize": 100, "pageNumber": 1, "source": "WEB", "client": "WEB"})
    if r["ok"]:
        payload = r["payload"]
        r["ok"] = bool(payload.get("success"))
        r["rows"] = (payload.get("result") or {}).get("data") or []
        if not r["ok"]:
            r["error"] = payload.get("message", "seat query failed")
    return r


def main():
    TMP.mkdir(exist_ok=True)
    assert datetime.now(timezone.utc) >= datetime.fromisoformat(T + "T15:10:00+08:00")
    market = json.loads((ROOT / "docs/research/market-review-2026-10-28-evidence.json").read_text())
    low = json.loads((ROOT / "backend/data/low_position_samples.json").read_text())["items"]
    recs = json.loads((ROOT / "backend/data/recommendations.json").read_text())["items"]
    previous = json.loads(gzip.decompress((ROOT / "docs/research/combined-pair-20261027-evidence.json.gz").read_bytes()))
    out = {"market_date": T, "previous_session": PREV, "planned_entry_date": "2026-10-29",
           "actual_started_at_utc": START, "reused_market_report": "market-review-20261028-close-v1",
           "reused_market_evidence": "docs/research/market-review-2026-10-28-evidence.json",
           "sina_pages": parallel(page, range(1, 61), workers=4)}
    quotes = {}
    for r in out["sina_pages"].values():
        if r["ok"] and isinstance(r["payload"], list):
            quotes.update({q["code"]: q for q in r["payload"]})
    out["quotes"] = quotes
    out["lhb_lists"] = parallel(lhb, ["2026-10-26", PREV, T], workers=3)
    current_rows = (out["lhb_lists"][T].get("payload", {}).get("result") or {}).get("data") or []
    old_rows = previous["lhb_lists"][PREV]["payload"]["result"]["data"]
    codes = {r["code"] for r in market["broad_pool"] + low + recs}
    codes.update(r["SECURITY_CODE"] for r in old_rows + current_rows)
    codes.update(previous["daily_histories"])
    # Preserve every T26 ordinary-main denominator from its contemporaneously archived full pool.
    prior_ladder = ["002724", "603278", "600838", "603089", "603528", "002535", "003021",
                    "603028", "000678", "603280", "603933", "301502"]
    codes.update(prior_ladder)
    codes.update(r["c"] for r in previous["limit_up_pools"][PREV]["payload"]["data"]["pool"])
    codes.update(r["c"] for r in previous["derived"]["limit_pool_reconciliation"]["added_records"])
    codes.update(["600592", "603331", "603007", "603719", "001219", "000411"])
    out["daily_histories"] = parallel(daily, sorted(codes), workers=4)
    # Historical exact single-day limit-up pools provide an independent ladder denominator.
    def pool(day):
        return get("https://push2ex.eastmoney.com/getTopicZTPool", {
            "ut": "7eea3edcaed734bea9cbfc24409ed989", "dpt": "wz.ztzt", "Pageindex": 0,
            "pagesize": 1000, "sort": "fbt:asc", "date": day.replace("-", ""), "_": ""})
    out["limit_up_pools"] = parallel(pool, ["2026-10-26", PREV, T], workers=3)
    # Selected single-day seat comparisons include support, breakdown and high-position controls.
    focus = ["000678","600838","603028","603528","001219","002708","002093","001331","605333","600826","600865","000554","600078","603109","603633","603699","603337","300539","300549","002696","001400","003028","002889","002820"]
    available = {r["SECURITY_CODE"] for r in current_rows}
    focus = [c for c in focus if c in available]
    out["seat_queries"] = parallel(seat, [c + ":" + s for c in focus for s in ("BUY", "SELL")], workers=4)
    minute_codes = {r["code"] for r in market["deep_pool"]}
    minute_codes.update(r["code"] for r in market["previous_pool_validation"])
    minute_codes.update(focus)
    minute_codes.update(r["code"] for r in low)
    out["minute_price_points"] = parallel(minute, sorted(minute_codes), workers=4)
    out["actual_collection_completed_at_utc"] = stamp()
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(OUT.relative_to(ROOT)), "raw_quotes": len(quotes),
        "page_errors": [k for k, v in out["sina_pages"].items() if not v["ok"]],
        "daily_ok": sum(v["ok"] for v in out["daily_histories"].values()), "daily_total": len(codes),
        "daily_errors": {c: v.get("error") for c, v in out["daily_histories"].items() if not v["ok"]},
        "lhb_rows": len(current_rows), "lhb_unique": len(available), "seat_codes": focus,
        "seat_errors": {c: v.get("error") for c, v in out["seat_queries"].items() if not v["ok"]},
        "minute_ok": sum(v["ok"] for v in out["minute_price_points"].values()),
        "minute_total": len(minute_codes),
        "pool_status": {d: {"ok": v["ok"], "payload_keys": list(v.get("payload", {}))} for d, v in out["limit_up_pools"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
