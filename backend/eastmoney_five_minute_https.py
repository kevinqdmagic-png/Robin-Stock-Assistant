"""Bounded, unadjusted Eastmoney HTTPS 5-minute historical K-line candidate.

Unofficial endpoint; never claim coverage or success without exact session validation.
"""
import json
import math
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
CODE_RE = re.compile(r"^(sh\.6|sz\.[03])\d{5}$")


def fetch_five_minute_https(code, day, opener=None):
    if not CODE_RE.fullmatch(code):
        raise ValueError("invalid_stock_code")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("invalid_date")
    secid = ("1." if code.startswith("sh.") else "0.") + code.split(".")[1]
    params = {
        "secid": secid, "klt": "5", "fqt": "0",
        "beg": day.replace("-", ""), "end": day.replace("-", ""),
        "lmt": "60", "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }
    req = Request(ENDPOINT + "?" + urlencode(params), headers={
        "User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/",
        "Accept": "application/json",
    })
    reader = opener or urlopen
    with reader(req, timeout=8) as response:
        raw = response.read(200000)
    try:
        payload = json.loads(raw)
        data = payload.get("data") or {}
        entries = data.get("klines") or []
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("eastmoney_invalid_json") from exc
    if not entries:
        raise ValueError("eastmoney_empty")
    bars = []
    for line in entries:
        fields = line.split(",")
        if len(fields) < 7:
            raise ValueError("eastmoney_bad_row")
        timestamp = fields[0]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", timestamp):
            raise ValueError("eastmoney_bad_timestamp")
        if timestamp[:10] != day:
            raise ValueError("eastmoney_wrong_session")
        try:
            opening, closing, high, low, volume, amount = map(float, fields[1:7])
        except (ValueError, TypeError) as exc:
            raise ValueError("eastmoney_bad_numeric") from exc
        if not all(map(math.isfinite, (opening, closing, high, low, volume, amount))) or not (
            0 < low <= min(opening, closing) <= max(opening, closing) <= high
        ) or volume < 0 or amount < 0:
            raise ValueError("eastmoney_bad_ohlcv")
        stamp = timestamp[:10].replace("-", "") + timestamp[11:13] + timestamp[14:16] + "00000"
        bars.append({"date": day, "time": stamp, "open": opening, "high": high,
                     "low": low, "close": closing, "volume": volume, "amount": amount})
    bars.sort(key=lambda b: b["time"])
    if len({b["time"] for b in bars}) != len(bars):
        raise ValueError("eastmoney_duplicate_timestamp")
    return {"provider": "eastmoney_https_unofficial", "historical_only": True,
            "frequency": "5", "adjustment": "none", "code": code, "date": day,
            "count": len(bars), "complete_session": len(bars) == 48,
            "coverage_note": "Unverified until exact 48-session validation",
            "bars": bars}
