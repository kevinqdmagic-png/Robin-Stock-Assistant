"""Task configuration snapshots and evidence-backed execution receipts."""
import hashlib
import json
import re
from datetime import datetime
from research_archive import load_document

STATUSES = {"running", "waiting", "completed", "blocked", "failed"}
TERMINAL = {"completed", "blocked", "failed"}
ID = re.compile(r"[a-z][a-z0-9_]*")


def instant(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp_requires_timezone")
    return parsed


def validate_registry(document):
    ids = set()
    instant(document["updated_at"])
    for row in document["items"]:
        if not ID.fullmatch(row.get("id", "")) or row["id"] in ids:
            raise ValueError("invalid_task_id")
        ids.add(row["id"])
        if not row.get("title") or not row.get("schedule") or not row.get("timezone"):
            raise ValueError("incomplete_task_configuration")
    for row in document["items"]:
        if any(dep not in ids for dep in row.get("dependencies", [])):
            raise ValueError("unknown_dependency")


def validate_runs(document, tasks):
    ids = set()
    task_ids = {row["id"] for row in tasks["items"]}
    for row in document["items"]:
        if not row.get("id") or row["id"] in ids or row.get("task_id") not in task_ids:
            raise ValueError("invalid_receipt_id")
        ids.add(row["id"])
        if not row.get("run_id") or row.get("status") not in STATUSES:
            raise ValueError("invalid_receipt_status")
        started = instant(row["started_at"])
        recorded = instant(row["recorded_at"])
        if recorded < started or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row.get("date", "")):
            raise ValueError("invalid_receipt_time")
        if row.get("trigger") not in {"scheduled", "manual"}:
            raise ValueError("invalid_receipt_trigger")
        if row["status"] in TERMINAL and instant(row["completed_at"]) < started:
            raise ValueError("invalid_completion_time")
        if row["status"] == "completed" and not row.get("report_ids"):
            raise ValueError("completed_receipt_requires_report")
        if not isinstance(row.get("report_ids", []), list):
            raise ValueError("invalid_report_links")


def belongs(report, task):
    if report.get("task_id"):
        return report["task_id"] == task["id"]
    # Legacy report links are historical material, not proof that a current run completed.
    slug = task["id"]
    if slug in {"early_pair", "late_pair", "apk_polish"}:
        return False
    if slug == "combined_pair":
        return report.get("strategy") == "combined_limitup_watch" or "综合双标" in report.get("title", "")
    if slug == "market_review":
        return (report.get("track") == "market_review" and
                report.get("strategy") != "combined_limitup_watch" and "综合双标" not in report.get("title", "") and
                report.get("group") not in {"0950", "1440"})
    return report.get("track") == task.get("track")


def paginate(rows, offset=0, limit=20):
    offset = max(0, int(offset))
    limit = max(1, min(100, int(limit)))
    rows = sorted(rows, key=lambda r: (r.get("date", ""), r.get("recorded_at", r.get("published_at", ""))), reverse=True)
    return {"items": rows[offset:offset + limit], "total": len(rows),
            "offset": offset, "has_more": offset + limit < len(rows)}


def context():
    tasks = load_document("tasks.json", "ROBIN_TASKS_FILE")
    runs = load_document("task_runs.json", "ROBIN_TASK_RUNS_FILE")
    validate_registry(tasks)
    validate_runs(runs, tasks)
    reports = load_document("research.json", "ROBIN_RESEARCH_FILE")
    return tasks, runs, reports


def checked_receipt(receipt, reports):
    row = dict(receipt)
    index = {r["id"]: r for r in reports["items"] if r.get("id")}
    linked = [index.get(key) for key in row.get("report_ids", [])]
    if row["status"] == "completed" and (not linked or any(r is None or r.get("task_id") != row["task_id"] for r in linked)):
        row["status"] = "report_missing"
        row["summary"] = "执行回执已有，关联报告尚未完整发布。"
    return row


def task_list():
    tasks, runs, reports = context()
    items = []
    for task in tasks["items"]:
        row = dict(task)
        receipts = sorted([r for r in runs["items"] if r["task_id"] == row["id"]],
                          key=lambda r: instant(r["recorded_at"]), reverse=True)
        history = paginate([r for r in reports["items"] if belongs(r, task)])
        row["last_run"] = checked_receipt(receipts[0], reports) if receipts else None
        row["report_count"] = history["total"]
        row["latest_report"] = history["items"][0] if history["items"] else None
        items.append(row)
    return {"items": items, "total": len(items), "configuration_updated_at": tasks["updated_at"],
            "status_source": "published_execution_receipts"}


def run_page(task=None, offset=0, limit=20):
    tasks, runs, reports = context()
    if task and task not in {r["id"] for r in tasks["items"]}:
        raise ValueError("unknown_task")
    return paginate([checked_receipt(r, reports) for r in runs["items"] if not task or r["task_id"] == task], offset, limit)


def report_page(task_id, track=None, day=None, offset=0, limit=20):
    tasks = load_document("tasks.json", "ROBIN_TASKS_FILE")
    task = next((r for r in tasks["items"] if r["id"] == task_id), None)
    if task is None:
        raise ValueError("unknown_task")
    rows = load_document("research.json", "ROBIN_RESEARCH_FILE")["items"]
    rows = [dict(r, body=r.get("body") or r.get("summary", "")) for r in rows
            if belongs(r, task) and (not track or r.get("track") == track) and (not day or r.get("date") == day)]
    return paginate(rows, offset, limit)


def data_revision():
    envs = {"research.json": "ROBIN_RESEARCH_FILE", "recommendations.json": "ROBIN_RECOMMENDATIONS_FILE",
            "tasks.json": "ROBIN_TASKS_FILE", "task_runs.json": "ROBIN_TASK_RUNS_FILE"}
    payload = {name: load_document(name, env) for name, env in envs.items()}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
