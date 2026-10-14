"""Intraday live evidence collector and non-actionable observations."""
import importlib.util
from datetime import datetime
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import Mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


collect = load("collect_intraday_feed.py", "collect_intraday_feed")
gate = load("run_intraday_research.py", "intraday_evaluator")
observe = load("publish_intraday_observation.py", "observation_writer")
CN = ZoneInfo("Asia/Shanghai")


class TestIntradayEvidence(unittest.TestCase):
    def test_live_tencent_quote_parses_source_timestamp_and_amount(self):
        f = [""] * 72
        for idx, value in {1:"样本证券",2:"600001",3:"10.50",4:"10.00",
                           6:"100000",30:"20261014144000",32:"5.00",
                           37:"15200",38:"10.00",49:"2.1"}.items():
            f[idx] = value
        rows = collect.parse_tencent('v_sh600001="' + "~".join(f) + '";', ["sh600001"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["turnover"], 152000000)
        self.assertEqual(rows[0]["as_of"], "2026-10-14T14:40:00+08:00")
        self.assertEqual(rows[0]["previous_close"], 10)
        self.assertEqual(rows[0]["source"], "https://qt.gtimg.cn/q=sh600001")

    def test_stale_row_is_not_validated_by_newest_quote(self):
        now = datetime(2026, 10, 14, 14, 40, tzinfo=CN)
        base = {"code":"600001","name":"证券", "market":"SH","price":10.5,
                "previous_close":10.0,"volume":100000,"turnover":152000000,
                "turnover_ratio":10.0,"pct":5,"as_of":"2026-10-14T14:30:00+08:00",
                "source":"https://qt.gtimg.cn/q=sh600001"}
        feed = {"source":"https://qt.gtimg.cn/q=sh600001", "as_of":now.isoformat(),
                "quotes":[base]}
        out = gate.evaluate("late_pair",now,feed)
        self.assertEqual(out["reason"],"stale_or_future_snapshot")

    def test_actual_watch_is_not_an_actionable_recommendation(self):
        now = datetime(2026, 10, 14, 14, 40, tzinfo=CN)
        row = {"code":"600001","name":"证券","market":"SH","price":10.5,
               "previous_close":10,"volume":100000,"turnover":152000000,
               "turnover_ratio":10,"pct":5,"volume_ratio":1.5,
               "as_of":now.isoformat(), "source":"https://qt.gtimg.cn/q=sh600001"}
        feed = {"source":row["source"],"as_of":now.isoformat(),"quotes":[row],
                "scope":"research_watchlist_only","requested_count":1}
        out = gate.evaluate("late_pair",now,feed)
        self.assertEqual(len(out["candidate_watch"]),1)
        self.assertEqual(out["recommendations"],[])
        self.assertEqual(out["reason"],"screened_watch_not_validated_strategy")
        rep,id,changed = observe.append_observation({"schema_version":1,"items":[]},out,"12345")
        self.assertTrue(changed)
        self.assertEqual(rep["items"][0]["candidate_count"],1)
        self.assertIn("非荐股",rep["items"][0]["body"])
        self.assertEqual(id,"intraday-watch-20261014-late_pair-gh12345")

    def test_provider_failure_never_fabricates(self):
        client = Mock()
        client.get.side_effect = RuntimeError("network bad")
        # Only requests errors are caught; an unexpected failure must alert CI.
        with self.assertRaises(RuntimeError):
            collect.gather(datetime(2026,10,14,14,40,tzinfo=CN),client=client)

    def test_bse_avoids_wrong_limit_rules(self):
        row={"code":"920001","name":"样本","price":12,"pct":9,"turnover":200000000,
             "turnover_ratio":15,"volume_ratio":2}
        self.assertEqual(gate.watch_candidates([row]),[])


if __name__ == "__main__":
    unittest.main()
