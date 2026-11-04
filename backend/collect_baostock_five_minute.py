"""Collect verified BaoStock five-minute history to a dated JSON artifact."""
import json
import os
from datetime import datetime
from pathlib import Path
from baostock_five_minute import fetch_five_minute
from eastmoney_five_minute_https import fetch_five_minute_https
from learning_loop import CN, latest_completed_session

def default_research_day(now=None):
    """Resolve the latest completed A-share session in Beijing time."""
    completed = latest_completed_session(now or datetime.now(CN))
    if completed is None:
        raise RuntimeError("completed_session_calendar_unavailable")
    return completed.isoformat()


DAY = os.environ.get("RESEARCH_DAY") or default_research_day()
OUT = Path("backend/data/baostock_five_minute") / (DAY + ".json")
CODES = ("sz.002218", "sh.688109")


def validate_session(item, code, day):
    """Require all 48 canonical five-minute bar endpoints, not just 48 rows."""
    bars = item.get("bars", [])
    if item.get("code") != code or item.get("date") != day or len(bars) != 48:
        return False
    # Trading intervals are 09:35..11:30 and 13:05..15:00, 48 in total.
    canonical = []
    for start, end in ((9 * 60 + 35, 11 * 60 + 30), (13 * 60 + 5, 15 * 60)):
        canonical.extend(f"{day.replace('-', '')}{m // 60:02d}{m % 60:02d}00000"
                         for m in range(start, end + 1, 5))
    return [bar.get("time") for bar in bars] == canonical


def main():
    results, errors = {}, {}
    for code in CODES:
        try:
            try:
                item = fetch_five_minute_https(code, DAY)
            except Exception as https_exc:
                try:
                    item = fetch_five_minute(code, DAY)
                except Exception as tcp_exc:
                    raise ValueError(f"https={str(https_exc)[:90]};tcp={str(tcp_exc)[:90]}") from tcp_exc
            if not item["complete_session"] or not validate_session(item, code, DAY):
                errors[code] = "invalid_or_incomplete_session:" + str(item["count"])
                continue
            results[code] = item
        except Exception as exc:
            errors[code] = str(exc)[:200]
    print(json.dumps({"date": DAY, "success": list(results), "errors": errors}, ensure_ascii=False))
    if not results:
        raise SystemExit("No complete BaoStock five-minute history; refusing to publish")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"date": DAY, "source": "verified_multi_source_5m", "stocks": results,
                               "errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
