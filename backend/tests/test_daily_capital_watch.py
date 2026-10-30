"""Daily watch selection and immutable history contracts."""
from datetime import datetime, date, timedelta
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from capital_watch import validate_archive, verify_append_only

spec = importlib.util.spec_from_file_location("daily_capital_watch", ROOT / "scripts/run_daily_capital_watch.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CN = ZoneInfo("Asia/Shanghai")


def bars(day="2026-10-13", count=85):
    end = date.fromisoformat(day)
    dates = []
    while len(dates) < count:
        if end.weekday() < 5:
            dates.append(end)
        end -= timedelta(days=1)
    dates.reverse()
    return [{"date": d.isoformat(), "open": 10, "close": 10,
             "high": 10.2, "low": 9.8, "volume": 10000} for d in dates]


class DailyCapitalWatchTests(unittest.TestCase):
    def test_automatic_workflow_retains_manual_query_task(self):
        tasks = json.loads((ROOT / "backend/data/tasks.json").read_text(encoding="utf-8"))["items"]
        by_id = {r["id"]: r for r in tasks}
        self.assertFalse(by_id["capital_behavior"]["enabled"])
        self.assertEqual(by_id["capital_behavior"]["execution_mode"], "app_only_on_demand")
        self.assertTrue(by_id["capital_watch_daily"]["enabled"])
        self.assertEqual(by_id["capital_watch_daily"]["timezone"], "Asia/Shanghai")

    def test_nontrading_session_does_not_scan(self):
        result = module.scan(now=datetime(2026,10,11,18,10,tzinfo=CN),pool=["002068"],
                             loader=lambda *args, **kw: self.fail("no market access"))
        self.assertEqual(result["status"], "skipped")

    def test_post_midnight_saturday_still_scans_friday(self):
        # GitHub Actions can start many hours late; a Friday run may
        # arrive after midnight Beijing time before any next session.
        delayed = datetime(2026, 10, 31, 0, 40, tzinfo=CN)
        codes = [f"60{i:04d}" for i in range(6)]
        result = module.scan(now=delayed, pool=codes,
                             loader=lambda *args, **kwargs: bars("2026-10-30"))
        self.assertEqual(result["date"], "2026-10-30")
        self.assertEqual(result["as_of"], delayed.isoformat(timespec="seconds"))
        self.assertEqual(result["status"], "no_matches")
        self.assertEqual(result["valid_daily"], 6)
        archive, changed = module.append_snapshot(
            {"schema_version": 1, "items": []}, result, "999001", published_at=delayed
        )
        self.assertTrue(changed)
        item = archive["items"][0]
        self.assertEqual(item["id"], "capital-watch-20261030-999001")
        self.assertEqual(item["published_at"], delayed.isoformat(timespec="seconds"))
        self.assertTrue(item["delayed_publication"])
        validate_archive(archive)

    def test_delay_window_cannot_replay_weekend_or_after_next_open(self):
        codes = ["600001"]
        for attempted in (datetime(2026, 11, 1, 0, 40, tzinfo=CN),
                          datetime(2026, 11, 2, 9, 30, tzinfo=CN)):
            result = module.scan(now=attempted, pool=codes,
                                 loader=lambda *args, **kwargs: self.fail("no market access"))
            self.assertEqual(result["status"], "skipped")
        with self.assertRaisesRegex(ValueError, "late_publish_outside_verified_session_window"):
            module.append_snapshot(
                {"schema_version": 1, "items": []},
                {"date": "2026-10-30", "status": "no_matches", "candidates": []},
                "999002", published_at=datetime(2026, 11, 2, 9, 30, tzinfo=CN)
            )

    def test_no_yesterday_bar_may_pass_today(self):
        result = module.scan(now=datetime(2026,10,14,18,10,tzinfo=CN),
                             pool=["002068"]*7,
                             loader=lambda *args,**kw: bars("2026-10-13"))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["candidates"], [])

    def test_minimum_evidence_and_no_forced_five_picks(self):
        codes = [f"60{i:04d}" for i in range(6)]
        result = module.scan(now=datetime(2026,10,13,18,10,tzinfo=CN),
                             pool=codes,loader=lambda *args,**kw: bars())
        self.assertEqual(result["scanned"],6)
        self.assertEqual(result["valid_daily"],6)
        self.assertEqual(result["status"],"no_matches")
        self.assertEqual(result["candidates"], [])

    def test_more_than_five_scored_observations_are_capped(self):
        from unittest.mock import patch
        codes = [f"60{i:04d}" for i in range(9)]
        def fake_assess(code, day, now, loader):
            return "examined", {
                "code": code, "as_of": day, "stage": "accumulation_candidate",
                "score": 65, "source": "tencent_qfq_daily",
                "evidence": ["完整日线代理"], "risk": ["不是主力账户识别"],
            }
        with patch.object(module, "assess", side_effect=fake_assess):
            result = module.scan(now=datetime(2026,10,13,18,10,tzinfo=CN),
                                 pool=codes, loader=lambda *args, **kwargs: [])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["candidates"]), 5)
        self.assertEqual(result["matching_before_limit"], 9)

    def test_zero_matches_still_not_fabricated(self):
        from unittest.mock import patch
        codes = [f"60{i:04d}" for i in range(6)]
        with patch.object(module, "classify", return_value={"stage": "unconfirmed", "exploratory_score": 10}):
            result = module.scan(now=datetime(2026,10,13,18,10,tzinfo=CN),
                                 pool=codes, loader=lambda *args,**kw: bars())
        self.assertEqual(result["status"],"no_matches")
        self.assertEqual(result["candidates"],[])

    def test_append_history_cannot_be_mutated(self):
        t = datetime(2026,10,13,18,11,tzinfo=CN)
        info = module.scan(now=t,pool=["600001"]*6,
                           loader=lambda *args,**kw: bars())
        # A single unique valid code is insufficient and produces a blocked receipt.
        before = {"schema_version":1,"items":[]}
        after,changed = module.append_snapshot(before, info, "1234",published_at=t)
        self.assertTrue(changed)
        self.assertEqual(after["items"][0]["status"],"blocked")
        validate_archive(after)
        again,changed2 = module.append_snapshot(after,info,"1234",published_at=t)
        self.assertFalse(changed2)
        self.assertEqual(again,after)
        copy = json.loads(json.dumps(after))
        copy["items"][0]["status"] = "no_matches"
        with self.assertRaises(ValueError):
            verify_append_only(after,copy)


if __name__ == "__main__":
    unittest.main()
