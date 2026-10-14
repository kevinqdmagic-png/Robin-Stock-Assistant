"""Intraday automation receipts are explicit and immutable."""
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
spec = importlib.util.spec_from_file_location("publisher", ROOT / "scripts/publish_intraday_outcome.py")
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
TZ = ZoneInfo("Asia/Shanghai")


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 14, 10, 11, tzinfo=TZ)
        self.outcome = {
            "task_id": "early_pair", "market_date": "2026-10-14",
            "checked_at": "2026-10-14T10:10:02+08:00",
            "status": "insufficient_evidence", "reason": "no_live_feed_supplied",
            "market_data_verified": False, "recommendations": [],
        }

    def test_blocked_receipt_without_invented_pick(self):
        updated, changed = publisher.record_outcome({"items": []}, self.outcome, "38499593332", self.now)
        self.assertTrue(changed)
        event = updated["items"][0]
        self.assertEqual(event["status"], "blocked")
        self.assertFalse(event["analysis_completed"])
        self.assertEqual(event["recommendation_ids"], [])
        self.assertIn("10:10:02", event["summary"])

    def test_idempotent_when_replayed(self):
        ledger, _ = publisher.record_outcome({"items": []}, self.outcome, "38499593332", self.now)
        unchanged, changed = publisher.record_outcome(ledger, self.outcome, "38499593332", self.now)
        self.assertFalse(changed)
        self.assertEqual(unchanged, ledger)

    def test_refuse_unverified_completion(self):
        with self.assertRaises(ValueError):
            publisher.record_outcome({"items": []},
                                     {**self.outcome, "status": "completed"},
                                     "38499593332", self.now)

    def test_late_trigger_marked_failure(self):
        outcome = {**self.outcome, "status": "skipped",
                   "reason": "outside_intraday_execution_window"}
        row = publisher.record_outcome({"items": []}, outcome, "38499593332", self.now)[0]["items"][0]
        self.assertEqual(row["status"], "failed")

    def test_modified_registry_does_not_depend_on_cancelled_quant_task(self):
        import json
        tasks = json.loads((ROOT / "backend/data/tasks.json").read_text(encoding="utf-8"))["items"]
        index = {t["id"]: t for t in tasks}
        self.assertNotIn("quant_research", index["combined_pair"]["dependencies"])
        self.assertTrue(index["early_pair"]["enabled"])
        self.assertEqual(index["early_pair"]["execution_mode"], "railway_resident_partial_observation")


if __name__ == "__main__":
    unittest.main()
