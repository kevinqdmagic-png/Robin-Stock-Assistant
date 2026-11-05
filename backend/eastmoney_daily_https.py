"""Free HTTPS daily OHLCV fallback. No silent substitution of stale candles."""
import json
import math
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
CODE = re.compile(r"^(sh\.6|sz\.[03])\d{5}$")


def fetch_daily_https(code, day, opener=None):
    if not CODE.fullmatch(code):
        raise ValueError("invalid_code")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("invalid_day")
    secid = ("1." if code.startswith("sh.") else "0.") + code[3:]
    args = {"secid": secid, "klt": "101", "fqt": "0",
            "beg": day.replace("-", ""), "end": day.replace("-", ""),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"}
    req = Request(ENDPOINT + "?" + urlencode(args),
                  headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})
    with (opener or urlopen)(req, timeout=8) as resp:
        payload = json.loads(resp.read(200000))
    rows = (payload.get("data") or {}).get("klines") or []
    if len(rows) != 1:
        raise ValueError("daily_missing_or_duplicate")
    fields = rows[0].split(",")
    if len(fields) < 7 or fields[0] != day:
        raise ValueError("daily_wrong_date_or_schema")
    try:
        op, close, high, low, vol, amount = map(float, fields[1:7])
    except (ValueError, TypeError) as exc:
        raise ValueError("daily_invalid_numeric") from exc
    if not all(math.isfinite(x) for x in (op, close, high, low, vol, amount)):
        raise ValueError("daily_nonfinite")
    if not (0 < low <= min(op, close) <= max(op, close) <= high and vol >= 0 and amount >= 0):
        raise ValueError("daily_invalid_ohlcv")
    return {"code": code, "date": day, "open": op, "high": high, "low": low,
            "close": close, "volume": vol, "amount": amount,
            "provider": "eastmoney_https_unofficial", "adjustment": "none",
            "volume_unit": "lots_100_shares",
            "historical_only": True}
