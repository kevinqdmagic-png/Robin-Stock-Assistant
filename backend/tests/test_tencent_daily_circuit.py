"""Public Tencent 501 retry gate: no repeated outage calls or fake adjusted data."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import daily_providers as providers


SAMPLE = [
    {"date": "2026-11-06", "open": 10.0, "close": 10.1,
     "high": 10.3, "low": 9.9, "volume": 1234.0},
]


class TencentDailyCircuitTests(unittest.TestCase):
    def test_http_501_opens_circuit_and_unadjusted_falls_back(self):
        failure = requests.Response()
        failure.status_code = 501
        failure.url = providers.URL
        with patch.object(providers, "_tencent_retry_after", 0.0), \
             patch.object(providers.requests, "get", return_value=failure) as client:
            with self.assertRaises(requests.HTTPError):
                providers.tencent_daily("600101", adjust="0")
            with self.assertRaisesRegex(ValueError, "tencent_daily_circuit_open"):
                providers.tencent_daily("600102", adjust="0")
            with patch.object(providers, "sina_daily", return_value=SAMPLE):
                fallback = providers.historical_daily_with_fallback(
                    "600103", adjust="0"
                )
            self.assertEqual(client.call_count, 1)
            self.assertEqual(fallback["rows"], SAMPLE)
            self.assertEqual(fallback["provider"], "sina")
            self.assertTrue(fallback["fallback_used"])
            self.assertEqual(fallback["adjustment"], "0")

    def test_adjusted_history_never_substitutes_sina(self):
        with patch.object(providers, "_tencent_retry_after", float("inf")), \
             patch.object(providers, "sina_daily") as fallback:
            with self.assertRaisesRegex(
                ValueError, "adjusted_history_fallback_unavailable"
            ):
                providers.historical_daily_with_fallback("600101", adjust="1")
            fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
