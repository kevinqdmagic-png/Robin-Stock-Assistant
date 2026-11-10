"""Regression: Tencent day-K 501 must not block verified unadjusted forward observations."""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intraday_forward import update_forward
from trading_calendar import CN_TZ


SIGNAL = {
    "date": "2026-10-08", "task_id": "early_pair", "status": "observed",
    "candidates": [{
        "code": "600101", "name": "观察票", "price": 10.0,
        "as_of": "2026-10-08T09:50:01+08:00",
        "quote_source": "tencent_public",
    }],
    "momentum_control": [],
}
BARS = [
    {"date": "2026-10-08", "open": 10.0, "close": 10.0, "high": 10.2, "low": 9.8, "volume": 100},
    {"date": "2026-10-09", "open": 10.3, "close": 11.0, "high": 11.1, "low": 10.0, "volume": 120},
    {"date": "2026-10-12", "open": 10.0, "close": 9.0, "high": 10.0, "low": 8.8, "volume": 130},
]
NOW = datetime(2026, 10, 14, 16, 10, tzinfo=CN_TZ)


class IntradayForwardFallbackTests(unittest.TestCase):
    def test_tencent_501_falls_back_to_sina_with_real_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "f.json"
            with patch("daily_providers.tencent_daily",
                       side_effect=requests.HTTPError("501 Not Implemented")) as primary, \
                 patch("daily_providers.sina_daily", return_value=BARS) as fallback:
                result = update_forward([SIGNAL], path, NOW)
                self.assertEqual(primary.call_count, 1)
                self.assertEqual(fallback.call_count, 1)
            self.assertEqual(result["appended"], 2)
            rows = json.loads(path.read_text(encoding="utf-8"))["items"]
            self.assertTrue(all(x["daily_source"] == "sina_unadjusted_daily" for x in rows))
            self.assertTrue(all(x["daily_fallback_used"] is True for x in rows))
            self.assertTrue(all(x["executed_trade"] is False for x in rows))
            self.assertTrue(all(x["net_trade_return_pct"] is None for x in rows))
            self.assertEqual(update_forward([SIGNAL], path, NOW,
                             daily_loader=lambda *a, **kw: BARS)["appended"], 0)

    def test_both_providers_failed_does_not_publish_outcomes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "f.json"
            with patch("daily_providers.tencent_daily",
                       side_effect=requests.HTTPError("501")), \
                 patch("daily_providers.sina_daily",
                       side_effect=requests.Timeout("sina down")):
                result = update_forward([SIGNAL], path, NOW)
            self.assertEqual(result["appended"], 0)
            self.assertEqual(result["status"], "pending_or_data_gaps")
            self.assertFalse(path.exists())

    def test_forward_adjusted_data_rejected_even_with_provider_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "f.json"
            result = update_forward(
                [SIGNAL], path, NOW,
                daily_loader=lambda *a, **kw: {
                    "rows": BARS, "provider": "sina",
                    "adjustment": "1", "fallback_used": True
                },
            )
            self.assertEqual(result["appended"], 0)
            self.assertIn("ValueError", result["provider_errors"])
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
