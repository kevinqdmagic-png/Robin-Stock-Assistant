import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from entry_alerts import scheduled_recommendations, evaluate_entry_alerts

NOW = datetime(2026, 10, 19, 10, 2, tzinfo=ZoneInfo("Asia/Shanghai"))
BASE = {
    "id": "test-000887", "date": "2026-10-16", "code": "000887",
    "name": "中鼎股份", "strategy": "combined_limitup_watch",
    "provenance": "contemporaneous", "planned_entry_date": "2026-10-19",
    "entry_price_condition_range": [17.8, 18.05],
    "invalid_level": 17.2, "trigger": "多项分时与行业核验",
}


class EntryAlertTests(unittest.TestCase):
    def test_scheduled_priority_and_date(self):
        lower = dict(BASE, id="lower", strategy="market_review_conditional",
                     reference_entry_range=[17.8, 18.05])
        old = dict(BASE, id="old", planned_entry_date="2026-10-16")
        selected = scheduled_recommendations([lower, old, BASE], "2026-10-19")
        self.assertEqual([row["id"] for row in selected], ["test-000887"])

    def test_price_zone_requires_fresh_live_quote_and_valid_range(self):
        quote = {"code": "000887", "price": 17.92, "as_of": "2026-10-19T10:01:30+08:00",
                 "source": "eastmoney_public", "pct": 3.0}
        rows = evaluate_entry_alerts([BASE], [quote], NOW, session_live=True)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["all_conditions_verified"])
        self.assertEqual(rows[0]["level"], "price_zone")
        self.assertEqual(evaluate_entry_alerts([BASE], [quote], NOW, False), [])
        self.assertEqual(evaluate_entry_alerts([BASE], [dict(quote, price=18.3)], NOW, True), [])
        self.assertEqual(evaluate_entry_alerts([BASE], [dict(quote, as_of="2026-10-19T09:50:00+08:00")], NOW, True), [])
        self.assertEqual(evaluate_entry_alerts([BASE], [dict(quote, as_of="2026-10-16T14:57:00+08:00")], NOW, True), [])

    def test_contemporaneous_close_research_is_monitored_on_planned_day(self):
        # Older publication with a valid planned entry day must not disappear
        # just because it was labeled a close-session research recommendation.
        close = dict(BASE, id="market-300825", code="300825",
                     strategy="market_review_conditional",
                     provenance="contemporaneous_close_research")
        today = scheduled_recommendations([BASE, close], "2026-10-19")
        self.assertEqual({row["code"] for row in today}, {"000887", "300825"})
        # Only the market review strategy has this provenance contract.
        inconsistent = dict(close, strategy="combined_limitup_watch")
        self.assertEqual(scheduled_recommendations([inconsistent], "2026-10-19"), [])

    def test_outdated_and_unverifiable_recommendations_never_alert(self):
        self.assertEqual(scheduled_recommendations([dict(BASE, provenance="historical")], "2026-10-19"), [])
        self.assertEqual(scheduled_recommendations([dict(BASE, entry_price_condition_range=None)], "2026-10-19"), [])
        self.assertEqual(evaluate_entry_alerts([dict(BASE, planned_entry_date="2026-10-20")],
            [{"code": "000887", "price": 17.9, "as_of": "2026-10-19T10:02:00+08:00"}], NOW, True), [])


if __name__ == "__main__":
    unittest.main()
