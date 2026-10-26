"""Daily research deadline audit is evidence-based, not a trade generator."""
import importlib.util
from datetime import datetime
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
spec = importlib.util.spec_from_file_location("audit", ROOT / "scripts/audit_task_deliveries.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
CN = ZoneInfo("Asia/Shanghai")


class DeadlineAuditTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 14, 20, 45, tzinfo=CN)
        self.tasks = {"items": [{"id": "market_review", "enabled": True},
                                {"id": "quant_research", "enabled": False},
                                {"id": "early_pair", "enabled": True}]}
        self.ledger = {"schema_version": 1, "items": []}
        self.reports = {"items": []}

    def test_missing_runs_become_blocked_receipts_not_completion(self):
        updated, s = audit.audit_day(self.ledger, self.tasks, self.reports, self.now)
        self.assertEqual(len(s["created"]), 2)
        self.assertEqual(s["unfulfilled"], ["market_review", "early_pair"])
        self.assertTrue(all(row["status"] == "blocked" for row in updated["items"]))
        self.assertTrue(all(not row["report_ids"] for row in updated["items"]))

    def test_dragon_tiger_missing_delivery_is_audited(self):
        self.tasks["items"].append({"id": "dragon_tiger", "enabled": True})
        updated, status = audit.audit_day(self.ledger, self.tasks, self.reports, self.now)
        self.assertIn("dragon_tiger", status["unfulfilled"])
        receipt = next(row for row in updated["items"] if row["task_id"] == "dragon_tiger")
        self.assertEqual(receipt["status"], "blocked")
        self.assertFalse(receipt["analysis_completed"])

    def test_idempotent_audit(self):
        first, _ = audit.audit_day(self.ledger, self.tasks, self.reports, self.now)
        second, s = audit.audit_day(first, self.tasks, self.reports, self.now)
        self.assertEqual(first, second)
        self.assertEqual(s["created"], [])

    def test_reject_before_deadline(self):
        with self.assertRaises(ValueError):
            audit.audit_day(self.ledger, self.tasks, self.reports,
                            datetime(2026, 10, 14, 20, 39, tzinfo=CN))

    def test_disabled_quant_not_required(self):
        updated, _ = audit.audit_day(self.ledger, self.tasks, self.reports, self.now)
        self.assertNotIn("quant_research", [r["task_id"] for r in updated["items"]])

    def test_complete_receipt_with_report_passes(self):
        self.reports["items"] = [{"id": "r1", "task_id": "market_review", "date": "2026-10-14"}]
        self.ledger["items"] = [{"id": "old", "run_id": "test-real-run",
                                 "task_id": "market_review", "date": "2026-10-14",
                                 "trigger": "scheduled", "status": "completed",
                                 "started_at": "2026-10-14T18:00:00+08:00",
                                 "completed_at": "2026-10-14T18:30:00+08:00",
                                 "recorded_at": "2026-10-14T18:35:00+08:00",
                                 "report_ids": ["r1"]}]
        updated, s = audit.audit_day(self.ledger, self.tasks, self.reports, self.now)
        self.assertEqual(s["unfulfilled"], ["early_pair"])
        self.assertEqual(len(updated["items"]), 2)


if __name__ == "__main__":
    unittest.main()
