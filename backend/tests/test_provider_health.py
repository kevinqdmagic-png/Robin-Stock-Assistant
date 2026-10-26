import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import provider_health as ph

NOW = datetime(2026, 10, 27, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


class ProviderHealthTests(unittest.TestCase):
    def setUp(self):
        with ph._guard:
            ph._events.clear()

    def test_empty_provider_is_unavailable_not_success(self):
        event = ph.record_provider_event("quote_batch", 4, [], None, ["HTTPError"], now=NOW)
        self.assertEqual(event["status"], "unavailable")
        self.assertEqual(ph.quality_summary()["by_kind"]["quote_batch"]["unavailable"], 1)

    def test_partial_fallback_records_degraded(self):
        quote = {"as_of": "2026-10-27T09:59:30+08:00"}
        event = ph.record_provider_event("quote_batch", 2, [quote], "tencent_batch_quote",
                                         ["eastmoney_batch:HTTPError"], now=NOW)
        self.assertEqual(event["status"], "degraded")
        self.assertEqual(event["returned"], 1)

    def test_stale_quote_never_counted_healthy(self):
        quote = {"as_of": "2026-10-26T14:00:00+08:00"}
        event = ph.assess_event("quote_batch", 1, [quote], "eastmoney_batch_quote", [], now=NOW)
        self.assertEqual(event["stale_quotes"], 1)
        self.assertEqual(event["status"], "degraded")

    def test_undated_quote_must_not_count_as_fresh(self):
        event = ph.assess_event("quote_batch", 1, [{"price": 5}], "other", [], now=NOW)
        self.assertEqual(event["unknown_quote_timestamps"], 1)
        self.assertEqual(event["status"], "degraded")

    def test_recent_complete_provider_and_summary(self):
        row = {"as_of": NOW.isoformat()}
        ph.record_provider_event("quote_batch", 1, [row], "eastmoney_batch_quote", [], now=NOW)
        self.assertEqual(ph.quality_summary()["by_kind"]["quote_batch"]["ok"], 1)
        self.assertFalse(ph.quality_summary()["persistent_across_deployments"])

    def test_invalid_kind_rejected(self):
        with self.assertRaises(ValueError):
            ph.assess_event("broker", 1, [], None, [], now=NOW)


if __name__ == "__main__":
    unittest.main()
