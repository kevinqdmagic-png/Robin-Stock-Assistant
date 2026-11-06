import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_statistics import dual_statistics, intraday_statistics


def event(strategy, number, value, **changes):
    return {"family": "test", "slot": "late_pair", "basis": "quote_to_close",
            "market_regime": "unknown", "horizon": 1, "strategy": strategy, "version": "v1",
            "code": str(600000 + number), "anchor_date": "2026-10-29",
            "status": "observed", "return_pct": value, **changes}


class ResearchStatisticsTests(unittest.TestCase):
    def test_high_frequency_and_high_payoff_have_separate_rankings(self):
        events = [event("frequent", i, v) for i, v in enumerate([1, 1, 1, -8])]
        events += [event("payoff", i, v) for i, v in enumerate([10, -1, -1, -1])]
        result = dual_statistics(events)
        rows = {r["strategy"]: r for r in result["groups"]}
        self.assertEqual(rows["frequent"]["positive_price_rate_pct"], 75)
        self.assertEqual(rows["frequent"]["mean_price_change_pct"], -1.25)
        self.assertEqual(rows["payoff"]["mean_price_change_pct"], 1.75)
        self.assertEqual(result["rankings"][0]["by_positive_rate"][0], rows["frequent"]["id"])
        self.assertEqual(result["rankings"][0]["by_mean_return"][0], rows["payoff"]["id"])
        self.assertIsNone(result["actual_trade_win_rate_pct"])
        self.assertFalse(result["rankings"][0]["ranking_is_verified_advantage"])

    def test_horizons_windows_versions_and_baselines_are_not_pooled(self):
        rows = [event("one", 1, 2), event("one", 2, -3, horizon=5),
                event("one", 3, 9, slot="early_pair"), event("one", 4, 5, basis="close_proxy"),
                event("one", 5, 1, version="v2")]
        result = dual_statistics(rows)
        self.assertEqual(len(result["groups"]), 5)
        self.assertEqual(len(result["rankings"]), 4)
        self.assertTrue(all(r["sample_count"] == 1 for r in result["groups"]))

    def test_duplicate_conflicting_pending_and_nonfinite_observations_are_visible(self):
        one = event("one", 1, 2)
        result = dual_statistics([one, dict(one), event("one", 2, 1), event("one", 2, 9),
                                  event("one", 3, None, status="pending"),
                                  event("one", 4, float("nan"))])
        row = result["groups"][0]
        self.assertEqual(row["sample_count"], 1)
        self.assertEqual(row["duplicates_excluded"], 2)
        self.assertEqual(row["conflicting_events_excluded"], 2)
        self.assertEqual(row["status_counts"]["pending"], 1)
        self.assertEqual(row["expected_event_count"], 4)
        self.assertIsNone(row["payoff_ratio"])

    def test_intraday_close_observations_cannot_invent_path_drawdown_or_trade_profit(self):
        result = intraday_statistics([{"task_id": "early_pair", "cohort": "low_chase",
            "model_version": "v2", "code": "600000", "signal_date": "2026-10-29",
            "horizon": 1, "price_change_from_quote_pct": -3}])
        row = result["groups"][0]
        self.assertIsNone(row["worst_path_mae_pct"])
        self.assertIsNone(row["actual_net_return_pct"])
        self.assertFalse(row["minimum_sample_floor_met"])


if __name__ == "__main__":
    unittest.main()
