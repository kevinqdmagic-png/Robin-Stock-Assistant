"""Offline checks for free HTTPS daily OHLCV fallback."""
import io
import json
import unittest
from eastmoney_daily_https import fetch_daily_https


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, limit):
        return json.dumps(self.payload).encode()


class DailyHttpsTests(unittest.TestCase):
    def test_valid(self):
        def opener(request, timeout):
            self.assertIn("klt=101", request.full_url)
            return FakeResponse({"data": {"klines": ["2026-11-05,10,11,12,9,100,1000"]}})
        bar = fetch_daily_https("sz.002218", "2026-11-05", opener)
        self.assertEqual(bar["close"], 11)
        self.assertEqual(bar["provider"], "eastmoney_https_unofficial")

    def test_stale_date_rejected(self):
        def opener(request, timeout):
            return FakeResponse({"data": {"klines": ["2026-11-04,10,11,12,9,100,1000"]}})
        with self.assertRaisesRegex(ValueError, "wrong_date"):
            fetch_daily_https("sz.002218", "2026-11-05", opener)

    def test_invalid_prices_rejected(self):
        def opener(request, timeout):
            return FakeResponse({"data": {"klines": ["2026-11-05,10,11,9,12,100,1000"]}})
        with self.assertRaisesRegex(ValueError, "invalid_ohlcv"):
            fetch_daily_https("sh.688109", "2026-11-05", opener)

    def test_missing_rejected(self):
        with self.assertRaises(ValueError):
            fetch_daily_https("sh.688109", "2026-11-05", lambda req, timeout: FakeResponse({"data": None}))


if __name__ == "__main__":
    unittest.main()
