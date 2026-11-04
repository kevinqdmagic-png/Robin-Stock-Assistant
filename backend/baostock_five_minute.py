"""Bounded BaoStock historical five-minute OHLCV retrieval; never a live quote."""
from datetime import date, datetime, timedelta
import math
import re

FIELDS = "date,time,code,open,high,low,close,volume,amount,adjustflag"
CODE_RE = re.compile(r"^(sh\.6|sz\.[03])\d{5}$")


def fetch_five_minute(code, day, client=None):
    if not CODE_RE.fullmatch(code):
        raise ValueError("invalid_baostock_code")
    target = date.fromisoformat(day)
    if target > date.today() or target < date.today() - timedelta(days=365 * 5):
        raise ValueError("historical_date_out_of_range")
    if client is None:
        import baostock as client
    login = client.login()
    if login.error_code != "0":
        raise ValueError("baostock_login_failed:" + str(login.error_code))
    try:
        result = client.query_history_k_data_plus(
            code, FIELDS, start_date=day, end_date=day,
            frequency="5", adjustflag="3")
        if result.error_code != "0":
            raise ValueError("baostock_five_minute_query_failed:" + str(result.error_code))
        rows = []
        seen = set()
        while result.next():
            record = dict(zip(result.fields, result.get_row_data()))
            if record.get("date") != day or record.get("code") != code:
                raise ValueError("baostock_mismatched_bar_identity")
            stamp = record.get("time", "")
            if not re.fullmatch(r"\d{17}", stamp) or stamp[:8] != day.replace("-", ""):
                raise ValueError("invalid_five_minute_timestamp")
            if stamp in seen:
                raise ValueError("duplicate_five_minute_timestamp")
            seen.add(stamp)
            try:
                opening, high, low, closing, volume, amount = (
                    float(record[k]) for k in ("open", "high", "low", "close", "volume", "amount"))
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError("invalid_five_minute_numeric") from exc
            if (not all(math.isfinite(x) for x in (opening, high, low, closing, volume, amount))
                    or low <= 0 or low > min(opening, closing)
                    or high < max(opening, closing) or volume < 0 or amount < 0):
                raise ValueError("invalid_five_minute_ohlcv")
            rows.append({"date": day, "time": stamp, "open": opening,
                         "high": high, "low": low, "close": closing,
                         "volume": volume, "amount": amount})
        if not rows:
            raise ValueError("baostock_five_minute_empty")
        rows.sort(key=lambda row: row["time"])
        return {"provider": "baostock", "historical_only": True,
                "frequency": "5", "adjustment": "none",
                "code": code, "date": day, "count": len(rows),
                "complete_session": len(rows) == 48,
                "coverage_note": "48 bars expected for ordinary full trading session; verify suspensions and special sessions",
                "bars": rows}
    finally:
        client.logout()
