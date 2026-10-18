import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from entry_confirmation import assess

NOW = datetime(2026, 10, 19, 9, 55, tzinfo=ZoneInfo("Asia/Shanghai"))
R = {"version":"combined_limitup_watch_v5","entry_sequence_required":True,
     "entry_window_cn":["09:45","10:30"],"auction_open_range":[17.4,18.1],
     "pullback_range":[17.35,17.6],"pullback_floor":17.3,"reclaim":17.78,
     "hold_minute_price_points":5,"peer_codes":["000099","002085"],
     "peers_each_min_change_pct":-2,"at_least_one_peer_positive":True,
     "same_scope_advance_min":2800,"ordinary_mainboard_limit_down_max":14}
Q = {"code":"000887","price":17.92,"pct":3,"as_of":"2026-10-19T09:54:30+08:00"}
P = [{"code":"000099","price":10,"pct":1,"as_of":Q["as_of"]},
     {"code":"002085","price":10,"pct":-1,"as_of":Q["as_of"]}]


def minute():
    bars=[]
    for m in range(30,55):
        price,vol=(17.75,8) if m<40 else (17.85,10) if m<45 else (17.50,3) if m<50 else (17.89,12)
        bars.append({"time":"2026-10-19 09:%02d"%m,"open":price,
                     "high":price+.01,"low":price-.01,
                     "close":price,"volume":vol})
    return {"ok":True,"stale":False,"refreshing":False,
            "source":"eastmoney_trends","bars":bars}


class ConfirmationTests(unittest.TestCase):
    def check(self,m=None,p=None):
        return assess({"rules":R},Q,m or minute(),P if p is None else p,
                      {"breadth_complete":False},NOW)

    def test_partial_pass_never_claims_everything_verified(self):
        check=self.check()
        self.assertTrue(check["technical_confirmed"])
        self.assertFalse(check["all_conditions_verified"])
        gates={x["key"]:x["status"] for x in check["gates"]}
        self.assertEqual(gates["minute_volume_reclaim"],"passed")
        self.assertEqual(gates["auction"],"unknown")

    def test_stale_and_unverified_minute_never_confirm(self):
        old=minute()
        old["source"]="tencent_minute"
        self.assertFalse(self.check(m=old)["technical_confirmed"])
        old=minute()
        old["bars"][-1]["time"]="2026-10-18 09:54"
        self.assertFalse(self.check(m=old)["technical_confirmed"])

    def test_peer_time_and_volume_fail_closed(self):
        bad=[dict(P[0],as_of="2026-10-18T09:54:30+08:00"),P[1]]
        self.assertFalse(self.check(p=bad)["technical_confirmed"])
        bad=minute()
        for row in bad["bars"][15:20]:
            row["volume"]=50
        self.assertFalse(self.check(m=bad)["technical_confirmed"])

    def test_unstructured_plan_not_machine_confirmable(self):
        result=assess({"trigger":"文字条件"},Q,minute(),P,{},NOW)
        self.assertFalse(result["technical_confirmed"])
        self.assertFalse(result["supported"])


if __name__=="__main__":
    unittest.main()
