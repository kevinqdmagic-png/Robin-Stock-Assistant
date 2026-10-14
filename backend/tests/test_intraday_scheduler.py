"""Production resident intraday runner: schedule, timestamp, persistence."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import intraday_scheduler as module
CN = ZoneInfo("Asia/Shanghai")


def q(code, now):
    return {"code":code, "name":"测试证券", "pct":5, "price":12.3,
            "as_of":now.isoformat(timespec="seconds"),
            "volume_ratio":1.8,"turnover":6.5,"source":"tencent_public"}


class IntradaySchedulerTests(unittest.TestCase):
    def test_day_closed_no_market_fetch(self):
        with patch.object(module, "target_universe") as fetch:
            self.assertIsNone(module.execute("late_pair", datetime(2026,10,11,14,40,tzinfo=CN)))
            fetch.assert_not_called()

    def test_1440_partial_real_observation_not_recommendation(self):
        at=datetime(2026,10,14,14,40,tzinfo=CN)
        codes=[f"60{i:04d}" for i in range(8)]
        def get_universe():
            return codes, {}, []
        def get_quotes(cs,now):
            return [q(c,now) for c in cs], []
        def get_signal(stock, date, now):
            return {"code":stock["code"],"score":61,"name":stock["name"],
                    "as_of":now.isoformat(),"signal_validated":False}
        outcome=module.execute("late_pair",at,get_universe,get_quotes,get_signal)
        self.assertEqual(outcome["status"],"observed")
        self.assertEqual(len(outcome["candidates"]),2)
        self.assertFalse(outcome["strategy_validated"])
        self.assertEqual(outcome["fresh_quotes"],8)

    def test_no_signal_is_successful_empty_observation(self):
        at=datetime(2026,10,14,14,40,tzinfo=CN)
        codes=[f"60{i:04d}" for i in range(8)]
        o=module.execute("late_pair",at,lambda:(codes,{},[]),
                         lambda codes,now:([q(c,now) for c in codes],[]),
                         lambda stock,day,now:None)
        self.assertEqual(o["status"],"no_signal")
        self.assertEqual(o["candidates"],[])

    def test_not_enough_fresh_quotes_returns_blocked_and_attempts(self):
        at=datetime(2026,10,14,14,40,tzinfo=CN)
        codes=[f"60{i:04d}" for i in range(8)]
        o=module.execute("late_pair",at,lambda:(codes,{},[]),lambda cs,n:([],["outage"]))
        self.assertEqual(o["status"],"blocked")
        self.assertEqual(o["reason_code"],"insufficient_fresh_quotes")

    def test_volume_parent_precreated_and_atomic_write_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            location=Path(folder)/"nested"/"intraday.json"
            with patch.object(module, "STORE", location):
                self.assertTrue(module.storage_ready())
                self.assertTrue(location.parent.is_dir())
                self.assertEqual(list(location.parent.iterdir()), [])

    def test_persist_atomic_and_historical_record_protected(self):
        now=datetime(2026,10,14,14,40,tzinfo=CN)
        with tempfile.TemporaryDirectory() as folder, patch.object(module, "STORE", Path(folder)/"runs.json"):
            first={"task_id":"late_pair","date":"2026-10-14","status":"blocked",
                   "started_at":now.isoformat(),"attempt":1,"candidates":[]}
            self.assertTrue(module.persist(first))
            self.assertFalse(module.persist(first))
            accepted=dict(first, status="observed", attempt=2)
            self.assertTrue(module.persist(accepted))
            self.assertFalse(module.persist(dict(first, attempt=3)))
            self.assertEqual(module.latest("late_pair",now=now)["latest"]["status"],"observed")

    def test_pre_deadline_has_scheduled_state(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(module,"STORE",Path(folder)/"runs.json"):
            result=module.latest("late_pair",now=datetime(2026,10,14,14,38,tzinfo=CN))
        self.assertEqual(result["current_status"],"scheduled")


if __name__=="__main__":
    unittest.main()
