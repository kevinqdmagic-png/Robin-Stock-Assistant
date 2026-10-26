"""Delivery alert policy; never treats partial reports or resident gaps as success."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ops_health", ROOT / "scripts/check_operational_health.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def payload():
    return {"ok": True, "date_cn": "2026-10-26", "status": "complete",
            "unverified_task_ids": [], "resident_intraday": {
                "ok": True, "items": [
                    {"task_id": "early_pair", "research_observation_delivered": True},
                    {"task_id": "late_pair", "research_observation_delivered": True}] }}


class OperationsMonitorTests(unittest.TestCase):
    def test_valid_deliveries_pass(self):
        self.assertTrue(module.inspect(payload())["ok"])

    def test_missing_dragon_tiger_fails(self):
        row = payload()
        row["unverified_task_ids"] = ["dragon_tiger"]
        self.assertFalse(module.inspect(row)["ok"])
        self.assertEqual(module.inspect(row)["missing"], ["dragon_tiger"])

    def test_resident_store_outage_fails(self):
        row = payload()
        row["resident_intraday"]["ok"] = False
        self.assertIn("resident_store_unavailable",
                      module.inspect(row)["resident_failures"])

    def test_partial_resident_fails(self):
        row = payload()
        row["resident_intraday"]["items"][0]["research_observation_delivered"] = False
        self.assertFalse(module.inspect(row)["ok"])

    def test_http_200_without_ok_is_not_success(self):
        self.assertFalse(module.inspect({"ok": False})["ok"])
        self.assertFalse(module.inspect({"status": "complete"})["ok"])


if __name__ == "__main__":
    unittest.main()
