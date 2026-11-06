import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_recovery import recovery_backlog

CN = ZoneInfo("Asia/Shanghai")


def documents(completed_day=None):
    tasks = {"items": [{"id": "market_review", "title": "Market", "enabled": True}]}
    runs, reports = {"items": []}, {"items": []}
    if completed_day:
        reports["items"].append({"id": "full-report", "task_id": "market_review", "date": completed_day,
            "status": "completed", "analysis_completed": True, "eligible_for_integrated_research": True,
            "report_type": "full_daily_research", "body": "Full research", "sources": ["source"]})
        runs["items"].append({"id": "run", "task_id": "market_review", "date": completed_day,
            "status": "completed", "analysis_completed": True, "report_ids": ["full-report"],
            "recorded_at": completed_day + "T21:00:00+08:00"})
    return tasks, runs, reports


class ResearchRecoveryTests(unittest.TestCase):
    def test_older_missing_work_survives_newer_completion_and_weekend(self):
        data = documents("2026-11-06")
        result = recovery_backlog("2026-11-05", documents=data,
                                  now=datetime(2026, 11, 7, 2, tzinfo=CN))
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["date"], "2026-11-05")
        later = recovery_backlog("2026-11-05", documents=data,
                                 now=datetime(2026, 11, 8, 2, tzinfo=CN))
        self.assertEqual(later["total"], 1)
        self.assertFalse(later["obligations_expire_on_date_change"])
        self.assertFalse(later["automatically_executing"])

    def test_only_same_day_full_completion_removes_obligation(self):
        data = documents("2026-11-05")
        now = datetime(2026, 11, 6, 2, tzinfo=CN)
        self.assertEqual(recovery_backlog("2026-11-05", documents=data, now=now)["total"], 0)
        data[1]["items"][0]["status"] = "partial"
        self.assertEqual(recovery_backlog("2026-11-05", documents=data, now=now)["total"], 1)

    def test_next_morning_tasks_are_pending_before_their_actual_due_time(self):
        data = documents()
        data[0]["items"] += [{"id": task, "title": task, "enabled": True,
                              "recovery_due_local_time": hour,
                              "recovery_due_timezone": "Pacific/Auckland"}
                             for task, hour in [("learning_review", "08:00"), ("combined_pair", "09:00")]]
        result = recovery_backlog("2026-11-06", documents=data,
                                  now=datetime(2026, 11, 7, 2, tzinfo=CN))
        self.assertEqual({r["task_id"] for r in result["pending_not_yet_due"]},
                         {"learning_review", "combined_pair"})
        self.assertEqual({r["task_id"] for r in result["items"]}, {"market_review"})
        after = recovery_backlog("2026-11-06", documents=data,
                                 now=datetime(2026, 11, 7, 5, tzinfo=CN))
        self.assertEqual(after["total"], 3)


if __name__ == "__main__":
    unittest.main()
