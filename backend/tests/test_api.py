import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import app as api
import market_insights


class APITests(unittest.TestCase):
    def test_partial_breadth_and_st_exclusion_are_distinct(self):
        rows = pd.DataFrame([
            {"code": "600000", "name": "A", "price": 10, "pct": 1, "amount": 1e8},
            {"code": "600001", "name": "*ST B", "price": 3, "pct": -1, "amount": 2e8},
        ])
        result = api._build_market_payload(rows, "partial", False, [])
        self.assertFalse(result["breadth_complete"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["decline"], 1)
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["amount_yi"], 3)

    def test_research_errors_not_masked_as_empty_success(self):
        with patch("app.archive_page", side_effect=ValueError("bad json")):
            self.assertFalse(api.research()["ok"])

    def test_bad_code_rejected_before_provider_call(self):
        with patch("app._get_daily") as mock:
            self.assertFalse(api.stock_backtest("../600000")["ok"])
            mock.assert_not_called()

    def test_quote_field_mapping(self):
        with patch("market_insights.fetch_rows", return_value=[{
            "f12": "BK01", "f14": "行业", "f3": 1.2, "f128": "领涨A", "f136": 4.2,
            "f104": 8, "f105": 2, "f124": 1790751600,
        }]):
            board = market_insights.board_quotes("industry", True)[0]
        self.assertEqual(board["leader"], "领涨A")
        self.assertEqual(board["advance"], 8)
        self.assertIsNotNone(board["as_of"])

    def test_overview_partial_failure_remains_visible(self):
        with patch.dict(market_insights._CACHE, {"payload": None, "saved_at": 0}), \
                patch("market_insights.index_quotes", return_value=[{"code": "000001"}]), \
                patch("market_insights.board_quotes", side_effect=ValueError("offline")):
            result = market_insights.overview()
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["provider_errors"]), 4)


if __name__ == "__main__":
    unittest.main()
