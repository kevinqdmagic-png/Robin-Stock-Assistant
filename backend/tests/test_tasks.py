import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from task_center import task_list, report_page, validate_registry, validate_runs, checked_receipt
from research_archive import verify_append_only
import app as api

TASKS = {"updated_at": "2026-10-01T08:40:17+13:00", "items": [
    {"id": "volume_price", "title": "量价", "track": "volume_price", "schedule": "daily", "timezone": "Pacific/Auckland"},
    {"id": "combined_pair", "title": "综合双标", "track": "market_review", "schedule": "daily", "timezone": "Pacific/Auckland"}]}
REPORT = {"id": "r", "date": "2026-09-30", "task_id": "volume_price", "track": "volume_price", "title": "量价", "body": "facts"}
EVENT = {"id": "e", "run_id": "run", "task_id": "volume_price", "date": "2026-09-30",
         "started_at": "2026-09-30T21:00:00+13:00", "recorded_at": "2026-09-30T21:20:00+13:00",
         "completed_at": "2026-09-30T21:20:00+13:00", "trigger": "scheduled",
         "status": "completed", "report_ids": ["r"]}


def loader(runs=None, reports=None):
    documents = {"tasks.json": TASKS, "task_runs.json": {"items": runs or []},
                 "research.json": {"items": reports or []}}
    return lambda name, env=None: copy.deepcopy(documents[name])


class TaskTests(unittest.TestCase):
    def test_schedule_does_not_fabricate_execution(self):
        with patch("task_center.load_document", side_effect=loader()):
            rows = task_list()["items"]
        self.assertIsNone(rows[0]["last_run"])

    def test_legacy_report_is_not_current_completion(self):
        legacy = dict(REPORT); legacy.pop("task_id")
        with patch("task_center.load_document", side_effect=loader(reports=[legacy])):
            task = task_list()["items"][0]
        self.assertEqual(task["report_count"], 1)
        self.assertIsNone(task["last_run"])

    def test_completion_requires_linked_report_from_same_task(self):
        result = checked_receipt(EVENT, {"items": []})
        self.assertEqual(result["status"], "report_missing")
        wrong = dict(REPORT, task_id="combined_pair")
        self.assertEqual(checked_receipt(EVENT, {"items": [wrong]})["status"], "report_missing")
        wrong_date = dict(REPORT, date="2026-09-29")
        self.assertEqual(checked_receipt(EVENT, {"items": [wrong_date]})["status"], "report_missing")
        self.assertEqual(checked_receipt(EVENT, {"items": [REPORT]})["status"], "completed")

    def test_latest_event_and_report_link(self):
        earlier = dict(EVENT, id="started", status="running", recorded_at=EVENT["started_at"], report_ids=[])
        with patch("task_center.load_document", side_effect=loader([EVENT, earlier], [REPORT])):
            task = task_list()["items"][0]
        self.assertEqual(task["last_run"]["id"], "e")
        self.assertEqual(task["latest_report"]["id"], "r")

    def test_combined_filter_does_not_mix_other_reports(self):
        combined = dict(REPORT, id="c", task_id="combined_pair", track="market_review")
        with patch("task_center.load_document", side_effect=loader(reports=[REPORT, combined])):
            page = report_page("combined_pair")
        self.assertEqual([r["id"] for r in page["items"]], ["c"])

    def test_invalid_and_naive_receipts_rejected(self):
        for changed in (dict(EVENT, task_id="unknown"),
                        dict(EVENT, started_at="2026-09-30T21:00:00"),
                        dict(EVENT, report_ids=[]),
                        dict(EVENT, completed_at="2026-10-01T21:00:00+13:00")):
            with self.subTest(receipt=changed), self.assertRaises(ValueError):
                validate_runs({"items": [changed]}, TASKS)

    def test_receipt_history_cannot_be_rewritten(self):
        before = {"items": [EVENT]}
        after = copy.deepcopy(before)
        after["items"][0]["status"] = "failed"
        with self.assertRaises(ValueError):
            verify_append_only(before, after, "task_runs")

    def test_api_errors_are_visible(self):
        with patch("app.task_list", side_effect=OSError("missing")):
            self.assertFalse(api.tasks()["ok"])

    def test_real_registry_and_empty_initial_receipts(self):
        root = Path(__file__).resolve().parents[1] / "data"
        tasks = json.loads((root / "tasks.json").read_text())
        runs = json.loads((root / "task_runs.json").read_text())
        validate_registry(tasks)
        validate_runs(runs, tasks)
        self.assertTrue({"apk_polish", "high_elasticity_once", "market_review", "quant_research",
                         "volume_price", "low_position", "dragon_tiger", "combined_pair",
                         "early_pair", "late_pair"}.issubset({row["id"] for row in tasks["items"]}))


if __name__ == "__main__":
    unittest.main()
