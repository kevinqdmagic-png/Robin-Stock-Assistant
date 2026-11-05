"""Bounded Sina HTTPS five-minute history with strict session provenance.

The endpoint is unofficial and returns JSONP.  Callers must still require the
exact 48 canonical A-share bars before publishing an archive.
"""
import json
import math
import re
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = (
    "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_robin5=/"
    "CN_MarketDataService.getKLineData"
)
CODE_RE = re.compile(r"^(sh\.6|sz\.[03])\d{5}$")


def _parse_jsonp(raw):
    text = raw.decode("utf-8", errors="strict") if isinstance(raw, bytes) else str(raw)
    match = re.search(r"=\s*\((\[.*\])\)\s*;?\s*$", text, re.S)
    if not match:
        raise ValueError("sina_invalid_jsonp")
    try:
        payload = json.loads(match.group(1))
    except (ValueError, TypeError) as exc:
        raise ValueError("sina_invalid_json") from exc
    if not isinstance(payload, list):
        raise ValueError("sina_invalid_payload")
    return payload


def fetch_five_minute_sina(code, day, opener=None):
    if not CODE_RE.fullmatch(code):
        raise ValueError("invalid_stock_code")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("invalid_date")
    symbol = code.replace(".", "")
    query = urlencode({"symbol": symbol, "scale": "5", "ma": "no", "datalen": "240"})
    request_url = ENDPOINT + "?" + query
    req = Request(request_url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn/",
        "Accept": "*/*",
    })
    reader = opener or urlopen
    with reader(req, timeout=9) as response:
        raw = response.read(500000)
    payload = _parse_jsonp(raw)
    bars = []
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("sina_bad_row")
        timestamp = str(row.get("day", ""))
        if timestamp[:10] != day:
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", timestamp):
            raise ValueError("sina_bad_timestamp")
        try:
            opening, high, low, closing, volume, amount = (
                float(row[field]) for field in
                ("open", "high", "low", "close", "volume", "amount")
            )
        except (KeyError, ValueError, TypeError, OverflowError) as exc:
            raise ValueError("sina_bad_numeric") from exc
        values = (opening, high, low, closing, volume, amount)
        if not all(map(math.isfinite, values)) or not (
            0 < low <= min(opening, closing) <= max(opening, closing) <= high
        ) or volume < 0 or amount < 0:
            raise ValueError("sina_bad_ohlcv")
        stamp = day.replace("-", "") + timestamp[11:13] + timestamp[14:16] + "00000"
        bars.append({"date": day, "time": stamp, "open": opening, "high": high,
                     "low": low, "close": closing, "volume": volume, "amount": amount})
    if not bars:
        raise ValueError("sina_no_exact_day_bars")
    bars.sort(key=lambda bar: bar["time"])
    if len({bar["time"] for bar in bars}) != len(bars):
        raise ValueError("sina_duplicate_timestamp")
    return {"provider": "sina_https_unofficial", "historical_only": True,
            "frequency": "5", "adjustment": "none", "code": code, "date": day,
            "count": len(bars), "complete_session": len(bars) == 48,
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "request_url": request_url,
            "response_sha256": hashlib.sha256(raw).hexdigest(),
            "coverage_note": "Unverified until exact 48-session validation",
            "bars": bars}
