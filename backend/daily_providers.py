"""Independent historical A-share day-K fallback.

The Tencent public endpoint is best-effort and can fail or change schema.
Never infer a bar from a quote, invent volume, or silently mix adjustment types.
"""
from datetime import date
import math
import re
import threading
import time

import requests

from quote_providers import stock_symbol

URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
# A provider-wide 501/502/503 response is not a per-security data failure.
# Short cooldown avoids repeated requests while independent sources can serve
# valid unadjusted historical bars. It never fabricates adjusted bars.
_TENCENT_RETRY_SECONDS = 300
_tencent_retry_after = 0.0
_tencent_guard = threading.Lock()


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
    # Only the real shared HTTP client participates in the process-wide gate.
    # Injected test clients remain independent and deterministic.
    global _tencent_retry_after
    if client is requests:
        with _tencent_guard:
            if time.monotonic() < _tencent_retry_after:
                raise ValueError("tencent_daily_circuit_open")
    param = f"{symbol},day,,,{limit}," + ("qfq" if adjust == "1" else "none")
    try:
        response = client.get(URL, params={"param": param}, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://gu.qq.com/",
        }, timeout=(3.5, 6))
        response.raise_for_status()
    except requests.HTTPError as exc:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        if client is requests and status in (501, 502, 503, 504):
            with _tencent_guard:
                _tencent_retry_after = max(
                    _tencent_retry_after, time.monotonic() + _TENCENT_RETRY_SECONDS
                )
        raise
    payload = response.json()
    return parse_tencent_daily(payload, symbol, adjust=adjust, limit=limit)


def parse_sina_daily(payload, limit=120):
    """Validate Sina unadjusted day-K fallback without inventing bars or units.

    Sina CN_MarketDataService.getKLineData returns a list of records with
    day/open/high/low/close/volume. This parser accepts only explicit dates
    and valid OHLCV; volume remains provider-native.
    """
    import datetime
    if not isinstance(payload, list):
        raise ValueError("invalid_sina_daily_response")
    rows = []
    seen = set()
    for item in payload[-limit:]:
        if not isinstance(item, dict):
            continue
        try:
            day = datetime.date.fromisoformat(str(item["day"])[:10]).isoformat()
            opening = float(item["open"])
            closing = float(item["close"])
            high = float(item["high"])
            low = float(item["low"])
            volume = float(item["volume"])
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        if not all(math.isfinite(v) for v in (opening, closing, high, low, volume)):
            continue
        if not (0 < low <= min(opening, closing) <= max(opening, closing) <= high and volume >= 0):
            continue
        if day in seen:
            raise ValueError("duplicate_sina_daily_date")
        seen.add(day)
        rows.append({"date": day, "open": opening, "close": closing,
                     "high": high, "low": low, "volume": volume})
    if not rows:
        raise ValueError("no_valid_sina_daily_bars")
    return sorted(rows, key=lambda r: r["date"])


def sina_daily(code, limit=120, client=requests):
    """Independent free unadjusted historical fallback, bounded and validated."""
    import json
    if not re.fullmatch(r"[0-9]{6}", str(code)):
        raise ValueError("invalid_stock_code")
    if not isinstance(limit, int) or limit < 1 or limit > 240:
        raise ValueError("invalid_history_limit")
    symbol = stock_symbol(code)
    if symbol.startswith("bj"):
        raise ValueError("sina_beijing_unsupported")
    # jsonp_v2 requires a callback path segment; omitting it returns HTTP 200
    # with "Invalid service name" rather than any bars.
    url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_robin=/CN_MarketDataService.getKLineData"
    response = client.get(url, params={"symbol": symbol, "scale": 240,
                          "ma": "no", "datalen": limit}, headers={
        "User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"
    }, timeout=(3.5, 7))
    response.raise_for_status()
    raw = response.text.strip()
    # The endpoint returns JSONP; extract only a single list payload.
    start, end = raw.find("(["), raw.rfind("])")
    if start < 0 or end < start:
        raise ValueError("invalid_sina_jsonp_wrapper")
    payload = json.loads(raw[start + 1:end + 1])
    return parse_sina_daily(payload, limit=limit)


def historical_daily_with_fallback(code, limit=120, adjust="0", client=requests):
    """Try Tencent first; Sina only when requesting unadjusted history.

    Return provenance explicitly. Never silently replace adjusted Tencent bars
    with unadjusted Sina bars, and never turn missing data into a trade signal.
    """
    errors = {}
    try:
        rows = tencent_daily(code, limit=limit, adjust=adjust, client=client)
        return {"rows": rows, "provider": "tencent", "adjustment": adjust,
                "fallback_used": False}
    except (requests.RequestException, ValueError, TypeError) as exc:
        errors["tencent"] = type(exc).__name__
    if adjust != "0":
        raise ValueError("adjusted_history_fallback_unavailable")
    try:
        rows = sina_daily(code, limit=limit, client=client)
        return {"rows": rows, "provider": "sina", "adjustment": "0",
                "fallback_used": True, "primary_error": errors["tencent"]}
    except (requests.RequestException, ValueError, TypeError) as exc:
        errors["sina"] = type(exc).__name__
    raise ValueError("all_unadjusted_daily_sources_failed:" + ",".join(errors))
