"""Freeze dates, keep proxy cohorts separate, verify chronological forward outcomes."""
from datetime import date, datetime, timedelta
import sys
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from learning_loop import build_snapshot, is_session
from low_position_learning import extract_observations, horizon_statistics

CN = ZoneInfo("Asia/Shanghai")


def report(report_id="r1", published="2026-09-24T17:17:00+08:00",
           day="2026-09-24", code="600001"):
    return {
        "id": report_id, "date": day, "task_id": "low_position",
        "published_at": published,
        "provenance": "contemporaneous_observation_not_recommendation",
        "shape_method_version": "low_position_shape_proxy_v1",
        "validation_status": "partial_not_tradeable",
        "analysis_completed": False,
        "signal_observations": [{
            "code": code, "date": day, "close_qfq": 10.12,
            "day_pct_proxy": 1.0, "relative_volume20": 2.1,
            "close_location": .8, "distance_ma20_pct": 3.1,
            "distance_60d_low_pct": 15.2,
            "source": "tencent_qfq_daily",
            "eligible_for_trading": False,
        }],
    }


def bars():
    d = date(2026, 5, 1)
    result = []
    while d <= date(2026, 10, 15):
        if is_session(d):
            result.append({
                "date": d.isoformat(), "open": 10, "close": 10,
                "high": 10.3, "low": 9.7, "volume": 15000,
            })
        d += timedelta(days=1)
    return result


class LowPositionForwardTests(unittest.TestCase):
    def test_retry_and_multiple_reports_do_not_duplicate_same_signal(self):
        records = [report("later", "2026-09-24T19:17:00+08:00"),
                   report("first", "2026-09-24T17:17:00+08:00"),
                   report("second", "2026-09-24T18:17:00+08:00")]
        found = extract_observations(records, date(2026, 10, 15))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["signal_source_report_id"], "first")
        self.assertFalse(found[0]["is_recommendation"])
        self.assertEqual(found[0]["frozen_features"]["relative_volume20"], 2.1)

    def test_old_method_or_backfill_not_included_in_forward_cohort(self):
        backfill = dict(report(), provenance="manual_backfill")
        expired = report("old", day="2026-07-01", published="2026-07-01T17:17:00+08:00")
        wrong_method = dict(report("wrong"), shape_method_version="future_unknown_version")
        future = report("future", day="2026-10-16", published="2026-10-16T17:17:00+08:00")
        late = report("late", published="2026-09-25T09:00:00+08:00")
        early = report("early", published="2026-09-24T09:50:00+08:00")
        self.assertEqual(extract_observations([backfill, expired, wrong_method, future, late, early],
                                              date(2026, 10, 15)), [])

    def test_forward_proxy_outcomes_are_not_fake_fills_or_recommendation_wins(self):
        frozen = extract_observations([report()], date(2026, 10, 15))
        calls = []
        def provider(code):
            calls.append(code)
            return bars(), "synthetic_unadjusted_daily", []
        snap = build_snapshot([], provider, now=datetime(2026, 10, 15, 18, tzinfo=CN),
                              low_position_observations=frozen)
        self.assertEqual(calls, ["600001"])
        self.assertEqual(snap["sample_count"], 0)
        self.assertEqual(snap["evaluations"], [])
        self.assertEqual(snap["low_position_summary"]["sample_count"], 1)
        self.assertEqual(snap["low_position_summary"]["horizons"]["2"]["matured_count"], 1)
        self.assertEqual(snap["low_position_summary"]["horizons"]["10"]["matured_count"], 0)
        self.assertEqual(snap["low_position_summary"]["horizons"]["30"]["matured_count"], 0)
        self.assertIn(30, [p["h"] for p in snap["low_position_evaluations"][0]["horizons"]])
        self.assertFalse(snap["low_position_summary"]["selection_rules_changed"])
        self.assertFalse(snap["trade_execution_verified"])
        low = snap["low_position_evaluations"][0]
        self.assertEqual(low["task_id"], "low_position")
        self.assertFalse(low["is_recommendation"])
        self.assertFalse(low["executed_trade"])
        self.assertEqual(low["signal_source_report_id"], "r1")
        self.assertIsNone(low["executable_net_return_pct"])
        self.assertEqual(low["frozen_signal_features"]["close_location"], 0.8)

    def test_provider_failures_do_not_count_as_hits(self):
        rows = extract_observations([report()], date(2026, 10, 15))
        snap = build_snapshot([], lambda code: ([], None, ["Timeout"]),
                              now=datetime(2026, 10, 15, 18, tzinfo=CN),
                              low_position_observations=rows)
        self.assertEqual(snap["low_position_summary"]["status_counts"]["provider_unavailable"], 1)
        self.assertEqual(snap["low_position_summary"]["horizons"]["1"]["matured_count"], 0)

    def test_horizon_report_never_uses_unmatured_or_invalid_returns(self):
        empty = horizon_statistics([{"status": "pending", "horizons": [{"h": 2, "status": "pending"}]}])
        self.assertEqual(empty["horizons"]["2"]["matured_count"], 0)
        self.assertIsNone(empty["horizons"]["2"]["positive_close_rate_pct"])


if __name__ == "__main__":
    unittest.main()
