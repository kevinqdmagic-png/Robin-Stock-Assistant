"""Production archive-first price observations, never mix inconsistent vendors."""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intraday_forward import update_forward
from trading_calendar import CN_TZ

DAY = "2026-11-05"
T1 = "2026-11-06"
T2 = "2026-11-09"
NOW = datetime(2026, 11, 11, 16, 10, tzinfo=CN_TZ)
SIGNAL = {
    "date": DAY, "task_id": "early_pair", "status": "observed",
    "candidates": [{
        "code": "600101", "name": "跟踪样本", "price": 10.0,
        "as_of": "2026-11-05T09:50:01+08:00",
        "quote_source": "tencent_public",
    }],
    "momentum_control": [],
}
CLOSES = {DAY: 10.0, T1: 11.0, T2: 9.0}


def archive_day(day, provider="baostock"):
    close = CLOSES[day]
    return {
        "ok": True, "trade_date": day, "provider": provider,
        "status": "historical_observation_only",
        "rows": [{"code": "sh.600101", "date": day, "close": close,
                  "open": close, "high": close, "low": close,
                  "volume": 10000.0, "adjustment": "none"}],
    }


def network_history(*_args, **_kwargs):
    return {"rows": [{"date": day, "close": close, "volume": 100}
                     for day, close in CLOSES.items()],
            "provider": "sina", "adjustment": "0",
            "fallback_used": True}


class VerifiedArchivedDailyTests(unittest.TestCase):
    def run_one(self, archive_loader, daily_loader):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "forward.json"
            result = update_forward([SIGNAL], file, NOW,
                                    daily_loader=daily_loader,
                                    archive_loader=archive_loader)
            rows = json.loads(file.read_text())["items"] if file.exists() else []
            return result, rows

    def test_verified_baostock_pair_uses_no_network_and_preserves_source(self):
        loader = Mock(side_effect=lambda day: archive_day(day))
        network = Mock(side_effect=AssertionError("should not go online"))
        result, rows = self.run_one(loader, network)
        self.assertEqual(result["attempted"], 2)
        self.assertEqual(result["appended"], 2)
        self.assertEqual(result["archived_pairs_used"], 2)
        self.assertEqual(loader.call_count, 3)  # anchor, T+1 and T+2 once
        network.assert_not_called()
        self.assertEqual(sorted(x["horizon"] for x in rows), [1, 2])
        self.assertTrue(all(x["daily_source"] ==
                            "baostock_unadjusted_daily_archive" for x in rows))
        self.assertTrue(all(x["daily_fallback_used"] is False for x in rows))
        self.assertTrue(all(x["executed_trade"] is False for x in rows))

    def test_two_days_of_verified_independent_backup_are_disclosed(self):
        result, rows = self.run_one(
            lambda day: archive_day(day, "eastmoney_https_unofficial"),
            Mock(side_effect=AssertionError("should not go online")),
        )
        self.assertEqual(result["archived_pairs_used"], 2)
        self.assertTrue(all(x["daily_fallback_used"] for x in rows))
        self.assertTrue(all(x["daily_source"] ==
                            "eastmoney_https_unofficial_unadjusted_daily_archive"
                            for x in rows))

    def test_cross_provider_archive_pair_reverts_to_coherent_network_series(self):
        archive = Mock(side_effect=lambda day: archive_day(
            day, "baostock" if day == DAY else "sina_close_snapshot"))
        network = Mock(side_effect=network_history)
        result, rows = self.run_one(archive, network)
        self.assertEqual(result["archived_pairs_used"], 0)
        self.assertEqual(result["appended"], 2)
        self.assertEqual(network.call_count, 1)  # cache per stock
        self.assertTrue(all(x["daily_source"] ==
                            "sina_unadjusted_daily" for x in rows))

    def test_archive_missing_and_network_down_stays_pending(self):
        network = Mock(side_effect=ConnectionError("all sources unavailable"))
        result, rows = self.run_one(
            lambda day: archive_day(day) if day == DAY else {"ok": False},
            network,
        )
        self.assertEqual(result["appended"], 0)
        self.assertEqual(result["archived_pairs_used"], 0)
        self.assertEqual(result["status"], "pending_or_data_gaps")
        self.assertEqual(rows, [])
        self.assertEqual(network.call_count, 1)

    def test_suspicious_quote_anchor_still_rejected(self):
        bad = {**SIGNAL, "candidates": [
            {**SIGNAL["candidates"][0], "price": 3.0},
        ]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "forward.json"
            result = update_forward([bad], path, NOW,
                                    daily_loader=lambda *a, **kw: network_history(),
                                    archive_loader=lambda day: archive_day(day))
        self.assertEqual(result["archived_pairs_used"], 0)
        self.assertEqual(result["appended"], 0)
        self.assertIn("signal_quote_anchor_mismatch", result["provider_errors"])


if __name__ == "__main__":
    unittest.main()
