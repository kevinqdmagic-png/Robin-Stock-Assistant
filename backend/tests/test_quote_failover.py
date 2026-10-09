import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as api
import market_insights as insights
from quote_providers import stock_symbol, tencent_quotes


def quote(code="600127", source="tencent_public"):
    return {"code": code, "name": "金健米业", "price": 15.18, "pct": 10.0,
            "turnover": 31.07, "volume_ratio": 1.84,
            "as_of": "2026-10-09T13:18:36+08:00", "source": source}


class QuoteFailoverTests(unittest.TestCase):
    def setUp(self):
        api._quote_cache.clear()
        api._quote_refreshing_codes.clear()

    def test_public_response_mapping_and_provider_timestamp(self):
        fields = [""] * 50
        values = {1: "金健米业", 2: "600127", 3: "15.18", 30: "20261009131836",
                  32: "10.00", 38: "31.07", 49: "1.84"}
        for position, value in values.items():
            fields[position] = value
        response = Mock(text='v_sh600127="' + "~".join(fields) + '";')
        with patch("quote_providers.requests.get", return_value=response):
            result = tencent_quotes(["sh600127"])
        self.assertEqual(result, [quote()])
        fields[49] = "-"
        response.text = 'v_sh600127="' + "~".join(fields) + '";'
        with patch("quote_providers.requests.get", return_value=response):
            self.assertIsNone(tencent_quotes(["sh600127"])[0]["volume_ratio"])
        fields[30] = "bad-date"
        response.text = 'v_sh600127="' + "~".join(fields) + '";'
        with patch("quote_providers.requests.get", return_value=response):
            with self.assertRaises(ValueError):
                tencent_quotes(["sh600127"])

    def test_stock_symbols_preserve_exchange_and_new_beijing_codes(self):
        self.assertEqual(stock_symbol("000001"), "sz000001")
        self.assertEqual(stock_symbol("600127"), "sh600127")
        self.assertEqual(stock_symbol("920001"), "bj920001")

    def test_cold_watchlist_survives_eastmoney_502(self):
        with patch("app._eastmoney_quotes", side_effect=requests.HTTPError("502")), \
                patch("app.tencent_quotes", return_value=[quote()]):
            result = api.quotes("600127")
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "tencent_batch_quote")
        self.assertEqual(result["items"], [quote()])
        self.assertIn("eastmoney_batch:HTTPError", result["provider_errors"])
        self.assertFalse(result["refreshing"])

    def test_partial_primary_batch_fills_missing_stocks_in_requested_order(self):
        with patch("app._eastmoney_quotes", return_value=[quote("002068", "eastmoney_public")]), \
                patch("app.tencent_quotes", return_value=[quote()]) as fallback:
            result = api.quotes("600127,002068")
        fallback.assert_called_once_with(["sh600127"])
        self.assertEqual([r["code"] for r in result["items"]], ["600127", "002068"])
        self.assertEqual(result["source"], "mixed_batch_quote")
        self.assertEqual(result["count"], 2)
        self.assertFalse(result["refreshing"])

    def test_both_providers_fail_without_fabricating_quotes(self):
        with patch("app._eastmoney_quotes", side_effect=requests.HTTPError("502")), \
                patch("app.tencent_quotes", side_effect=requests.Timeout()), \
                patch("app._kick_quote_refresh"):
            result = api.quotes("600127")
        self.assertFalse(result["ok"])
        self.assertEqual(result["items"], [])
        self.assertEqual(len(result["provider_errors"]), 2)

    def test_partial_refresh_keeps_old_quote_age_and_retries_missing_stock(self):
        api._quote_cache["002068"] = {"saved_at": time.time() - 900, "quote": quote("002068")}
        with patch("app._eastmoney_quotes", return_value=[quote()]), \
                patch("app.tencent_quotes", side_effect=requests.Timeout()), \
                patch("app._kick_quote_refresh") as refresh:
            result = api.quotes("600127,002068")
        self.assertGreaterEqual(result["cache_age_sec"], 899)
        self.assertTrue(result["refreshing"])
        refresh.assert_called_once()

    def test_index_outage_uses_explicit_index_symbols(self):
        rows = [quote(code) for code in ("000001", "399001", "399006", "000688")]
        with patch("market_insights.fetch_rows", side_effect=requests.HTTPError("502")), \
                patch("market_insights.tencent_quotes", return_value=rows) as fallback:
            result = insights.index_quotes()
        fallback.assert_called_once_with(["sh000001", "sz399001", "sz399006", "sh000688"])
        self.assertEqual(result, rows)

    def test_yesterdays_index_is_replaced_by_newer_quote_during_trading(self):
        rows = [{"f12": code, "f14": "指数", "f2": 100, "f3": -2,
                 "f124": 1791446400} for code in ("000001", "399001", "399006", "000688")]
        fresh = [quote(r["f12"]) for r in rows]
        with patch("market_insights.fetch_rows", return_value=rows), \
                patch("market_insights.session_state", return_value={"is_live": True}), \
                patch("market_insights.tencent_quotes", return_value=fresh):
            result = insights.index_quotes()
        self.assertEqual(result, fresh)

    def test_wrong_market_scope_is_rejected_before_board_display(self):
        wrong = Mock()
        wrong.json.return_value = {"data": {"diff": [{"f12": "600127"}]}}
        good = Mock()
        good.json.return_value = {"data": {"diff": [{"f12": "BK0001"}]}}
        with patch("market_insights.requests.get", side_effect=[wrong, good]) as fetch:
            rows = insights.fetch_rows({"fs": "m:90 t:2 f:!50"})
        self.assertEqual(rows, [{"f12": "BK0001"}])
        self.assertIn("push2delay", fetch.call_args.args[0])

    def test_overview_refresh_retains_failed_sections_with_stale_marker(self):
        cached = {"ok": True, "indices": [{"code": "000001"}],
                  "industry": {"strong": [{"code": "BK001"}], "weak": []},
                  "concept": {"strong": [], "weak": []}}
        with patch.dict(insights._CACHE, {"payload": cached, "saved_at": time.time(), "refreshing": False}), \
                patch("market_insights.index_quotes", return_value=[quote("000001")]), \
                patch("market_insights.board_quotes", side_effect=requests.Timeout()):
            result = insights._refresh_overview()
            cached_result = insights.overview()
        self.assertEqual(result["industry"]["strong"], cached["industry"]["strong"])
        self.assertTrue(cached_result["stale"])
        self.assertIn("industry:strong", result["stale_sections"])


if __name__ == "__main__":
    unittest.main()
