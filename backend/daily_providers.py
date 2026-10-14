"""Independent historical A-share day-K fallback.

The Tencent public endpoint is best-effort and can fail or change schema.
Never infer a bar from a quote, invent volume, or silently mix adjustment types.
"""
from datetime import date
import math
import re

import requests

from quote_providers import stock_symbol

URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"


def parse_tencent_daily(payload, symbol, adjust="1", limit=120):
    if adjust not in ("0", "1"):
        raise ValueError("unsupported_adjustment")
    if not isinstance(payload, dict):
        raise ValueError("invalid_daily_response")
    node = (payload.get("data") or {}).get(symbol)
    if not isinstance(node, dict):
        raise ValueError("symbol_absent_from_daily_response")
    # A forward-adjusted strategy must not silently use unadjusted prices,
    # nor may performance verification use forward-adjusted prices.
    key = "qfqday" if adjust == "1" else "day"
    raw = node.get(key)
    if not isinstance(raw, list) or not raw:
        raise ValueError("requested_adjustment_unavailable")
    rows = []
    seen = set()
    for fields in raw[-limit:]:
        if not isinstance(fields, (list, tuple)) or len(fields) < 6:
            continue
        try:
            day = date.fromisoformat(str(fields[0])).isoformat()
            opening, closing, high, low, volume = [float(v) for v in fields[1:6]]
        except (ValueError, TypeError, OverflowError):
            continue
        if not all(math.isfinite(v) for v in (opening, closing, high, low, volume)):
            continue
        if not (0 < opening <= high + 1e-5 and
                0 < closing <= high + 1e-5 and
                0 < low <= min(opening, closing) + 1e-5 and volume >= 0):
            continue
        if day in seen:
            raise ValueError("duplicate_daily_date")
        seen.add(day)
        # Volume is the provider's own unit. Same-security ratios are comparable
        # within this source, but absolute shares are not inferred.
        rows.append({"date": day, "open": opening, "close": closing,
                     "high": high, "low": low, "volume": volume})
    if not rows:
        raise ValueError("no_valid_tencent_daily_bars")
    rows.sort(key=lambda x: x["date"])
    return rows


def tencent_daily(code, limit=120, adjust="1", client=requests):
    if not re.fullmatch(r"[0-9]{6}", str(code)):
        raise ValueError("invalid_stock_code")
    if adjust not in ("0", "1"):
        raise ValueError("unsupported_adjustment")
    symbol = stock_symbol(code)
    param = f"{symbol},day,,,{limit}," + ("qfq" if adjust == "1" else "none")
    response = client.get(URL, params={"param": param}, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://gu.qq.com/",
    }, timeout=(3.5, 6))
    response.raise_for_status()
    payload = response.json()
    return parse_tencent_daily(payload, symbol, adjust=adjust, limit=limit)
