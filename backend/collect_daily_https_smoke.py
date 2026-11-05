"""Independent, date-scoped HTTPS daily smoke collection for two frozen stocks."""
import json
import os
from pathlib import Path
from eastmoney_daily_https import fetch_daily_https
from collect_baostock_five_minute import default_research_day

day = os.environ.get("RESEARCH_DAY") or default_research_day()
codes = ("sz.002218", "sh.688109")
stocks, errors = {}, {}
for code in codes:
    try:
        stocks[code] = fetch_daily_https(code, day)
    except Exception as exc:
        errors[code] = str(exc)[:180]
print(json.dumps({"day": day, "verified": list(stocks), "errors": errors}))
if len(stocks) != len(codes):
    raise SystemExit("Daily HTTPS smoke incomplete; refusing to publish")
out = Path("backend/data/https_daily_smoke") / (day + ".json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"date": day, "source": "eastmoney_https_unofficial",
                           "sample_only": True, "stocks": stocks}, indent=2) + "\n")
