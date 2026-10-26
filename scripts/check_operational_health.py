#!/usr/bin/env python3
"""Scheduled fail-closed delivery check; observes only, never fabricates research."""
import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

CN = ZoneInfo("Asia/Shanghai")


def inspect(payload):
    if not isinstance(payload, dict) or not payload.get("ok"):
        return {"ok": False, "reason": "operations_delivery_unavailable", "missing": []}
    missing = list(payload.get("unverified_task_ids") or [])
    resident = payload.get("resident_intraday") or {}
    resident_bad = [x.get("task_id") for x in resident.get("items", [])
                    if x.get("research_observation_delivered") is not True]
    if not resident.get("ok"):
        resident_bad.append("resident_store_unavailable")
    return {"ok": not missing and not resident_bad,
            "reason": "all_research_evidence_present" if not missing and not resident_bad
                      else "research_delivery_incomplete",
            "research_date": payload.get("date_cn"),
            "missing": missing, "resident_failures": resident_bad,
            "source": "published_report_receipts_and_railway_resident_store",
            "orders_verified": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://robin-stock-api-production.up.railway.app")
    parser.add_argument("--output", default="daily-ops-health.json")
    args = parser.parse_args()
    try:
        with urlopen(args.base.rstrip("/") + "/api/operations/delivery", timeout=18) as r:
            payload = json.load(r)
        result = inspect(payload)
    except Exception as exc:
        result = {"ok": False, "reason": "operations_api_read_failed",
                  "error_type": type(exc).__name__, "missing": []}
    result["checked_at_cn"] = datetime.now(CN).isoformat(timespec="seconds")
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
