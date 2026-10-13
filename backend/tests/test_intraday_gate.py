"""Intraday gate: never produce an unsupported recommendation."""
import importlib.util
from datetime import datetime
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

script = Path(__file__).resolve().parents[2] / "scripts" / "run_intraday_research.py"
spec = importlib.util.spec_from_file_location("run_intraday_research", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
TZ = ZoneInfo("Asia/Shanghai")


class IntradayGateTests(unittest.TestCase):
    def test_early_slot_with_no_verified_feed_has_no_stock(self):
        result = module.evaluate("early_pair", datetime(2026, 10, 13, 9, 50, tzinfo=TZ))
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["recommendations"], [])

    def test_late_slot_with_no_verified_feed_has_no_stock(self):
        result = module.evaluate("late_pair", datetime(2026, 10, 13, 14, 40, tzinfo=TZ))
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["recommendations"], [])

    def test_holiday_is_skipped(self):
        result = module.evaluate("early_pair", datetime(2026, 10, 5, 9, 50, tzinfo=TZ))
        self.assertEqual(result["status"], "skipped")

    def test_delayed_execution_is_not_backdated(self):
        result = module.evaluate("early_pair", datetime(2026, 10, 13, 10, 30, tzinfo=TZ))
        self.assertEqual(result["status"], "skipped")

    def test_invalid_slot_rejected(self):
        with self.assertRaises(ValueError):
            module.evaluate("unregistered", datetime(2026, 10, 13, 9, 50, tzinfo=TZ))
