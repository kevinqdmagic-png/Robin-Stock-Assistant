"""Evidence-based, read-only daily delivery status for the latest A-share session.

This reports whether complete research was published. It never infers execution
from a scheduler firing, a partial observation, or an HTTP 200 response.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from learning_loop import latest_completed_session
from task_center import checked_receipt, context, instant

CN = ZoneInfo("Asia/Shanghai")
# These are independent *delivery* checks. The combined orchestrator may
# execute multiple tracks, but one receipt cannot satisfy another track.
DELIVERY_TASKS = (
    "market_review", "volume_price", "low_position", "dragon_tiger",
    "combined_pair", "limitup_single", "early_pair", "late_pair",
)
FULL_RESEARCH_TASKS = set(DELIVERY_TASKS[:6])
AUDIT_DEADLINE = time(20, 40)


def _published_complete(task_id, row, reports):
    """Only real completed receipts with valid linked same-day reports count."""
    checked = checked_receipt(row, reports)
    if checked["status"] != "completed" or not row.get("report_ids"):
        return False
    if task_id in FULL_RESEARCH_TASKS and row.get("analysis_completed") is not True:
        return False
    linked = {r.get("id"): r for r in reports["items"] if r.get("id")}
    return all(
        linked.get(report_id, {}).get("task_id") == task_id
        and linked[report_id].get("date") == row["date"]
        and linked[report_id].get("status") not in ("evidence_only", "missing_original_report")
        for report_id in row["report_ids"]
    )


def build_delivery_health(tasks, runs, reports, *, now=None, session_day=None):
    """A complete/blocked/missing matrix; does not trigger any jobs or trades."""
    now = (now or datetime.now(CN)).astimezone(CN)
    day = session_day or latest_completed_session(now)
    if day is None:
        return {"ok": False, "status": "calendar_unverified",
                "time_cn": now.isoformat(timespec="seconds"), "items": []}
    if isinstance(day, str):
        from datetime import date
        day = date.fromisoformat(day)
    day_text = day.isoformat()
    after_deadline = day < now.date() or (day == now.date() and now.time() >= AUDIT_DEADLINE)
    registry = {task["id"]: task for task in tasks["items"]}
    items = []
    for task_id in DELIVERY_TASKS:
        task = registry.get(task_id)
        if task is None or not task.get("enabled", False):
            continue
        history = sorted(
            (row for row in runs["items"]
             if row.get("task_id") == task_id and row.get("date") == day_text),
            key=lambda row: instant(row["recorded_at"]), reverse=True,
        )
        complete = next((row for row in history if _published_complete(task_id, row, reports)), None)
        latest = history[0] if history else None
        if complete:
            state = "completed"
        elif not after_deadline:
            state = "pending"
        elif latest and latest.get("status") in {"failed", "blocked", "partial", "waiting", "running"}:
            state = latest["status"]
        elif latest:
            state = "unverified"
        else:
            state = "missing"
        items.append({
            "task_id": task_id, "title": task.get("title", task_id),
            "status": state, "receipt_count": len(history),
            "verified_receipt_id": complete["id"] if complete else None,
            "latest_receipt_id": latest["id"] if latest else None,
            "latest_recorded_at": latest.get("recorded_at") if latest else None,
        })
    gaps = [row["task_id"] for row in items if row["status"] != "completed"]
    return {
        "ok": True, "date_cn": day_text, "time_cn": now.isoformat(timespec="seconds"),
        "status": "complete" if not gaps else ("incomplete" if after_deadline else "pending"),
        "audit_deadline_cn": day_text + "T20:40:00+08:00",
        "checked_task_count": len(items),
        "verified_count": len(items) - len(gaps),
        "unverified_task_ids": gaps, "items": items,
        "execution_claim": "published_complete_receipts_only",
        "trading_strategy_validated": False,
    }


def delivery_health(*, now=None):
    tasks, runs, reports = context()
    return build_delivery_health(tasks, runs, reports, now=now)
