#!/usr/bin/env python3
"""Verify T2026-11-02 recovery documents are genuinely readable from production."""
import json
import os
import time
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

BASE = "https://robin-stock-api-production.up.railway.app"
DAY = "2026-11-02"
PREFIX = "recovery-audit-20261102-20261103"
TASKS = ("market_review", "volume_price", "low_position", "dragon_tiger", "combined_pair", "limitup_single")


def read(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urlencode(params)
    with urlopen(url, timeout=12) as response:
        data = json.load(response)
    if data.get("ok") is not True:
        raise AssertionError(f"backend responded not-ok to {path}: {data.get('status')}")
    return data


def check(expected_sha):
    health = read("/health")
    actual_sha = health.get("build_commit")
    if actual_sha != expected_sha:
        raise AssertionError(f"production_sha_mismatch: expected={expected_sha}, got={actual_sha}")
    reports = read("/api/research", {"date": DAY, "limit": 100})
    found = {r.get("id"): r for r in reports.get("items", [])}
    result = {"build_sha": actual_sha, "report_ids": [], "blocked_receipts": []}
    for task in TASKS:
        report_id = f"{PREFIX}-{task}-report"
        row = found.get(report_id)
        if not row:
            raise AssertionError(f"report_missing:{report_id}")
        if not (row.get("date") == DAY and row.get("task_id") == task
                and row.get("status") == "blocked"
                and row.get("analysis_completed") is False
                and row.get("eligible_for_integrated_research") is False):
            raise AssertionError(f"report_misclassified:{report_id}")
        receipts = read("/api/task-runs", {"task": task, "limit": 100})
        receipt_id = f"{PREFIX}-{task}-receipt"
        receipt = next((x for x in receipts.get("items", []) if x.get("id") == receipt_id), None)
        if not receipt or receipt.get("status") != "blocked" or report_id not in receipt.get("report_ids", []):
            raise AssertionError(f"blocked_receipt_missing_or_inaccurate:{receipt_id}")
        result["report_ids"].append(report_id)
        result["blocked_receipts"].append(receipt_id)
    # Also insist that the later 164/166 real D-day OHLCV observations survived
    # production archive loading, without laundering them into a full study.
    price_id = "recovery-frozen-daybars-20261102-v1"
    price = found.get(price_id)
    if not price or price.get("status") != "partial" or price.get("recovered_unique") != 164 or price.get("analysis_completed") is not False:
        raise AssertionError("frozen_universe_price_evidence_missing_or_misclassified")
    price_receipts = read("/api/task-runs", {"task": "volume_price", "limit": 100})
    price_receipt = next((x for x in price_receipts.get("items", []) if x.get("id") == "recovery-frozen-daybars-20261102-receipt"), None)
    if not price_receipt or price_receipt.get("status") != "partial":
        raise AssertionError("frozen_universe_price_receipt_missing")
    daily = read("/api/operations/delivery")
    if daily.get("date_cn") != DAY:
        raise AssertionError("wrong_latest_completed_trading_date")
    if daily.get("verified_count") != 0 or set(daily.get("unverified_task_ids", [])) != set(TASKS):
        raise AssertionError("delivery_health_false_full_completion:" +
                             json.dumps({"verified_count": daily.get("verified_count"),
                                         "missing": daily.get("unverified_task_ids")}))
    result["price_observation"] = price_id
    result["price_verified_count"] = price["recovered_unique"]
    result["delivery_verified_count"] = daily["verified_count"]
    result["delivery_missing"] = daily["unverified_task_ids"]
    return result


def main():
    expected_sha = os.environ.get("GITHUB_SHA", "")
    if len(expected_sha) != 40:
        raise SystemExit("GITHUB_SHA must be present and full length")
    failure = None
    for attempt in range(12):
        try:
            result = check(expected_sha)
            print(json.dumps({"status": "PRODUCTION_REPORT_READBACK_VERIFIED", **result}, ensure_ascii=False))
            return 0
        except (URLError, HTTPError, ValueError, AssertionError, TimeoutError) as exc:
            failure = f"{type(exc).__name__}: {exc}"
            print(f"ATTEMPT_{attempt+1}_NOT_YET_VERIFIED: {failure}", flush=True)
            if attempt < 11:
                time.sleep(10)
    print(json.dumps({"status": "BLOCKED", "reason": failure}, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
