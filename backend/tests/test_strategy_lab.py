import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from strategy_lab import simulate_daily_open_proxy, summarize_snapshot

DAY = "2026-10-23"
SIGNAL = {"id": "test-20261023", "code": "600000", "date": DAY,
          "published_at": "2026-10-23T18:00:00+08:00"}
MASTER = {"verified": True, "code": "600000", "as_of": DAY,
          "risk_warning": False, "ipo_unlimited": False,
          "corporate_action_checked": True, "tradable": True,
          "price_limit_fraction": 0.1}
BARS = [
    {"date": "2026-10-23", "open": 10, "high": 10.5, "low": 9.9, "close": 10, "volume": 1000},
    {"date": "2026-10-26", "open": 10.2, "high": 10.6, "low": 10, "close": 10.4, "volume": 1500},
    {"date": "2026-10-27", "open": 10.7, "high": 10.9, "low": 10.3, "close": 10.6, "volume": 1400},
    {"date": "2026-10-28", "open": 10.5, "high": 10.6, "low": 10.1, "close": 10.2, "volume": 1800},
]


class StrategyLabTests(unittest.TestCase):
    def test_conservative_master_gate(self):
        r = simulate_daily_open_proxy(SIGNAL, BARS)
        self.assertEqual(r["reason"], "historical_security_master_unverified")
        self.assertIsNone(r["actual_strategy_net_return_pct"])

    def test_entry_next_session_exit_following_session(self):
        r = simulate_daily_open_proxy(SIGNAL, BARS, security_master=MASTER)
        self.assertEqual(r["status"], "paper_proxy_complete")
        self.assertEqual(r["entry_date"], "2026-10-26")
        self.assertEqual(r["exit_date"], "2026-10-27")
        self.assertLess(r["paper_net_pct"], r["paper_gross_pct"])
        self.assertFalse(r["verified_order_fill"])
        self.assertIsNone(r["actual_strategy_net_return_pct"])

    def test_opening_limit_up_is_unfilled(self):
        rows = [dict(x) for x in BARS]
        rows[1] = dict(rows[1], open=11, high=11.1)
        r = simulate_daily_open_proxy(SIGNAL, rows, security_master=MASTER)
        self.assertEqual(r["status"], "no_entry")
        self.assertEqual(r["reason"], "opening_limit_up_queue_unverified")

    def test_limit_down_exit_does_not_assume_sale(self):
        rows = [dict(x) for x in BARS]
        rows[2] = dict(rows[2], open=9.36, high=9.4, low=9.3, close=9.36)
        # Next day after an unsaleable limit-down open is absent.
        rows = rows[:3]
        r = simulate_daily_open_proxy(SIGNAL, rows, security_master=MASTER)
        self.assertEqual(r["status"], "pending_exit")
        self.assertEqual(r["reason"], "missing_or_suspended_exit_session")

    def test_missing_next_session_does_not_shift_entry(self):
        rows = [BARS[0], BARS[2], BARS[3]]
        r = simulate_daily_open_proxy(SIGNAL, rows, security_master=MASTER)
        self.assertEqual(r["reason"], "missing_or_suspended_entry_session")

    def test_published_after_entry_must_be_rejected(self):
        altered = dict(SIGNAL, published_at="2026-10-26T09:31:00+08:00")
        r = simulate_daily_open_proxy(altered, BARS, security_master=MASTER)
        self.assertEqual(r["reason"], "signal_not_published_before_entry")

    def test_duplicate_strategy_records_do_not_inflate_success_rate(self):
        base = {"code": "600000", "signal_date": "2026-10-23", "status": "observed",
                "horizons": [{"h": 2, "status": "observed", "close_pct": 2.0,
                              "mae_pct": -6.0}]}
        second = dict(base, signal_id="duplicate-from-market-review")
        result = summarize_snapshot({"date": DAY, "evaluations": [base, second]})
        self.assertEqual(result["horizons"]["2"]["sample_count"], 1)
        self.assertEqual(result["overlap_rows_excluded"], 1)
        self.assertFalse(result["research_gate"]["model_promotion_authorized"])

    def test_empty_lab_has_no_fictitious_win_rate(self):
        result = summarize_snapshot({"date": DAY, "evaluations": []})
        self.assertIsNone(result["horizons"]["2"]["positive_pct"])
        self.assertEqual(result["actual_trades_verified"], 0)


if __name__ == "__main__":
    unittest.main()
