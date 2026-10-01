import copy
import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics import backtest_daily, breakout_signals, recommendation_performance, clean_bars
from research_archive import validate_document, verify_append_only, archive_page
from trading_calendar import CN_TZ, completed_bars, session_state


def bar(i, open=10, close=10, high=10.2, low=9.8, volume=100):
    return {"date": (datetime(2026, 8, 1) + timedelta(days=i)).date().isoformat(),
            "open": open, "close": close, "high": high, "low": low, "volume": volume}


def fixture():
    return [bar(i) for i in range(20)] + [
        bar(20, 10.1, 11, 11.2, 10, 200),
        bar(21, 11.1, 11.2, 11.4, 10.9),
        bar(22, 11.3, 11.3, 99, 1),
    ]


class DailyValidationTests(unittest.TestCase):
    def test_t1_and_exit_day_extremes(self):
        result = backtest_daily(fixture(), "600000", holding=1, cost_bps=20)
        trade = result["trades"][0]
        self.assertEqual(trade["entry_date"], fixture()[21]["date"])
        self.assertEqual(trade["exit_date"], fixture()[22]["date"])
        self.assertAlmostEqual(trade["mfe_pct"], (11.4 / 11.1 - 1) * 100, places=3)
        self.assertAlmostEqual(trade["mae_pct"], (10.9 / 11.1 - 1) * 100, places=3)
        self.assertAlmostEqual(trade["gross_pct"] - trade["net_pct"], .2, places=2)

    def test_future_prices_cannot_change_prior_signal(self):
        a = fixture()
        b = copy.deepcopy(a)
        b[22] = bar(22, 90, 100, 100, 90, 10000)
        first = breakout_signals(a)[1][0]
        self.assertEqual(first, breakout_signals(b)[1][0])

    def test_pending_not_counted_as_loss_or_removed(self):
        report = backtest_daily(fixture()[:21], "600000")
        self.assertEqual(report["signal_count"], 1)
        self.assertEqual(report["pending_count"], 1)
        self.assertEqual(report["completed_count"], 0)
        self.assertIsNone(report["stats"]["win_rate_pct"])

    def test_limit_up_buy_unavailable(self):
        rows = fixture()
        rows[21] = bar(21, 12.1, 12.1, 12.1, 12.1)
        report = backtest_daily(rows, "600000", holding=1)
        self.assertEqual(report["trades"][0]["status"], "entry_unavailable")
        self.assertEqual(report["unavailable_count"], 1)

    def test_limit_down_exit_deferred(self):
        rows = fixture()
        rows[22] = bar(22, 10.08, 10.08, 10.08, 10.08)
        rows.append(bar(23, 10.2, 10.3, 10.4, 10.1))
        report = backtest_daily(rows, "600000", holding=1)
        trade = report["trades"][0]
        self.assertEqual(trade["exit_date"], rows[23]["date"])
        self.assertEqual(trade["delayed_exit_sessions"], 1)

    def test_duplicate_or_invalid_candle_rejected(self):
        with self.assertRaises(ValueError):
            clean_bars([bar(0), bar(0)])
        with self.assertRaises(ValueError):
            clean_bars([bar(0, high=1)])
        with self.assertRaises(ValueError):
            clean_bars([bar(0, close=float("nan"))])

    def test_missing_reference_cannot_fabricate_performance(self):
        result = recommendation_performance({"date": "2026-09-29", "reference_price": None}, fixture())
        self.assertEqual(result["status"], "needs_evidence")
        self.assertEqual(result["points"], [])

    def test_performance_preserves_unmatured_horizons(self):
        rows = fixture()
        record = {"date": rows[20]["date"], "reference_price": 11, "published_at": "2026-08-21T16:00:00+08:00",
                  "provenance": "contemporaneous"}
        result = recommendation_performance(record, rows)
        self.assertEqual(result["status"], "price_observation")
        self.assertEqual(len(result["points"]), 6)
        self.assertEqual(result["points"][0]["status"], "observed")
        self.assertEqual(result["points"][1]["status"], "pending")

    def test_corporate_action_requires_review(self):
        rows = fixture()
        rows[21] = dict(bar(21, 5.5, 5.5, 5.6, 5.4), pct=0)
        record = {"date": rows[20]["date"], "reference_price": 11, "published_at": "2026-08-21T16:00:00+08:00",
                  "provenance": "contemporaneous"}
        self.assertEqual(recommendation_performance(record, rows)["status"], "corporate_action_review")


class CalendarTests(unittest.TestCase):
    def test_national_holiday_not_live(self):
        state = session_state(datetime(2026, 10, 1, 10, tzinfo=CN_TZ))
        self.assertEqual(state["code"], "closed")
        self.assertFalse(state["is_live"])

    def test_first_reopening_and_weekend(self):
        reopening = session_state(datetime(2026, 10, 8, 10, tzinfo=CN_TZ))
        self.assertTrue(reopening["is_live"])
        self.assertEqual(reopening["date"], "2026-10-08")
        self.assertFalse(session_state(datetime(2026, 10, 10, 10, tzinfo=CN_TZ))["is_live"])

    def test_unverified_calendar_fails_closed(self):
        self.assertEqual(session_state(datetime(2027, 1, 4, 10, tzinfo=CN_TZ))["code"], "unknown")

    def test_incomplete_daily_candle_excluded(self):
        rows = [{"date": "2026-09-29"}, {"date": "2026-09-30"}]
        self.assertEqual(len(completed_bars(rows, datetime(2026, 9, 30, 14, tzinfo=CN_TZ))), 1)
        self.assertEqual(len(completed_bars(rows, datetime(2026, 9, 30, 15, 10, tzinfo=CN_TZ))), 2)


class ArchiveTests(unittest.TestCase):
    def test_original_recommendation_may_not_change(self):
        before = {"items": [{"id": "a", "date": "2026-09-30", "code": "600000", "reference_price": 10}]}
        after = copy.deepcopy(before)
        after["items"][0]["results"] = [{"date": "2026-10-08", "close_pct": -5}]
        verify_append_only(before, after, "recommendations")
        after["items"][0]["reference_price"] = 8
        with self.assertRaises(ValueError):
            verify_append_only(before, after, "recommendations")

    def test_failure_sample_may_not_be_deleted(self):
        with self.assertRaises(ValueError):
            verify_append_only({"items": [{"id": "failed"}]}, {"items": []}, "recommendations")

    def test_date_track_and_pagination(self):
        payload = {"items": [{"id": str(i), "date": "2026-09-30", "track": "volume_price",
                              "title": "sample", "body": "facts"} for i in range(3)] +
                            [{"id": "other", "date": "2026-09-29", "track": "market_review", "body": "facts"}]}
        with patch("research_archive.load_document", return_value=payload):
            page = archive_page("volume_price", "2026-09-30", offset=1, limit=1)
        self.assertEqual(page["total"], 3)
        self.assertEqual(len(page["items"]), 1)
        self.assertTrue(page["has_more"])

    def test_recorded_outcomes_are_append_only(self):
        before = {"items": [{"id": "a", "results": [
            {"as_of": "2026-10-08", "horizon": 1, "close_pct": -5},
            {"as_of": "2026-10-09", "horizon": 2, "close_pct": 2}]}]}
        after = copy.deepcopy(before)
        after["items"][0]["results"].append({"as_of": "2026-10-12", "horizon": 3, "close_pct": 1})
        verify_append_only(before, after, "recommendations")
        for changed in ([], list(reversed(before["items"][0]["results"])),
                        [{"as_of": "2026-10-08", "horizon": 1, "close_pct": 5}]):
            with self.subTest(results=changed), self.assertRaises(ValueError):
                altered = copy.deepcopy(before)
                altered["items"][0]["results"] = changed
                verify_append_only(before, altered, "recommendations")

    def test_original_strategy_label_may_not_change(self):
        before = {"items": [{"id": "a", "strategy": "combined_limitup_watch"}]}
        after = copy.deepcopy(before)
        after["items"][0]["strategy"] = "different_model"
        with self.assertRaises(ValueError):
            verify_append_only(before, after, "recommendations")

    def test_versioned_data_documents(self):
        root = Path(__file__).resolve().parents[1] / "data"
        for name, kind in (("research.json", "research"), ("recommendations.json", "recommendations")):
            validate_document(json.loads((root / name).read_text()), kind)


if __name__ == "__main__":
    unittest.main()
