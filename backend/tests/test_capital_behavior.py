import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from capital_behavior import classify, archive_context
from task_center import validate_registry
import app as api

ROOT = Path(__file__).resolve().parents[1]


def bars(n=75):
    return [
        {"date": f"2026-08-{i+1:02d}" if i < 25 else f"2026-09-{i-24:02d}" if i < 55
         else f"2026-10-{i-54:02d}",
         "open": 10.0, "high": 10.2, "low": 9.8, "close": 10.0,
         "volume": 1000.0}
        for i in range(n)
    ]


# ISO dates must only sort lexically and be unique for the bar algorithm;
# generate a monotonic valid calendar series instead.
from datetime import date, timedelta


def samples(n=75):
    day0 = date(2026, 5, 1)
    data = []
    for i in range(n):
        data.append({
            "date": (day0 + timedelta(days=i)).isoformat(),
            "open": 10, "high": 10.2, "low": 9.8, "close": 10,
            "volume": 1000,
        })
    return data


class CapitalBehaviorTests(unittest.TestCase):
    def test_insufficient_bars_rejected(self):
        with self.assertRaisesRegex(ValueError, "61"):
            classify(samples(60))

    def test_no_evidence_not_pretended_to_be_real_main_force(self):
        result = classify(samples())
        self.assertFalse(result["identity_verified"])
        self.assertIsNone(result["prediction_probability"])
        self.assertEqual(result["validation"], "uncalibrated_hypothesis_not_a_trading_signal")
        self.assertEqual(result["as_of"], samples()[-1]["date"])

    def test_breakout_requires_volume_and_strong_close(self):
        data = samples()
        data[-1].update(open=10.15, low=10.0, high=11.2, close=11.15, volume=2000)
        result = classify(data)
        self.assertEqual(result["stage"], "breakout_observed")
        self.assertGreater(result["observations"]["relative_volume20"], 1.4)
        self.assertGreater(result["observations"]["close_location"], 0.65)

    def test_no_lookahead_future_bar_change(self):
        data = samples(75)
        earlier = classify(data[:70])
        data[70:] = [{**r, "open": 40, "high": 50, "low": 30, "close": 42,
                      "volume": 20000} for r in data[70:]]
        self.assertEqual(earlier, classify(data[:70]))
        self.assertNotEqual(earlier["as_of"], classify(data)["as_of"])

    def test_no_verified_volume(self):
        data = samples()
        data[-4]["volume"] = 0
        with self.assertRaisesRegex(ValueError, "volume"):
            classify(data)

    def test_archived_sample_counts_do_not_claim_auto_training(self):
        result = archive_context()
        self.assertTrue(result["research_history_available"])
        self.assertFalse(result["automatically_trained_on_archive"])
        self.assertFalse(result["capital_model_uses_historical_results_to_fit"])
        self.assertIn("low_position", result["sample_counts"])

    def test_api_rejects_bad_code(self):
        self.assertEqual(api.capital_behavior("../../bad")["status"], "invalid_code")

    def test_api_uses_completed_bars(self):
        with patch("app._get_daily", return_value=(samples(), "synthetic_test", [])), patch(
                "app.completed_bars", side_effect=lambda x: x):
            result = api.capital_behavior("002472")
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "synthetic_test")

    def test_separate_app_tasks_do_not_consume_daily_dependencies(self):
        doc = json.loads((ROOT / "data" / "tasks.json").read_text(encoding="utf-8"))
        validate_registry(doc)
        by_id = {r["id"]: r for r in doc["items"]}
        for key in ("low_position", "dragon_tiger", "capital_behavior"):
            self.assertEqual(by_id[key]["execution_mode"], "app_only_on_demand")
            self.assertFalse(by_id[key]["enabled"])
        self.assertFalse(by_id["low_dragon"]["enabled"])
        for key in ("low_position", "dragon_tiger", "capital_behavior"):
            self.assertNotIn(key, by_id["combined_pair"]["dependencies"])
            self.assertNotIn(key, by_id["combined_pair"]["executes_missing_tasks"])


if __name__ == "__main__":
    unittest.main()
