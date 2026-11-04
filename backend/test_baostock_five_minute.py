"""Offline tests for BaoStock five-minute historical validation."""
import unittest
from unittest.mock import Mock

from baostock_five_minute import fetch_five_minute


class FakeResult:
    error_code = "0"
    fields = ["date", "time", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag"]

    def __init__(self, records):
        self.records = iter(records)
        self.current = None

    def next(self):
        self.current = next(self.records, None)
        return self.current is not None

    def get_row_data(self):
        return self.current


class FiveMinuteTests(unittest.TestCase):
    def client(self, records):
        api = Mock()
        api.login.return_value.error_code = "0"
        api.query_history_k_data_plus.return_value = FakeResult(records)
        return api

    def test_valid_bar(self):
        row = ["2026-11-04", "20261104100000000", "sz.002218", "3.5", "3.6", "3.4", "3.55", "1200", "4200", "3"]
        api = self.client([row])
        result = fetch_five_minute("sz.002218", "2026-11-04", client=api)
        self.assertEqual(result["count"], 1)
        self.assertFalse(result["complete_session"])
        self.assertEqual(result["bars"][0]["close"], 3.55)
        api.logout.assert_called_once()

    def test_reject_duplicate_timestamp(self):
        row = ["2026-11-04", "20261104100000000", "sz.002218", "3.5", "3.6", "3.4", "3.55", "1200", "4200", "3"]
        api = self.client([row, row])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            fetch_five_minute("sz.002218", "2026-11-04", client=api)
        api.logout.assert_called_once()

    def test_reject_bad_price(self):
        row = ["2026-11-04", "20261104100000000", "sz.002218", "3.5", "3.4", "3.6", "3.55", "1200", "4200", "3"]
        api = self.client([row])
        with self.assertRaisesRegex(ValueError, "ohlcv"):
            fetch_five_minute("sz.002218", "2026-11-04", client=api)

    def test_reject_bad_code_without_login(self):
        with self.assertRaisesRegex(ValueError, "invalid_baostock_code"):
            fetch_five_minute("bad", "2026-11-04", client=Mock())


if __name__ == "__main__":
    unittest.main()
