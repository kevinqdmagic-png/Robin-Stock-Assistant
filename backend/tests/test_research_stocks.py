import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as api
from research_archive import load_document
from research_stocks import catalog, validate_catalog, verify_catalog_history


class ResearchStocksTests(unittest.TestCase):
    def test_original_core_is_preserved_and_comparison_is_separate(self):
        document = catalog()
        self.assertEqual({s["code"] for s in document["items"] if s["role"] == "core"},
                         {"300450", "603662", "688498"})
        ding = next(s for s in document["items"] if s["code"] == "688668")
        self.assertEqual(ding["role"], "comparison")

    def test_stock_reason_is_available_without_market_provider(self):
        with patch("app._get_daily") as daily, patch("app.requests.get") as provider:
            result = api.research_stock("300450")
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(len(result["stock"]["history"]), 2)
        daily.assert_not_called()
        provider.assert_not_called()

    def test_stock_links_preserve_both_original_and_followup(self):
        result = api.research(code="688498")
        self.assertTrue({"high-elasticity-2026-09-30-original", "high-elasticity-2026-10-01-rescreen"}
                        .issubset({r["id"] for r in result["items"]}))
        filtered = api.research(code="688498", date="2026-10-01", task="high_elasticity_once")
        self.assertTrue(filtered["ok"])
        # Later reports may be appended on the same date without replacing
        # the preserved legacy follow-up. Verify filtering, not a frozen count.
        filtered_ids = {r["id"] for r in filtered["items"]}
        self.assertIn("high-elasticity-2026-10-01-rescreen", filtered_ids)
        self.assertNotIn("high-elasticity-2026-09-30-original", filtered_ids)
        for report in filtered["items"]:
            self.assertEqual(report["date"], "2026-10-01")
            self.assertEqual(report["track"], "high_elasticity")
            if report.get("task_id"):
                self.assertEqual(report["task_id"], "high_elasticity_once")

    def test_invalid_or_unknown_stock_never_receives_another_stock_reason(self):
        self.assertFalse(api.research_stock("../300450")["ok"])
        result = api.research_stock("999999")
        self.assertTrue(result["ok"])
        self.assertIsNone(result["stock"])
        self.assertEqual(api.research(code="999999")["items"], [])

    def test_research_catalog_does_not_create_daily_performance_records(self):
        before = copy.deepcopy(load_document("recommendations.json"))
        self.assertTrue(api.research_stocks()["items"])
        self.assertEqual(load_document("recommendations.json"), before)

    def test_deleted_or_changed_historical_reason_is_rejected(self):
        before = catalog()
        for mutation in ("change", "delete"):
            after = copy.deepcopy(before)
            if mutation == "change":
                after["items"][0]["history"][0]["reason"] = "new buy call"
            else:
                after["items"][0]["history"].pop(0)
            with self.assertRaises(ValueError):
                verify_catalog_history(before, after)

    def test_new_episode_can_be_appended_without_overwriting_original(self):
        before = catalog()
        after = copy.deepcopy(before)
        entry = copy.deepcopy(after["items"][0]["history"][-1])
        entry["id"] += "-new"
        after["items"][0]["history"].append(entry)
        verify_catalog_history(before, after)

    def test_wrong_report_link_and_duplicate_code_are_rejected(self):
        reports = load_document("research.json")
        wrong = copy.deepcopy(catalog())
        wrong["items"][0]["history"][0]["report_ids"] = ["volume-price-2026-10-01-audit"]
        with self.assertRaises(ValueError):
            validate_catalog(wrong, reports)
        duplicate = copy.deepcopy(catalog())
        duplicate["items"].append(copy.deepcopy(duplicate["items"][0]))
        with self.assertRaises(ValueError):
            validate_catalog(duplicate, reports)


if __name__ == "__main__":
    unittest.main()
