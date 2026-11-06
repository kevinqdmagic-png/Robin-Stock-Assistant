"""Unexpired research obligations derived from durable reports and receipts."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from daily_results import daily_results
from learning_loop import is_session, latest_completed_session
from task_center import context

CN = ZoneInfo("Asia/Shanghai")


def due_at(task, day):
    local_time = task.get("recovery_due_local_time")
    if not local_time:
        return datetime.combine(day, time(20, 40), CN)
    zone = ZoneInfo(task["recovery_due_timezone"])
    close = datetime.combine(day, time(15, 15), CN).astimezone(zone)
    due = datetime.combine(close.date(), time.fromisoformat(local_time), zone)
    if due < close:
        due += timedelta(days=1)
    return due.astimezone(CN)


def recovery_backlog(since="2026-11-02", offset=0, limit=50, *, documents=None, now=None):
    """Do not expire old work or treat a partial/blocked receipt as completion.

    This is a work list for the scheduled researchers, not a claim that an
    executor is running. It does not reconstruct missed intraday signals.
    """
    now = (now or datetime.now(CN)).astimezone(CN)
    start = date.fromisoformat(since)
    latest = latest_completed_session(now)
    if latest is None or start.year != 2026:
        raise ValueError("recovery_calendar_unverified")
    if offset < 0 or not 1 <= limit <= 200:
        raise ValueError("invalid_pagination")
    documents = documents or context()
    tasks, _runs, _reports = documents
    registry = {t["id"]: t for t in tasks["items"] if t.get("enabled")}
    items, pending = [], []
    day = start
    while day <= latest:
        if is_session(day) is not True:
            day += timedelta(days=1)
            continue
        rows = daily_results(day.isoformat(), documents=documents, now=now)["items"]
        for row in rows:
            task = registry.get(row["task_id"])
            if not task or row["full_research_completed"]:
                continue
            due = due_at(task, day)
            item = {**row, "due_at_cn": due.isoformat(timespec="seconds"),
                    "expires": False, "historical_signal_reconstruction_allowed": False}
            if now < due:
                pending.append(item)
            else:
                item["overdue_hours"] = round((now - due).total_seconds() / 3600, 2)
                items.append(item)
        day += timedelta(days=1)
    return {
        "ok": True, "time_cn": now.isoformat(timespec="seconds"),
        "tracking_since": since, "latest_completed_session": latest.isoformat(),
        "items": items[offset:offset + limit], "total": len(items), "offset": offset,
        "has_more": offset + limit < len(items),
        "pending_not_yet_due": pending,
        "obligations_expire_on_date_change": False,
        "automatically_executing": False,
        "completion_basis": "published_complete_report_and_valid_receipt",
    }
