"""Regressions for unavailable history, stale backup quotes and report publication."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import intraday_scheduler as scheduler
from daily_providers import sina_daily
from daily_results import daily_results, report_detail
from daily_snapshot import read_snapshot
from delivery_health import resident_intraday_health
from quote_providers import parse_sina_quotes
from sina_snapshot import parse_close_snapshot

CN = ZoneInfo("Asia/Shanghai")


def sina_line(stamp="2026-11-05,15:34:59"):
    values = ["浦发银行", "10.09", "10.09", "9.87", "10.1", "9.82", "9.87", "9.88", "62907781", "623425673"]
    values += ["0"] * 20 + stamp.split(",") + ["00"]
    return 'var hq_str_sh600000="' + ",".join(values) + '";'


class ReliabilityTests(unittest.TestCase):
    def test_sina_quote_has_real_time_without_inventing_ratios(self):
        row = parse_sina_quotes(sina_line(), ["sh600000"])[0]
        self.assertEqual(row["as_of"], "2026-11-05T15:34:59+08:00")
        self.assertEqual(row["price"], 9.87)
        self.assertAlmostEqual(row["pct"], -2.18)
        self.assertIsNone(row["turnover"])
        self.assertIsNone(row["volume_ratio"])

    def test_close_snapshot_rejects_intraday_and_wrong_date_and_preserves_units(self):
        args = (["sh.600000"], "2026-11-05")
        self.assertEqual(parse_close_snapshot(sina_line("2026-11-05,14:59:59"), *args), [])
        self.assertEqual(parse_close_snapshot(sina_line("2026-11-04,15:05:00"), *args), [])
        row = parse_close_snapshot(sina_line(), *args)[0]
        self.assertEqual(row["volume"], 62907781)
        self.assertEqual(row["amount"], 623425673)
        self.assertEqual(row["volume_unit"], "shares")

    def test_sina_daily_requires_callback_segment(self):
        client = Mock()
        client.get.return_value.text = 'var _robin=([{"day":"2026-11-05","open":"10.09","close":"9.87","low":"9.82","high":"10.1","volume":"62907781"}]);'
        rows = sina_daily("600000", client=client)
        self.assertEqual(rows[0]["date"], "2026-11-05")
        self.assertIn("/var%20_robin=/CN_MarketDataService", client.get.call_args.args[0])

    def test_real_quote_backup_replaces_stale_primary_but_not_with_stale_backup(self):
        now = datetime(2026, 11, 6, 9, 50, tzinfo=CN)
        row = {"code": "600000", "name": "浦发银行", "price": 10, "pct": 1,
               "source": "sina_public", "as_of": now.isoformat()}
        stale = dict(row, as_of=(now - timedelta(days=1)).isoformat())
        with patch.object(scheduler, "tencent_quotes", return_value=[stale]), patch.object(
                scheduler, "sina_quotes", return_value=[row]) as backup:
            found, _ = scheduler._fresh_quotes(["600000"], now)
        self.assertEqual(found, [row])
        backup.assert_called_once_with(["sh600000"])
        with patch.object(scheduler, "tencent_quotes", side_effect=requests.Timeout()), patch.object(
                scheduler, "sina_quotes", return_value=[stale]):
            self.assertEqual(scheduler._fresh_quotes(["600000"], now)[0], [])

    def test_all_history_failures_do_not_erase_timestamped_observation_pair(self):
        now = datetime(2026, 11, 6, 9, 50, tzinfo=CN)
        quotes = [{"code": f"60000{i}", "name": "测试股票", "price": 10, "pct": i - 2,
                   "source": "sina_public", "as_of": now.isoformat(),
                   "turnover": 3, "volume_ratio": 2} for i in range(5)]
        with patch.object(scheduler, "_candidate", side_effect=ValueError("primary down")), patch.object(
                scheduler, "_relative_shadow_candidate", side_effect=ValueError("history down")):
            result = scheduler.execute("early_pair", now,
                universe_loader=lambda: ([r["code"] for r in quotes], {}, []),
                quote_loader=lambda codes, at: (quotes, []))
        self.assertEqual(result["status"], "observed")
        self.assertEqual(len(result["candidates"]), 2)
        self.assertEqual(result["quote_only_shadow_count"], 2)
        self.assertTrue(all(r["daily_source"] is None and r["buy_order_allowed"] is False
                            and r["as_of"] == now.isoformat() for r in result["candidates"]))
        self.assertIn("all_strict_daily_validation_failed", result["provider_errors"])

    def test_empty_record_does_not_pass_new_pair_delivery_requirement(self):
        now = datetime(2026, 11, 6, 15, 30, tzinfo=CN)
        def source(slot):
            return {"ok": True, "storage": "railway_persistent_volume", "store_writable": True,
                    "latest": {"date": "2026-11-06", "status": "no_signal", "candidates": []}}
        result = resident_intraday_health(now=now, provider=source)
        self.assertEqual(result["status"], "incomplete")
        self.assertTrue(all(r["required_candidate_count"] == 2 and not r["research_observation_delivered"]
                            for r in result["items"]))


class DailyResultIndexTests(unittest.TestCase):
    def documents(self):
        return ({"items": [{"id": "market_review", "title": "复盘"}, {"id": "volume_price", "title": "量价"}]},
                {"items": []}, {"items": [
                    {"id": "partial-today", "date": "2026-11-05", "task_id": "market_review",
                     "title": "补做报告", "summary": "实质部分成果", "body": "全文", "status": "partial"},
                    {"id": "yesterday", "date": "2026-11-04", "task_id": "volume_price",
                     "title": "昨天报告", "body": "旧全文", "status": "completed"}]})

    def test_published_partial_is_not_completed_and_old_reports_do_not_fill_today(self):
        data = daily_results("2026-11-05", documents=self.documents())
        self.assertEqual(data["published_count"], 1)
        self.assertEqual(data["completed_count"], 0)
        self.assertEqual(data["items"][1]["status"], "missing")
        self.assertNotIn("body", data["items"][0])
        self.assertEqual(data["items"][0]["detail_path"], "/api/research/partial-today")
        self.assertTrue(data["items"][0]["recovery_required"])

    def test_summary_paginates_and_full_report_is_retrieved_separately(self):
        data = daily_results("2026-11-05", limit=1, documents=self.documents())
        self.assertTrue(data["has_more"])
        self.assertEqual(data["total"], 2)
        self.assertEqual(report_detail("partial-today", reports=self.documents()[2])["report"]["body"], "全文")
        self.assertIsNone(report_detail("missing", reports=self.documents()[2]))

    def test_real_full_backup_is_usable_when_primary_archives_are_missing(self):
        import tempfile
        import shutil
        source = Path(__file__).resolve().parents[1] / "data/sina_daily_full/2026-11-05.json"
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "sina_daily_full"
            target.mkdir()
            shutil.copy(source, target)
            data = read_snapshot("2026-11-05", folder)
        self.assertTrue(data["ok"] and data["fallback_used"])
        self.assertEqual(data["provider"], "sina_close_snapshot")
        self.assertEqual(data["coverage"]["verified"], 5217)


if __name__ == "__main__":
    unittest.main()
