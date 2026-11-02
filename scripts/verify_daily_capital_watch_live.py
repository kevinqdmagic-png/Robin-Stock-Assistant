#!/usr/bin/env python3
"""Fail-closed public production readback of daily accumulation watch."""
import json
import os
import time
from urllib.request import urlopen
from urllib.error import URLError
from urllib.parse import urlencode

BASE = "https://robin-stock-api-production.up.railway.app"
TARGET = "2026-11-02"
EXPECTED_CODES = {"300033", "600030", "300058", "300413", "002812"}

def verify(sha):
    with urlopen(BASE + "/health", timeout=12) as response:
        h = json.load(response)
    if h.get("build_commit") != sha:
        raise AssertionError("production_version_not_deployed:" + str(h.get("build_commit")))
    with urlopen(BASE + "/api/capital-watch?limit=10", timeout=12) as response:
        w = json.load(response)
    if not w.get("ok"):
        raise AssertionError("watch_api_error")
    latest = w.get("latest") or {}
    actual_codes = {row.get("code") for row in latest.get("candidates", [])}
    if latest.get("date") != TARGET or latest.get("status") != "completed":
        raise AssertionError("missing_20261102_completed_watch")
    if latest.get("scanned") != 110 or latest.get("valid_daily") < 100 or actual_codes != EXPECTED_CODES:
        raise AssertionError("watch_candidate_drift_or_insufficient_sources:" + str(actual_codes))
    if w.get("last_completed_trade_day") != TARGET or w.get("status") != "latest_trade_day":
        raise AssertionError("previous_trade_day_freshness_bug:" + str(w.get("status")))
    return {"status": "PRODUCTION_CAPITAL_WATCH_VERIFIED", "deployed_sha":sha,
            "watch_date":TARGET, "candidate_codes":sorted(actual_codes),
            "scanned":latest["scanned"], "valid_daily":latest["valid_daily"],
            "freshness":w["status"]}

def main():
    expected = os.environ["GITHUB_SHA"]
    for attempt in range(15):
        try:
            print(json.dumps(verify(expected), ensure_ascii=False))
            return 0
        except (URLError, TimeoutError, ValueError, AssertionError) as exc:
            print(f"NOT_YET_VERIFIED {attempt+1}: {type(exc).__name__}:{exc}",flush=True)
            if attempt < 14: time.sleep(10)
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
