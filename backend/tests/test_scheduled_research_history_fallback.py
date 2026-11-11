"""Tencent daily 501 must not make the after-close sample silently empty."""
import importlib.util
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
spec = importlib.util.spec_from_file_location(
    "scheduled_history_fallback", ROOT / "scripts/run_scheduled_research.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
CN = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 11, 11, 0, 20, tzinfo=CN)


def sample():
    d = date(2026, 8, 1)
    final = date(2026, 11, 10)
    rows = []
    while d <= final:
        day = d.isoformat()
        if d.weekday() < 5 and not ("2026-10-01" <= day <= "2026-10-07"):
            recent = day == "2026-11-10"
            rows.append({"date": day, "open": 10, "close": 10.18 if recent else 10,
                         "high": 10.2, "low": 9.9, "volume": 400 if recent else 200})
        d += timedelta(days=1)
    assert len(rows) > 60
    return rows


class ScheduledHistoryFallbackTests(unittest.TestCase):
    def test_tencent_outage_uses_one_coherent_raw_series(self):
        candles = sample()
        with patch.object(mod, "tencent_daily",
                          side_effect=requests.HTTPError("501")) as primary, \
             patch.object(mod, "historical_daily_with_fallback",
                          return_value={"rows": candles, "provider": "sina",
                                        "adjustment": "0",
                                        "fallback_used": True}) as backup:
            row = mod.analyze_one("600101", NOW, research_day="2026-11-10")
            primary.assert_called_once()
            backup.assert_called_once_with("600101", limit=125, adjust="0")
        self.assertEqual(row["date"], "2026-11-10")
        self.assertEqual(row["adjustment"], "none")
        self.assertEqual(row["provider"], "sina_daily")
        self.assertTrue(row["fallback_used"])
        self.assertGreater(row["relative_volume20"], 1.5)

    def test_raw_fallback_is_not_disguised_as_old_qfq_signal(self):
        with patch.object(mod, "read_snapshot", return_value={"ok": False}), \
             patch.object(mod, "tencent_daily",
                          side_effect=requests.HTTPError("501")), \
             patch.object(mod, "historical_daily_with_fallback",
                          return_value={"rows": sample(), "provider": "sina",
                                        "adjustment": "0", "fallback_used": True}):
            snapshot = mod.collect(
                NOW, pool=[str(600101+i) for i in range(12)],
                quote_provider=lambda _: [],
                recover_latest_completed=True, workers=2,
            )
        self.assertEqual(snapshot["fresh"], 12)
        self.assertEqual(snapshot["day"], "2026-11-10")
        low = next(r for r in mod.build_reports(snapshot, NOW)
                   if r["task_id"] == "low_position")
        self.assertEqual(low["run_status"], "partial")
        self.assertEqual(low["signal_observations"], [])
        self.assertEqual(low["raw_fallback_samples_excluded_from_frozen_qfq_signals"], 12)
        self.assertIn("未复权12只", low["body"])

    def test_original_qfq_series_preserves_frozen_shape_model(self):
        with patch.object(mod, "tencent_daily", return_value=sample()), \
             patch.object(mod, "historical_daily_with_fallback") as other:
            row = mod.analyze_one("600101", NOW, research_day="2026-11-10")
        other.assert_not_called()
        self.assertEqual(row["adjustment"], "qfq")
        self.assertEqual(row["provider"], "tencent_daily")
        self.assertFalse(row["fallback_used"])


if __name__ == "__main__":
    unittest.main()
