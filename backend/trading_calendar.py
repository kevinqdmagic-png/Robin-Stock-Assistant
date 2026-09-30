"""Exchange calendar, verified annual notice; unknown years fail closed."""
from datetime import datetime
from zoneinfo import ZoneInfo

CN_TZ = ZoneInfo("Asia/Shanghai")
CALENDAR_SOURCE = "https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml"
CLOSURES_2026 = (
    ("2026-01-01", "2026-01-03"), ("2026-02-15", "2026-02-23"),
    ("2026-04-04", "2026-04-06"), ("2026-05-01", "2026-05-05"),
    ("2026-06-19", "2026-06-21"), ("2026-09-25", "2026-09-27"),
    ("2026-10-01", "2026-10-07"),
)


def session_state(now=None):
    now = (now or datetime.now(CN_TZ)).astimezone(CN_TZ)
    day = now.date().isoformat()
    if now.weekday() >= 5:
        return {"code": "closed", "label": "周末休市", "is_live": False}
    if now.year != 2026:
        return {"code": "unknown", "label": "交易日待核验", "is_live": False}
    if any(start <= day <= end for start, end in CLOSURES_2026):
        return {"code": "closed", "label": "节假日休市", "is_live": False}
    minutes = now.hour * 60 + now.minute
    if 570 <= minutes < 690 or 780 <= minutes < 900:
        return {"code": "trading", "label": "交易时段", "is_live": True}
    if 690 <= minutes < 780:
        return {"code": "lunch", "label": "午间休市", "is_live": False}
    return {"code": "after_close" if minutes >= 900 else "before_open",
            "label": "已收盘" if minutes >= 900 else "盘前", "is_live": False}


def completed_bars(bars, now=None):
    now = (now or datetime.now(CN_TZ)).astimezone(CN_TZ)
    day = now.date().isoformat()
    # Do not admit an incomplete daily candle, even if a provider labels it today.
    complete_today = now.hour * 60 + now.minute >= 910 and session_state(now)["code"] == "after_close"
    return [b for b in bars if b.get("date", "") < day or
            (b.get("date") == day and complete_today)]
