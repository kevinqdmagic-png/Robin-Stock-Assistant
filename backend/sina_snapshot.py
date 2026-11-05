"""Independent SH/SZ daily backup from timestamped, post-close Sina quotes."""
from datetime import datetime
import math
import re
from urllib.request import Request, urlopen

from daily_snapshot import STOCK_CODE_RE

PROVIDER = "sina_close_snapshot"


def parse_close_snapshot(raw, codes, day):
    wanted = {code.replace(".", ""): code for code in codes if STOCK_CODE_RE.fullmatch(code)}
    rows = {}
    for symbol, body in re.findall(r'hq_str_((?:sh|sz)\d{6})="([^"]*)"', raw):
        fields = body.split(",")
        if symbol not in wanted or len(fields) < 32 or fields[30] != day:
            continue
        try:
            stamp = datetime.strptime(fields[30] + " " + fields[31], "%Y-%m-%d %H:%M:%S")
            if (stamp.hour, stamp.minute) < (15, 0):
                continue
            o, previous, c, h, l, volume, amount = [float(fields[i]) for i in (1, 2, 3, 4, 5, 8, 9)]
            if not all(math.isfinite(v) for v in (o, previous, c, h, l, volume, amount)):
                continue
            if not (0 < l <= min(o, c) <= max(o, c) <= h and volume >= 0 and amount >= 0 and previous > 0):
                continue
            code = wanted[symbol]
            if code in rows:
                raise ValueError("duplicate_sina_close_code")
            rows[code] = {"code": code, "date": day, "name": fields[0],
                          "open": o, "high": h, "low": l, "close": c,
                          "preclose": previous, "pctChg": (c / previous - 1) * 100,
                          "volume": volume, "amount": amount, "volume_unit": "shares",
                          "provider": PROVIDER, "adjustment": "none",
                          "quote_as_of": stamp.isoformat() + "+08:00", "historical_only": True}
        except (ValueError, TypeError, IndexError):
            continue
    return list(rows.values())


def fetch_close_batch(codes, day, opener=urlopen):
    if not 1 <= len(codes) <= 45 or any(not STOCK_CODE_RE.fullmatch(code) for code in codes):
        raise ValueError("invalid_close_batch")
    datetime.strptime(day, "%Y-%m-%d")
    url = "https://hq.sinajs.cn/list=" + ",".join(code.replace(".", "") for code in codes)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"})
    with opener(request, timeout=10) as response:
        raw = response.read(300000).decode("gb18030")
    return parse_close_snapshot(raw, codes, day)
