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

    def test_recent_snapshot_is_still_not_a_recommendation(self):
        now = datetime(2026, 10, 13, 9, 50, tzinfo=TZ)
        feed = {"source": "https://market-data.vendor.cn/quotes", "as_of": now.isoformat(),
                "quotes": [{"code": "600000", "price": 12.5, "market": "SH", "name": "浦发银行", "previous_close": 12.3, "volume": 100000, "turnover": 1200000, "pct": 1.63, "turnover_ratio": 1.0, "as_of": now.isoformat()}]}
        result = module.evaluate("early_pair", now, feed)
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["reason"], "screened_watch_not_validated_strategy")
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(result["snapshot"]["quote_count"], 1)

    def test_stale_snapshot_rejected(self):
        now = datetime(2026, 10, 13, 14, 40, tzinfo=TZ)
        feed = {"source": "https://market-data.vendor.cn/quotes",
                "as_of": "2026-10-13T14:20:00+08:00",
                "quotes": [{"code": "600000", "price": 12.5}]}
        result = module.evaluate("late_pair", now, feed)
        self.assertEqual(result["reason"], "stale_or_future_snapshot")
        self.assertNotIn("snapshot", result)

    def test_invalid_quote_rejected(self):
        now = datetime(2026, 10, 13, 9, 50, tzinfo=TZ)
        feed = {"source": "https://market-data.vendor.cn/quotes", "as_of": now.isoformat(),
                "quotes": [{"code": "bad", "price": -1}]}
        self.assertEqual(module.evaluate("early_pair", now, feed)["reason"], "invalid_code")

    def test_duplicate_code_is_rejected(self):
        now = datetime(2026, 10, 13, 9, 50, tzinfo=TZ)
        quote = {"code": "600000", "price": 12.5, "market": "SH",
                 "name": "浦发银行", "previous_close": 12.3,
                 "volume": 100000, "turnover": 1200000, "pct": 1.63, "turnover_ratio": 1.0, "as_of": now.isoformat()}
        feed = {"source": "https://market-data.vendor.cn/quotes", "as_of": now.isoformat(),
                "quotes": [quote, dict(quote)]}
        self.assertEqual(module.evaluate("early_pair", now, feed)["reason"],
                         "duplicate_quote_code")

    def test_price_only_quote_cannot_pass_evidence_gate(self):
        now = datetime(2026, 10, 13, 14, 40, tzinfo=TZ)
        feed = {"source": "https://market-data.vendor.cn/quotes", "as_of": now.isoformat(),
                "quotes": [{"code": "600000", "price": 12.5}]}
        self.assertEqual(module.evaluate("late_pair", now, feed)["reason"],
                         "missing_exchange")

    def test_placeholder_source_rejected(self):
        now = datetime(2026, 10, 13, 9, 50, tzinfo=TZ)
        feed = {"source": "https://example.org/fake", "as_of": now.isoformat(),
                "quotes": [{"code": "600000", "price": 12.5, "market": "SH",
                            "name": "sample", "previous_close": 12.3,
                            "volume": 100000, "turnover": 1200000}]}
        self.assertEqual(module.evaluate("early_pair", now, feed)["reason"],
                         "untrusted_source")

    def test_invalid_slot_rejected(self):
        with self.assertRaises(ValueError):
            module.evaluate("unregistered", datetime(2026, 10, 13, 9, 50, tzinfo=TZ))
