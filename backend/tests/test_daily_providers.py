"""Tencent day K backup format, volume and corporate-action safeguards."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from daily_providers import parse_tencent_daily, tencent_daily


def data(key="qfqday"):
    return {"data": {"sz002068": {key: [
        ["2026-10-12", "9.10", "9.40", "9.50", "9.00", "10000"],
        ["2026-10-13", "9.40", "9.45", "9.55", "9.38", "12000", {"bonus": 0}],
        ["2026-10-14", "9.45", "9.51", "9.61", "9.40", "12050"],
    ]}}}


class TencentDailyTests(unittest.TestCase):
    def test_forward_adjusted_kline_parsing(self):
        result = parse_tencent_daily(data(), "sz002068", adjust="1")
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["date"], "2026-10-12")
        self.assertEqual(result[1]["volume"], 12000)
        self.assertEqual(result[-1]["high"], 9.61)
        self.assertNotIn("amount", result[0])

    def test_forward_adjusted_not_replaced_by_raw(self):
        with self.assertRaisesRegex(ValueError, "requested_adjustment_unavailable"):
            parse_tencent_daily(data("day"), "sz002068", adjust="1")
        with self.assertRaisesRegex(ValueError, "requested_adjustment_unavailable"):
            parse_tencent_daily(data(), "sz002068", adjust="0")

    def test_raw_price_history_for_performance_is_not_qfq(self):
        result = parse_tencent_daily(data("day"), "sz002068", adjust="0")
        self.assertEqual(len(result), 3)

    def test_zero_volume_preserved_to_fail_closed(self):
        payload = data()
        payload["data"]["sz002068"]["qfqday"][1][5] = "0"
        result = parse_tencent_daily(payload, "sz002068")
        self.assertEqual(result[1]["volume"], 0)

    def test_negative_or_duplicate_records_rejected(self):
        payload = data()
        payload["data"]["sz002068"]["qfqday"][1][4] = "10.00"
        self.assertEqual(len(parse_tencent_daily(payload, "sz002068")), 2)
        payload = data()
        payload["data"]["sz002068"]["qfqday"][1][0] = "2026-10-12"
        with self.assertRaisesRegex(ValueError, "duplicate_daily_date"):
            parse_tencent_daily(payload, "sz002068")

    def test_tencent_http_uses_code_exchange_and_adjustment(self):
        client = Mock()
        client.get.return_value.json.return_value = data()
        result = tencent_daily("002068", limit=120, client=client)
        self.assertEqual(len(result), 3)
        call = client.get.call_args
        self.assertEqual(call.kwargs["params"]["param"], "sz002068,day,,,120,qfq")
        with self.assertRaises(ValueError):
            tencent_daily("bad", client=client)


if __name__ == "__main__":
    unittest.main()
