"""Daily operations: test completed receipts, missing tasks and false successes."""
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from delivery_health import build_delivery_health, DELIVERY_TASKS

CN = ZoneInfo("Asia/Shanghai")
DAY = "2026-10-26"


def receipt(task, status="completed", *, analysis=True, report_id=None):
    report_id = report_id if report_id is not None else task + "-report"
    return {
        "id": task + "-run", "task_id": task, "date": DAY,
        "recorded_at": "2026-10-26T18:20:00+08:00",
        "status": status, "analysis_completed": analysis,
        "report_ids": [report_id] if report_id else [],
    }


def report(task):
    return {"id": task + "-report", "task_id": task, "date": DAY,
            "status": "completed", "report_type": "full_daily_research"}


class DeliveryHealthTests(unittest.TestCase):
    def setUp(self):
        self.tasks = {"items": [{"id": task, "enabled": True, "title": task}
                                for task in DELIVERY_TASKS]}
        self.runs = {"items": [receipt(task) for task in DELIVERY_TASKS]}
        self.reports = {"items": [report(task) for task in DELIVERY_TASKS]}
        self.after = datetime(2026, 10, 27, 8, 0, tzinfo=CN)

    def scan(self, now=None):
        return build_delivery_health(self.tasks, self.runs, self.reports,
                                     now=now or self.after, session_day=DAY)

    def test_all_six_independent_full_research_receipts_required(self):
        result = self.scan()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["verified_count"], 6)
        self.assertFalse(result["trading_strategy_validated"])

    def test_missing_dragon_tiger_cannot_be_satisfied_by_combined(self):
        self.runs["items"] = [r for r in self.runs["items"]
                              if r["task_id"] != "dragon_tiger"]
        result = self.scan()
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["unverified_task_ids"], ["dragon_tiger"])
        self.assertEqual(next(x for x in result["items"]
                              if x["task_id"] == "dragon_tiger")["status"], "missing")

    def test_partial_and_blocked_are_not_success(self):
        self.runs["items"] = [dict(r, status="partial")
                              if r["task_id"] == "volume_price" else r
                              for r in self.runs["items"]]
        self.assertEqual(self.scan()["unverified_task_ids"], ["volume_price"])

    def test_report_missing_rejects_completed_receipt(self):
        self.reports["items"] = [r for r in self.reports["items"]
                                 if r["task_id"] != "market_review"]
        result = self.scan()
        self.assertEqual(result["unverified_task_ids"], ["market_review"])
        self.assertEqual(result["items"][0]["status"], "unverified")

    def test_explicit_incomplete_analysis_fails_closed(self):
        self.runs["items"] = [dict(r, analysis_completed=False)
                              if r["task_id"] == "combined_pair" else r
                              for r in self.runs["items"]]
        self.assertIn("combined_pair", self.scan()["unverified_task_ids"])

    def test_before_audit_deadline_is_pending_not_missing(self):
        self.runs["items"] = []
        result = self.scan(datetime(2026, 10, 26, 18, 0, tzinfo=CN))
        self.assertEqual(result["status"], "pending")
        self.assertTrue(all(x["status"] == "pending" for x in result["items"]))

    def test_disabled_track_not_misreported(self):
        self.tasks["items"][0]["enabled"] = False
        result = self.scan()
        self.assertEqual(result["checked_task_count"], 5)
        self.assertNotIn("market_review", [r["task_id"] for r in result["items"]])

    def test_invalid_market_calendar_does_not_invent_date(self):
        result = build_delivery_health(self.tasks, self.runs, self.reports,
                                       now=datetime(2027, 2, 2, 10, tzinfo=CN))
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "calendar_unverified")


if __name__ == "__main__":
    unittest.main()
