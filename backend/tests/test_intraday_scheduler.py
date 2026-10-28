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


    def test_v2_prevents_high_ma_and_10day_extension(self):
        from unittest.mock import patch
        at = datetime(2026, 10, 14, 14, 40, tzinfo=CN)
        # Pre-signal daily bars: large enough 60-day range for fair position.
        from datetime import timedelta
        rows = []
        for i in range(65):
            d = (at.date() - timedelta(days=65-i)).isoformat()
            rows.append({"date": d, "open": 10, "close": 10,
                         "high": 11, "low": 8, "volume": 10000})
        normal = q("600101", at)
        normal.update(price=10.35, pct=2.8, volume_ratio=2.2)
        overheated = dict(normal, price=12.6, pct=5.1)
        with patch.object(module, "tencent_daily", return_value=rows):
            accepted = module._candidate(normal, at.date().isoformat(), at)
            rejected = module._candidate(overheated, at.date().isoformat(), at)
        self.assertIsNotNone(accepted)
        self.assertEqual(accepted["model_version"], "intraday_low_chase_shadow_v2")
        self.assertFalse(accepted["signal_validated"])
        self.assertFalse(accepted["buy_order_allowed"])
        self.assertIsNone(rejected)

    def test_v2_does_not_rank_gainers_first_and_archives_control(self):
        at = datetime(2026,10,14,9,50,tzinfo=CN)
        quotes = [dict(q(f"60{i:04d}",at),pct=2.0 + i*0.55,
                       volume_ratio=2, turnover=5) for i in range(8)]
        def choose(stock, day, now):
            if stock["pct"] >= 5.0:
                return None
            return {"code": stock["code"], "name": stock["name"], "price": stock["price"],
                    "as_of": now.isoformat(), "score": 15.0-stock["pct"],
                    "model_version": "intraday_low_chase_shadow_v2",
                    "signal_validated": False}
        result = module.execute("early_pair",at,lambda:([x["code"] for x in quotes],{},[]),
                                lambda cs,n:(quotes,[]),choose)
        self.assertEqual(result["model_version"], "intraday_low_chase_shadow_v2")
        self.assertEqual(result["status"], "observed")
        self.assertLess(result["candidates"][0]["score"], 16)
        self.assertTrue(result["momentum_control"])
        self.assertTrue(result["momentum_control"][0]["control_only"])
        self.assertNotIn(result["momentum_control"][0]["code"],
                         {v["code"] for v in result["candidates"]})

    def test_forward_tracking_matures_without_lookahead_or_fills(self):
        from intraday_forward import update_forward, forward_summary
        anchor = "2026-10-08"
        at = datetime(2026,10,14,16,10,tzinfo=CN)
        observed = {
            "date": anchor, "task_id": "early_pair", "status": "observed",
            "candidates": [{"code":"600101", "name":"观察票", "price":10,
                            "as_of":"2026-10-08T09:50:01+08:00",
                            "model_version":"intraday_low_chase_shadow_v2",
                            "quote_source":"tencent_public"}],
            "momentum_control": [],
        }
        candles = [
            {"date":anchor,"open":10,"close":10,"high":10.2,"low":9.8,"volume":1},
            {"date":"2026-10-09","open":10.3,"close":11,"high":11.1,"low":10,"volume":1},
            {"date":"2026-10-12","open":10,"close":9,"high":10,"low":8.8,"volume":1},
        ]
        def daily(code, limit, adjust):
            self.assertEqual(adjust,"0")
            return candles
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"forward.json"
            still_trading = update_forward([observed],path,
                datetime(2026,10,14,14,40,tzinfo=CN),daily_loader=daily)
            self.assertEqual(still_trading["appended"],0)
            first = update_forward([observed],path,at,daily_loader=daily)
            self.assertEqual(first["appended"],2)
            again = update_forward([observed],path,at,daily_loader=daily)
            self.assertEqual(again["appended"],0)
            summary = forward_summary(path,"early_pair")
            self.assertEqual(summary["total"],2)
            self.assertFalse(summary["strategy_validated"])
            self.assertTrue(all(x["executed_trade"] is False for x in summary["items"]))
            self.assertTrue(all(x["net_trade_return_pct"] is None for x in summary["items"]))
            self.assertEqual(sorted(x["price_change_from_quote_pct"] for x in summary["items"]),[-10,10])
            self.assertNotIn(5,[x["horizon"] for x in summary["items"]])

    def test_forward_tracker_rejects_unverified_adjustment(self):
        from intraday_forward import update_forward
        signal={"date":"2026-10-08","task_id":"late_pair","status":"observed",
            "candidates":[{"code":"600101","price":10,"name":"证券",
                "as_of":"2026-10-08T14:40:00+08:00"}]}
        candles=[
            {"date":"2026-10-08","open":19,"close":19,"high":20,"low":18,"volume":1},
            {"date":"2026-10-09","open":19,"close":20,"high":20,"low":18,"volume":1}
        ]
        with tempfile.TemporaryDirectory() as folder:
            result=update_forward([signal],Path(folder)/"f.json",
                datetime(2026,10,14,16,0,tzinfo=CN),
                daily_loader=lambda code,limit,adjust:candles)
            self.assertEqual(result["appended"],0)
            self.assertIn("signal_quote_anchor_mismatch",result["provider_errors"])


if __name__=="__main__":
    unittest.main()
