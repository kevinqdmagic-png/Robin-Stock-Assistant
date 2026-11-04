"""Collect verified BaoStock five-minute history to a dated JSON artifact."""
import json
import os
from datetime import date
from pathlib import Path
from baostock_five_minute import fetch_five_minute

DAY = os.environ.get("RESEARCH_DAY", date.today().isoformat())
OUT = Path("backend/data/baostock_five_minute") / (DAY + ".json")
CODES = ("sz.002218", "sh.688109")


def main():
    results, errors = {}, {}
    for code in CODES:
        try:
            item = fetch_five_minute(code, DAY)
            if not item["complete_session"]:
                errors[code] = "incomplete_session:" + str(item["count"])
                continue
            results[code] = item
        except Exception as exc:
            errors[code] = str(exc)[:200]
    print(json.dumps({"date": DAY, "success": list(results), "errors": errors}, ensure_ascii=False))
    if not results:
        raise SystemExit("No complete BaoStock five-minute history; refusing to publish")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"date": DAY, "source": "baostock", "stocks": results,
                               "errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
