"""Independent public quote fallback, with the provider's own quote timestamp."""
from datetime import datetime
import math
import re

import requests

from analytics import number
from trading_calendar import CN_TZ


def stock_symbol(code):
    if code.startswith(("4", "8", "92")):
        return "bj" + code
    return ("sh" if code.startswith(("5", "6", "9")) else "sz") + code


def parse_sina_quotes(raw, symbols):
    """Independent timestamped SH/SZ quotes; absent ratios stay unknown."""
    wanted = set(symbols)
    quotes = {}
    for symbol, body in re.findall(r'hq_str_((?:sh|sz)\d{6})="([^"]*)"', raw):
        fields = body.split(",")
        if symbol not in wanted or len(fields) < 32:
            continue
        price, previous = number(fields[3]), number(fields[2])
        if (price is None or previous is None or not math.isfinite(price) or not math.isfinite(previous)
                or price <= 0 or previous <= 0 or not fields[0]):
            continue
        try:
            stamp = datetime.strptime(fields[30] + " " + fields[31], "%Y-%m-%d %H:%M:%S").replace(tzinfo=CN_TZ)
        except ValueError:
            continue
        quotes[symbol] = {
            "code": symbol[-6:], "name": fields[0], "price": price,
            "pct": round((price / previous - 1) * 100, 2),
            "as_of": stamp.isoformat(timespec="seconds"),
            "turnover": None, "volume_ratio": None, "source": "sina_public",
            "pct_basis": "provider_previous_close", "previous_close": previous,
        }
    return [quotes[s] for s in symbols if s in quotes]


def sina_quotes(symbols, timeout=(3.5, 5)):
    symbols = list(dict.fromkeys(s for s in symbols if re.fullmatch(r"(?:sh|sz)\d{6}", s)))
    if not symbols:
        return []
    response = requests.get("https://hq.sinajs.cn/list=" + ",".join(symbols), headers={
        "User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/",
    }, timeout=timeout)
    response.raise_for_status()
    response.encoding = "gb18030"
    rows = parse_sina_quotes(response.text, symbols)
    if not rows:
        raise ValueError("sina_quote_empty_or_invalid")
    return rows


def tencent_quotes(symbols, timeout=(4, 5)):
    symbols = list(dict.fromkeys(symbols))
    response = requests.get(
        "https://qt.gtimg.cn/q=" + ",".join(symbols),
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"},
        timeout=timeout,
    )
    response.raise_for_status()
    response.encoding = "gb18030"
    quotes = {}
    for symbol, body in re.findall(r'v_((?:sh|sz|bj)\d{6})="([^"]*)"', response.text):
        fields = body.split("~")
        if symbol not in symbols or len(fields) <= 32 or fields[2] != symbol[-6:]:
            continue
        price, pct = number(fields[3]), number(fields[32])
        if price is None or price <= 0 or pct is None or not fields[1]:
            continue
        try:
            if len(fields[30]) != 14:
                continue
            as_of = datetime.strptime(fields[30], "%Y%m%d%H%M%S").replace(tzinfo=CN_TZ)
        except ValueError:
            continue
        quotes[symbol] = {
            "code": fields[2], "name": fields[1], "price": round(price, 3),
            "pct": round(pct, 2), "as_of": as_of.isoformat(timespec="seconds"),
            "turnover": number(fields[38]) if len(fields) > 38 else None,
            "volume_ratio": number(fields[49]) if len(fields) > 49 else None,
            "source": "tencent_public",
        }
    if not quotes:
        raise ValueError("tencent_quote_empty_or_invalid")
    return [quotes[symbol] for symbol in symbols if symbol in quotes]
