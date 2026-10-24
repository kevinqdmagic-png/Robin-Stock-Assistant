"""Collect fresh, dated public evidence for the manual 23 October completion."""
import concurrent.futures
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
T = "2026-10-23"
def load(path):
    return json.loads((ROOT / path).read_bytes())
def get(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"})
    with urlopen(req, timeout=18) as r:
        return r.read()
def daily(code):
    symbol = ("sh" if code.startswith(("5", "6", "9")) else "sz") + code
    url = f"https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param={symbol},day,,,180"
    try:
        raw = json.loads(get(url)); block = raw["data"][symbol]
        rows = block.get("day")
        if not rows:
            raise ValueError("unadjusted_daily_missing")
        bars = [{"date": x[0], "open": float(x[1]), "close": float(x[2]), "high": float(x[3]), "low": float(x[4]), "volume": float(x[5])} for x in rows if x[0] <= T]
        if not bars or bars[-1]["date"] != T:
            raise ValueError("latest_completed_bar_not_2026_10_23")
        return code, {"source": url, "adjustment": "unadjusted", "bars": bars}
    except Exception as e:
        return code, {"source": url, "error": type(e).__name__ + ": " + str(e)}
def main():
    low = load("backend/data/low_position_samples.json")["items"]
    recs = load("backend/data/recommendations.json")["items"]
    market = load("docs/research/low-dragon-2026-10-23-market-scan.json")
    codes = {x["code"] for x in low + recs + market["deep_pool"]}
    codes.update(["002724", "603278", "002343", "600592", "002747", "603466", "002354", "688368"])
    result = {"market_date": T, "started_at_utc": datetime.now(timezone.utc).isoformat(), "daily": {}, "other_sources": {}}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for code, item in pool.map(daily, sorted(codes)):
            result["daily"][code] = item
    sources = {
        "index_quotes": "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688",
        "lhb_details": "https://datacenter-web.eastmoney.com/api/data/v1/get?" + urlencode({"reportName": "RPT_DAILYBILLBOARD_DETAILS", "columns": "ALL", "filter": "(TRADE_DATE='2026-10-23')", "pageSize": "500", "pageNumber": "1", "sortColumns": "SECURITY_CODE", "sortTypes": "1", "source": "WEB", "client": "WEB"}),
        "cls_limitup": "https://www.cls.cn/detail/2513445",
        "em_ladder": "https://finance.eastmoney.com/a/202610233906254776.html",
        "em_institutions": "https://finance.eastmoney.com/a/202610233906358266.html",
    }
    def retrieve(pair):
        key, url = pair
        try:
            b = get(url)
            text = b.decode("gb18030" if key == "index_quotes" else "utf-8", errors="replace")
            value = json.loads(text) if key == "lhb_details" else text
            return key, {"source": url, "payload": value}
        except Exception as e:
            return key, {"source": url, "error": type(e).__name__ + ": " + str(e)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        result["other_sources"] = dict(pool.map(retrieve, sources.items()))
    result["retrieved_at_utc"] = datetime.now(timezone.utc).isoformat()
    scratch = ROOT.parent / "task_audit_20261023" / "completion_raw.json"
    scratch.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(scratch), "daily_ok": sum("bars" in x for x in result["daily"].values()), "daily_total": len(codes), "errors": {c:x["error"] for c,x in result["daily"].items() if "error" in x}, "sources": {k: x.get("error", "ok") for k,x in result["other_sources"].items()}}, ensure_ascii=False))
if __name__ == "__main__":
    main()
