import copy
from datetime import date, datetime, timedelta
import sys
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from learning_loop import (
    is_session, nth_session_after, evaluate, build_snapshot,
    append_snapshot, validate_learning_archive, verify_append_only,
    evaluate_shadow_rules,
)

CN = ZoneInfo("Asia/Shanghai")


def fixture():
    dates = []
    d = date(2026, 3, 1)
    while d <= date(2026, 10, 30):
        if is_session(d):
            dates.append(d)
        d += timedelta(days=1)
    rows = [{"date": d.isoformat(), "open": 10, "high": 10.3,
             "low": 9.7, "close": 10, "volume": 15000} for d in dates]
    return rows


def signal(anchor="2026-09-24", published_at="2026-09-24T15:20:00+08:00"):
    return {"id": "signal-demo", "date": anchor,
            "published_at": published_at, "code": "600000",
            "provenance": "contemporaneous", "strategy": "test_v1"}


class LearningTests(unittest.TestCase):
    def test_exchange_horizons_skip_weekend_and_holiday(self):
        day = date(2026, 9, 24)
        self.assertEqual(nth_session_after(day, 1), date(2026, 9, 28))
        self.assertEqual(nth_session_after(day, 2), date(2026, 9, 29))
        self.assertEqual(nth_session_after(day, 5), date(2026, 10, 9))
        self.assertIsNone(nth_session_after(date(2026, 12, 30), 5))

    def test_observation_proxy_never_claims_trades(self):
        bars = fixture()
        by = {x["date"]: x for x in bars}
        by["2026-09-28"].update(high=10.5, close=10.4)
        by["2026-09-29"].update(low=9.5, close=9.6)
        result = evaluate(signal(), bars, "test_public_daily", as_of=date(2026, 9, 30))
        self.assertFalse(result["executed_trade"])
        self.assertIsNone(result["executable_net_return_pct"])
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["horizons"][0]["date"], "2026-09-28")
        self.assertEqual(result["horizons"][1]["close_pct"], -4)
        self.assertEqual(result["horizons"][2]["status"], "pending")
        self.assertEqual(result["feature_snapshot"]["as_of"], "2026-09-23")
        self.assertTrue(result["attribution"])

    def test_missing_bar_not_shifted_to_next_session(self):
        bars = [r for r in fixture() if r["date"] != "2026-09-28"]
        result = evaluate(signal(), bars, "test_public_daily", as_of=date(2026, 9, 30))
        self.assertEqual(result["horizons"][0]["status"], "missing_or_suspended_session")
        self.assertEqual(result["horizons"][1]["status"], "missing_or_suspended_session")
        self.assertEqual(result["horizons"][1]["date"], "2026-09-29")

    def test_after_next_open_excluded_from_valid_samples(self):
        rec = signal(published_at="2026-09-28T09:31:00+08:00")
        self.assertEqual(
            evaluate(rec, fixture(), "source", as_of=date(2026, 9, 30))["status"],
            "ineligible_published_after_next_open")

    def test_corporate_action_is_quarantined_if_pct_disagrees(self):
        bars = fixture()
        for b in bars:
            b["pct"] = 0
        next(r for r in bars if r["date"] == "2026-09-29").update(low=1.5, close=2)
        result = evaluate(signal(), bars, "source", as_of=date(2026, 9, 30))
        self.assertEqual(result["status"], "quarantine_corporate_action_or_price_disagreement")

    def test_closed_or_preclose_never_writes_learning(self):
        recs = [signal()]
        provider = lambda code: (fixture(), "test", [])
        for time in ("2026-10-11T18:00:00+08:00", "2026-10-12T13:00:00+08:00"):
            result = build_snapshot(recs, provider, now=datetime.fromisoformat(time))
            self.assertFalse(append_snapshot({"schema_version": 1, "runs": []}, result)[1])

    def test_snapshot_immutable_and_repeat_is_idempotent(self):
        recs = [signal()]
        provider = lambda code: (fixture(), "test", [])
        snapshot = build_snapshot(recs, provider, now=datetime(2026, 9, 30, 18, tzinfo=CN))
        self.assertEqual(snapshot["sample_count"], 1)
        self.assertFalse(snapshot["trade_execution_verified"])
        self.assertEqual(snapshot["validation"]["status"], "insufficient_verified_proxy_samples")
        ledger = {"schema_version": 1, "runs": []}
        after, changed = append_snapshot(ledger, snapshot)
        self.assertTrue(changed)
        self.assertFalse(append_snapshot(after, snapshot)[1])
        validate_learning_archive(after)
        verify_append_only(ledger, after)
        corrupted = copy.deepcopy(after)
        corrupted["runs"][0]["date"] = "2026-10-01"
        with self.assertRaises(ValueError):
            verify_append_only(after, corrupted)

    def test_insufficient_data_is_not_training(self):
        self.assertEqual(evaluate_shadow_rules([])["status"], "insufficient_verified_proxy_samples")
        self.assertFalse(evaluate_shadow_rules([])["promotion_authorized"])

    def test_no_future_quote_from_provider_used(self):
        recs = [signal()]
        original = fixture()
        def provider(code):
            return (original + [{"date": "2026-11-03", "open": 90,
                                 "close": 90, "high": 99, "low": 80, "volume": 900}],
                    "test", [])
        snapshot = build_snapshot(recs, provider, now=datetime(2026, 9, 30, 18, tzinfo=CN))
        first = snapshot["evaluations"][0]
        baseline = evaluate(signal(), fixture(), "test", as_of=date(2026, 9, 30))
        self.assertEqual(first["horizons"], baseline["horizons"])

    def test_provider_errors_cannot_be_performance(self):
        record = signal()
        result = build_snapshot([record], lambda code: ([], None, ["timeout"]),
                                now=datetime(2026, 9, 30, 18, tzinfo=CN))
        self.assertEqual(result["evaluations"][0]["status"], "provider_unavailable")
        self.assertEqual(result["validation"]["total_mature_t2_featured"], 0)


if __name__ == "__main__":
    unittest.main()
