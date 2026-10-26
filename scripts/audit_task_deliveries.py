#!/usr/bin/env python3
"""Record undelivered scheduled research without pretending it ran.

The 20:40 Beijing audit is an independent inspection of immutable task receipts.
It never generates research, recommendations, market observations or trade claims.
Resident 09:50/14:40 Railway records are checked by the operations endpoint,
not by this GitHub full-report audit.
"""
import argparse
from datetime import datetime, time
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from research_archive import load_document, verify_append_only
from task_center import validate_runs
from trading_calendar import session_state

CN_TZ = ZoneInfo("Asia/Shanghai")
AUDIT_TASKS = ("limitup_single", "market_review", "volume_price",
               "combined_pair", "low_position", "dragon_tiger")


def audit_day(ledger, tasks, reports, now=None, day=None, audit_id=None):
    now = (now or datetime.now(CN_TZ)).astimezone(CN_TZ)
    day = day or now.date().isoformat()
    try:
        date = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("invalid_audit_date")
    if date > now.date() or (date == now.date() and now.time() < time(20, 40)):
        raise ValueError("audit_before_research_deadline")
    observation = datetime.combine(date, time(14, 0), CN_TZ)
    if session_state(observation)["code"] != "trading":
        return ledger, {"date": day, "status": "market_closed", "created": [], "unfulfilled": []}
    index = {r["id"]: r for r in reports.get("items", []) if r.get("id")}
    registry = {t["id"]: t for t in tasks["items"]}
    published = {r["id"] for r in ledger["items"]}
    updated = dict(ledger)
    updated["items"] = list(ledger["items"])
    created, unfulfilled = [], []
    for task_id in AUDIT_TASKS:
        task = registry.get(task_id)
        if task is None or not task.get("enabled"):
            continue
        history = [r for r in updated["items"] if r["task_id"] == task_id and r["date"] == day]
        completed = any(r["status"] == "completed" and r.get("report_ids") and
                        all(key in index and index[key].get("task_id") == task_id and index[key].get("date") == day
                            for key in r["report_ids"]) for r in history)
        if completed:
            continue
        unfulfilled.append(task_id)
        # If a scheduled receipt already documents an execution failure, do not
        # duplicate it. Create a missing-delivery receipt only if none was recorded.
        if history:
            continue
        id = "deadline-audit-" + day.replace("-", "") + "-" + task_id
        if id in published:
            continue
        stamp = now.isoformat(timespec="seconds")
        receipt = {
            "id": id, "run_id": str(audit_id or ("deadline-audit-" + day)),
            "task_id": task_id, "date": day, "trigger": "scheduled",
            "started_at": stamp, "completed_at": stamp, "recorded_at": stamp,
            "status": "blocked",
            "summary": "北京时间20:40交付审计：未找到当日可核验的完整任务回执/关联研究报告。此回执仅证明未交付，不代表曾经执行研究；检查定时器、数据源和发布流程。",
            "report_ids": [], "recommendation_ids": [],
            "analysis_completed": False, "eligible_for_integrated_research": False,
            "reason_code": "missing_delivery_evidence",
        }
        updated["items"].append(receipt)
        created.append(id)
    if created:
        validate_runs(updated, tasks)
        verify_append_only(ledger, updated, "task_runs")
    return updated, {"date": day, "status": "unfulfilled" if unfulfilled else "complete",
                     "created": created, "unfulfilled": unfulfilled}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day")
    parser.add_argument("--ledger", default=str(ROOT / "backend/data/task_runs.json"))
    parser.add_argument("--output", default="deadline_audit_status.json")
    args = parser.parse_args()
    now = datetime.now(CN_TZ)
    path = Path(args.ledger)
    before = json.loads(path.read_text(encoding="utf-8"))
    tasks = load_document("tasks.json", "ROBIN_TASKS_FILE")
    reports = load_document("research.json", "ROBIN_RESEARCH_FILE")
    after, status = audit_day(before, tasks, reports, now, args.day,
                              "github-actions-deadline-audit")
    if status["created"]:
        path.write_text(json.dumps(after, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status["changed"] = bool(status["created"])
    Path(args.output).write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
