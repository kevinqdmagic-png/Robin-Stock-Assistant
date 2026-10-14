"""An actual scheduled evidence attempt is not the same as a completed recommendation."""
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
spec = importlib.util.spec_from_file_location("scheduled_research", ROOT / "scripts/run_scheduled_research.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
CN = ZoneInfo("Asia/Shanghai")


class ScheduledResearchTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 15, 18, 17, tzinfo=CN)
        self.registry = {"items": [{"id": t} for t in mod.TASKS]}
        self.reports = {"schema_version": 1, "items": []}
        self.runs = {"schema_version": 1, "items": []}

    @staticmethod
    def daily(code, limit=125, adjust="1"):
        base = datetime(2026, 9, 1, tzinfo=CN)
        dates = [(base + timedelta(days=j)).date() for j in range(45)]
        rows = []
        for day in dates:
            if day.weekday() < 5 and not (day.month == 10 and 1 <= day.day <= 7):
                rows.append({"date": day.isoformat(), "open": 10.0, "close": 10.1,
                             "high": 10.2, "low": 9.9, "volume": 200})
        # 2026-10-15 included and no invented future candle.
        return rows

    @staticmethod
    def quotes(symbols):
        return [{"code": x[-6:], "name": x, "price": 100.0, "pct": 0.5,
                 "as_of": "2026-10-15T15:00:00+08:00",
                 "source": "tencent_public"} for x in symbols]

    def test_date_gate_prevents_premarket_or_holiday_replays(self):
        for date in (datetime(2026, 10, 15, 9, 30, tzinfo=CN),
                     datetime(2026, 10, 6, 18, 17, tzinfo=CN)):
            with self.subTest(date=date):
                snapshot = mod.collect(date, pool=["600001"], day_provider=self.daily,
                                       quote_provider=self.quotes)
                self.assertFalse(snapshot["eligible"])

    def test_source_coverage_and_no_executable_claims(self):
        pool = [str(600001 + i) for i in range(14)]
        snapshot = mod.collect(self.now, pool=pool, day_provider=self.daily,
                               quote_provider=self.quotes, workers=2)
        self.assertEqual(snapshot["fresh"], 14)
        self.assertEqual(len(snapshot["indexes"]), 4)
        self.assertFalse(snapshot["full_a_share_coverage"])
        reports, runs, info = mod.stage(self.reports, self.runs, self.registry, snapshot, "12345", self.now)
        self.assertEqual(info["statuses"], {"market_review": "partial", "volume_price": "partial",
                                             "limitup_single": "partial", "combined_pair": "waiting", "low_position": "partial"})
        self.assertEqual(len(reports["items"]), 5)
        self.assertEqual(len(runs["items"]), 5)
        self.assertTrue(all(not r["analysis_completed"] for r in runs["items"]))
        self.assertTrue(all(not r["eligible_for_integrated_research"] for r in runs["items"]))
        self.assertTrue(all(not r["report_ids"] == [] for r in runs["items"]))
        self.assertEqual(mod.stage(reports, runs, self.registry, snapshot, "12345", self.now)[2]["changed_reports"], False)
        more = mod.stage(reports, runs, self.registry, snapshot, "12346", self.now)[1]
        self.assertEqual(len(more["items"]), 10)

    def test_provider_outage_creates_blocked_evidence_not_fake_picks(self):
        snapshot = {"eligible": True, "day": "2026-10-15", "indexes": [],
                    "checked": 14, "fresh": 0, "observations": [],
                    "errors": {"index_quote_Timeout": 1},
                    "universe": "limited", "full_a_share_coverage": False}
        _, runs, info = mod.stage(self.reports, self.runs, self.registry, snapshot, "12347", self.now)
        self.assertEqual(info["statuses"]["volume_price"], "blocked")
        self.assertEqual(info["statuses"]["combined_pair"], "waiting")
        self.assertEqual(info["statuses"]["low_position"], "blocked")
        self.assertFalse(any(row["status"] == "completed" for row in runs["items"]))


if __name__ == "__main__":
    unittest.main()
