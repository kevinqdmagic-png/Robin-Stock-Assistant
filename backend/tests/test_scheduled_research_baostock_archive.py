"""After-close partial research must acknowledge dated BaoStock OHLCV evidence."""
import importlib.util
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
spec = importlib.util.spec_from_file_location(
    "scheduled_research_archive", ROOT / "scripts/run_scheduled_research.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
CN = ZoneInfo("Asia/Shanghai")


def archive():
    return {
        "ok": True, "provider": "baostock", "trade_date": "2026-11-10",
        "fallback_used": False,
        "coverage": {"checked": 5225, "verified": 5218,
                     "coverage_ratio": 0.99866},
        "rows": [
            {"code": "sh.600101", "open": 10, "close": 11},
            {"code": "sz.000001", "open": 10, "close": 9},
            {"code": "sz.300001", "open": 10, "close": 10},
        ],
    }


class ScheduledArchivedEvidenceTests(unittest.TestCase):
    def test_uses_baostock_market_baseline_when_online_lookback_is_empty(self):
        now = datetime(2026, 11, 11, 0, 20, tzinfo=CN)
        with patch.object(mod, "read_snapshot", return_value=archive()) as reader:
            snapshot = mod.collect(
                now, pool=[], quote_provider=lambda _: [],
                recover_latest_completed=True,
            )
        reader.assert_called_once_with("2026-11-10")
        info = snapshot["archived_market"]
        self.assertEqual(info["provider"], "baostock")
        self.assertEqual(info["status"], "verified")
        self.assertEqual(info["close_above_open"], 1)
        self.assertEqual(info["close_below_open"], 1)
        self.assertEqual(info["close_equal_open"], 1)
        self.assertEqual(info["coverage"]["verified"], 5218)
        self.assertEqual(snapshot["fresh"], 0)
        self.assertFalse(snapshot["full_a_share_coverage"])
        reports = mod.build_reports(snapshot, now)
        market = next(x for x in reports if x["task_id"] == "market_review")
        self.assertIn("已核验沪深全市场历史日线", market["body"])
        self.assertIn("不是相对昨收的上涨/下跌家数", market["body"])
        self.assertFalse(market["eligible_for_integrated_research"])
        self.assertEqual(market["run_status"], "blocked")

    def test_missing_archive_never_claims_verified_full_market(self):
        now = datetime(2026, 11, 11, 0, 20, tzinfo=CN)
        with patch.object(mod, "read_snapshot",
                          return_value={"ok": False, "source_errors": [
                              {"provider": "baostock", "reason": "missing"}]}):
            snapshot = mod.collect(
                now, pool=[], quote_provider=lambda _: [],
                recover_latest_completed=True,
            )
        self.assertEqual(snapshot["archived_market"]["status"], "unavailable")
        market = next(x for x in mod.build_reports(snapshot, now)
                      if x["task_id"] == "market_review")
        self.assertIn("缺少可核验全市场历史日线归档", market["body"])


if __name__ == "__main__":
    unittest.main()
