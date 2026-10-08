import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as api

BARS = [{"time": "2026-10-08 15:00", "open": 10, "close": 11,
         "high": 11, "low": 10, "volume": 5, "amount": 5500}]


class MinuteReliabilityTests(unittest.TestCase):
    def setUp(self):
        with api._minute_lock:
            api._minute_cache.clear()
            api._minute_failures.clear()
            api._minute_inflight.clear()
        api._minute_eastmoney_retry_after = 0.0

    def test_concurrent_cold_requests_share_success(self):
        entered, release = threading.Event(), threading.Event()
        def fetch(code):
            entered.set()
            release.wait(2)
            return BARS, "eastmoney_trends", []
        with patch("app._fetch_minute", side_effect=fetch) as provider:
            with ThreadPoolExecutor(max_workers=6) as pool:
                owner = pool.submit(api.stock_minute, "600592")
                self.assertTrue(entered.wait(1))
                others = [pool.submit(api.stock_minute, "600592") for _ in range(5)]
                release.set()
                rows = [owner.result(2)] + [f.result(2) for f in others]
            self.assertEqual(provider.call_count, 1)
        self.assertTrue(all(row["ok"] and row["bars"] == BARS for row in rows))
        self.assertFalse(api._minute_inflight)

    def test_failure_cooldown_avoids_repeated_upstream_timeouts(self):
        with patch("app._fetch_minute", return_value=([], None, ["HTTPError"])) as provider:
            first = api.stock_minute("600592")
            second = api.stock_minute("600592")
        self.assertFalse(first["ok"])
        self.assertFalse(second["ok"])
        self.assertEqual(provider.call_count, 1)
        self.assertGreater(second["retry_after_sec"], 0)
        self.assertFalse(api._minute_inflight)

    def test_stale_chart_returns_while_one_refresh_runs(self):
        old_time = time.time() - 60
        old = {"ok": True, "code": "600592", "time_cn": "2026-10-08T15:00:00+08:00",
               "bars": BARS, "source": "eastmoney_trends"}
        api._minute_cache["600592"] = {"saved_at": old_time, "payload": old}
        entered, release = threading.Event(), threading.Event()
        def fetch(code):
            entered.set()
            release.wait(2)
            return [], None, ["ConnectionError"]
        with patch("app._fetch_minute", side_effect=fetch) as provider:
            first = api.stock_minute("600592")
            self.assertTrue(entered.wait(1))
            flight = api._minute_inflight["600592"]
            second = api.stock_minute("600592")
            self.assertTrue(first["stale"] and second["refreshing"])
            self.assertEqual(first["time_cn"], old["time_cn"])
            self.assertGreaterEqual(first["cache_age_sec"], 60)
            self.assertEqual(provider.call_count, 1)
            release.set()
            self.assertTrue(flight.wait(2))
            failed = api.stock_minute("600592")
        self.assertEqual(failed["bars"], BARS)
        self.assertEqual(failed["errors"], ["ConnectionError"])
        self.assertEqual(api._minute_cache["600592"]["saved_at"], old_time)
        self.assertFalse(api._minute_inflight)

    def test_unexpected_exception_releases_guard_and_uses_cooldown(self):
        with patch("app._fetch_minute", side_effect=RuntimeError("offline")):
            result = api.stock_minute("600592")
        self.assertFalse(result["ok"])
        self.assertEqual(result["errors"], ["RuntimeError"])
        self.assertFalse(api._minute_inflight)

    def test_tencent_date_price_and_cumulative_volume_mapping(self):
        response = Mock()
        response.json.return_value = {"data": {"sh600592": {"data": {
            "date": "20261008", "data": ["0930 10.2 100 102000", "0931 10.3 150 153500"]
        }}}}
        with patch("app.requests.get", return_value=response):
            bars, source, errors = api._tencent_minute("600592")
        self.assertEqual(source, "tencent_minute")
        self.assertEqual(bars[1]["time"], "2026-10-08 09:31")
        self.assertEqual(bars[1]["volume"], 50)
        self.assertEqual(bars[1]["amount"], 51500)
        self.assertFalse(bars[1]["ohlc_verified"])
        self.assertEqual(errors, [])

    def test_eastmoney_uses_close_field_instead_of_open(self):
        response = Mock()
        response.json.return_value = {"data": {"trends": [
            "2026-10-08 09:31,10.0,10.4,10.5,9.9,20,20400,10.2"
        ]}}
        with patch("app.requests.get", return_value=response):
            bars, _, _ = api._eastmoney_minute("600592")
        self.assertEqual(bars[0]["open"], 10.0)
        self.assertEqual(bars[0]["close"], 10.4)

    def test_failed_eastmoney_uses_independent_provider_and_cools_down(self):
        with patch("app._eastmoney_minute", return_value=([], None, ["ConnectionError"])) as east, \
                patch("app._tencent_minute", return_value=(BARS, "tencent_minute", [])) as fallback:
            first = api._fetch_minute("600592")
            second = api._fetch_minute("600000")
        self.assertEqual(east.call_count, 1)
        self.assertEqual(fallback.call_count, 2)
        self.assertEqual(first[1], "tencent_minute")
        self.assertEqual(second[1], "tencent_minute")

    def test_fallback_chart_cannot_become_unverified_buy_signal(self):
        with patch("app.stock_minute", return_value={"ok": True, "source": "tencent_minute", "bars": BARS}), \
                patch("app._get_daily") as daily:
            result = api._analyze_signal({"code": "600592", "name": "龙溪股份", "pct": 2})
        self.assertIsNone(result)
        daily.assert_not_called()


if __name__ == "__main__":
    unittest.main()

