"""Regression tests for full-delivery audit: addenda and partial snapshots cannot pass."""
import json
from datetime import datetime
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_full_research_delivery import REQUIRED, audit, latest_closed_session

CN = ZoneInfo("Asia/Shanghai")
DAY = "2026-10-30"


def archive():
    reports, runs = [], []
    for task in REQUIRED:
        rid = f"{task}-{DAY}-close-v1"
        reports.append({
            "id": rid, "task_id": task, "date": DAY, "status": "completed",
            "analysis_completed": True, "eligible_for_integrated_research": task != "limitup_single",
            "body": "Original full research with underlying source evidence",
            "sources": ["https://example.org/source"],
        })
        runs.append({
            "id": f"{task}-{DAY}-receipt", "task_id": task, "date": DAY,
            "status": "completed", "trigger": "scheduled", "report_ids": [rid],
        })
    return {"items": reports}, {"items": runs}


class FullDeliveryAuditTest(unittest.TestCase):
    def test_full_set_passes(self):
        reports, runs = archive()
        result = audit(DAY, reports, runs, datetime(2026, 10, 30, 20, 20, tzinfo=CN))
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["status"], "full_reports_in_repository_verified")

    def test_supplement_cannot_replace_original(self):
        reports, runs = archive()
        reports["items"][-1]["id"] += "-supplement"
        runs["items"][-1]["report_ids"] = [reports["items"][-1]["id"]]
        result = audit(DAY, reports, runs, datetime(2026, 10, 30, 20, 20, tzinfo=CN))
        self.assertEqual(result["missing"], ["limitup_single"])

    def test_partial_and_waiting_are_not_success(self):
        reports, runs = archive()
        reports["items"][0]["eligible_for_integrated_research"] = False
        runs["items"][1]["status"] = "waiting"
        result = audit(DAY, reports, runs, datetime(2026, 10, 30, 20, 20, tzinfo=CN))
        self.assertEqual(result["missing"], ["market_review", "volume_price"])

    def test_prior_session_uses_exchange_calendar(self):
        actual = latest_closed_session(datetime(2026, 11, 3, 7, 0, tzinfo=CN))
        self.assertEqual(actual, "2026-11-02")
        holiday = latest_closed_session(datetime(2026, 10, 6, 20, 30, tzinfo=CN))
        self.assertEqual(holiday, "2026-09-30")


if __name__ == "__main__":
    unittest.main()
