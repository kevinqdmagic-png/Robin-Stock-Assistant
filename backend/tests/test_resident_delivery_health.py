"""Resident intraday audit uses its persistent store, not a GitHub report."""
from datetime import datetime
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from delivery_health import resident_intraday_health

CN = ZoneInfo("Asia/Shanghai")


def store(status="observed", day="2026-10-26", ok=True, writable=True):
    return {"ok": ok, "storage": "railway_persistent_volume",
            "store_writable": writable,
            "latest": {"date": day, "status": status,
                       "started_at": day + "T14:40:01+08:00"}}


class ResidentDeliveryTests(unittest.TestCase):
    def test_both_slots_separately_verified(self):
        def mock(slot):
            return store(status="no_signal" if slot == "early_pair" else "observed")
        result = resident_intraday_health(
            now=datetime(2026, 10, 26, 15, 30, tzinfo=CN), provider=mock)
        self.assertEqual(result["status"], "complete")
        self.assertTrue(all(r["research_observation_delivered"] for r in result["items"]))
        self.assertFalse(result["actual_order_fills_verified"])

    def test_absent_observation_is_missing_after_window(self):
        def mock(slot):
            return store(day="2026-10-23")
        result = resident_intraday_health(
            now=datetime(2026, 10, 26, 15, 30, tzinfo=CN), provider=mock)
        self.assertTrue(all(x["status"] == "missing" for x in result["items"]))

    def test_before_slot_scheduled_is_pending(self):
        result = resident_intraday_health(
            now=datetime(2026, 10, 26, 9, 20, tzinfo=CN),
            provider=lambda slot: store(day="2026-10-23"))
        self.assertEqual(result["items"][0]["status"], "pending")

    def test_broken_storage_not_success(self):
        result = resident_intraday_health(
            now=datetime(2026, 10, 26, 15, 30, tzinfo=CN),
            provider=lambda slot: store(writable=False))
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["items"][0]["status"], "store_unavailable")


if __name__ == "__main__":
    unittest.main()
