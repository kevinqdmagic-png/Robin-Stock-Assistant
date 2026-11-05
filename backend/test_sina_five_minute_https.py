"""Offline tests for the Sina HTTPS five-minute fallback."""
import json
import unittest

from sina_five_minute_https import fetch_five_minute_sina


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.payload


def opener_for(rows):
    payload = ("/* guard */ var _robin5=(" + json.dumps(rows) + ");").encode()
    return lambda _request, timeout: FakeResponse(payload)


class SinaFiveMinuteTests(unittest.TestCase):
    def test_filters_exact_date_and_normalizes_timestamp(self):
        rows = [
            {"day": "2026-11-04 15:00:00", "open": "3.4", "high": "3.5",
             "low": "3.3", "close": "3.45", "volume": "100", "amount": "345"},
            {"day": "2026-11-05 09:35:00", "open": "3.5", "high": "3.6",
             "low": "3.4", "close": "3.55", "volume": "1200", "amount": "4200"},
        ]
        result = fetch_five_minute_sina("sz.002218", "2026-11-05", opener=opener_for(rows))
        self.assertEqual(result["provider"], "sina_https_unofficial")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["bars"][0]["time"], "20261105093500000")
        self.assertEqual(result["bars"][0]["amount"], 4200.0)
        self.assertRegex(result["response_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("symbol=sz002218", result["request_url"])

    def test_rejects_bad_ohlcv(self):
        rows = [{"day": "2026-11-05 09:35:00", "open": "3.5", "high": "3.4",
                 "low": "3.6", "close": "3.55", "volume": "1200", "amount": "4200"}]
        with self.assertRaisesRegex(ValueError, "bad_ohlcv"):
            fetch_five_minute_sina("sz.002218", "2026-11-05", opener=opener_for(rows))

    def test_rejects_duplicate_timestamp(self):
        row = {"day": "2026-11-05 09:35:00", "open": "3.5", "high": "3.6",
               "low": "3.4", "close": "3.55", "volume": "1200", "amount": "4200"}
        with self.assertRaisesRegex(ValueError, "duplicate"):
            fetch_five_minute_sina("sh.688109", "2026-11-05", opener=opener_for([row, row]))

    def test_rejects_invalid_wrapper(self):
        def opener(_request, timeout):
            return FakeResponse(b"not jsonp")
        with self.assertRaisesRegex(ValueError, "invalid_jsonp"):
            fetch_five_minute_sina("sh.688109", "2026-11-05", opener=opener)


if __name__ == "__main__":
    unittest.main()
