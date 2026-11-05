"""Small daily report index; publication and full-research completion stay distinct."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from delivery_health import _published_complete, DELIVERY_TASKS
from learning_loop import latest_completed_session
from task_center import context, checked_receipt

CN = ZoneInfo("Asia/Shanghai")
TASKS = (*DELIVERY_TASKS, "learning_review")


def daily_results(day=None, offset=0, limit=7, *, documents=None, now=None):
    now = (now or datetime.now(CN)).astimezone(CN)
    selected = date.fromisoformat(day) if day else latest_completed_session(now)
    if selected is None or selected > now.date():
        raise ValueError("invalid_or_unknown_report_date")
    if not 0 <= offset or not 1 <= limit <= 20:
        raise ValueError("invalid_pagination")
    day = selected.isoformat()
    tasks, runs, reports = documents or context()
    registry = {t["id"]: t for t in tasks["items"]}
    report_index = {r["id"]: r for r in reports["items"] if r.get("id")}
    rows = []
    for task_id in TASKS:
        if task_id not in registry:
            continue
        versions = sorted((r for r in reports["items"] if r.get("task_id") == task_id
                           and r.get("date") == day),
                          key=lambda r: (r.get("published_at", ""), r["id"]), reverse=True)
        receipts = sorted((r for r in runs["items"] if r.get("task_id") == task_id
                           and r.get("date") == day), key=lambda r: r.get("recorded_at", ""), reverse=True)
        # Show the latest receipt's linked report when present, without combining
        # a new failure receipt with an unrelated old completed report.
        latest = checked_receipt(receipts[0], reports) if receipts else None
        linked = [report_index[rid] for rid in (latest or {}).get("report_ids", [])
                  if rid in report_index and report_index[rid].get("task_id") == task_id
                  and report_index[rid].get("date") == day]
        report = linked[0] if linked else (versions[0] if versions else None)
        full = any(_published_complete(task_id, r, reports) for r in receipts) if task_id in DELIVERY_TASKS else any(
            checked_receipt(r, reports)["status"] == "completed" for r in receipts)
        state = "completed" if full else (latest or report or {}).get("status", "missing")
        if state == "completed" and not full:
            state = "unverified"
        rows.append({
            "task_id": task_id, "title": registry[task_id]["title"], "date": day,
            "status": state, "full_research_completed": full,
            "published": report is not None, "report_count": len(versions),
            "report_id": report["id"] if report else None,
            "report_title": report.get("title") if report else None,
            "summary": (report or latest or {}).get("summary", "本交易日暂无已发布报告，等待补做。"),
            "published_at": report.get("published_at") if report else None,
            "detail_path": "/api/research/" + report["id"] if report else None,
            "receipt_id": (latest or {}).get("id"),
            "recovery_required": not full,
            "research_shadow_candidates": [
                {key: candidate.get(key) for key in ("code", "name", "reference_price", "reference_as_of",
                    "actual_frozen_at", "planned_observation_date", "hypothesis", "risk")}
                for candidate in (report or {}).get("research_shadow_candidates", [])
                if candidate.get("task_id") == task_id
            ],
        })
    return {
        "ok": True, "date_cn": day, "time_cn": now.isoformat(timespec="seconds"),
        "market_scope": "Shanghai+Shenzhen; Beijing excluded",
        "items": rows[offset:offset + limit], "total": len(rows), "offset": offset,
        "has_more": offset + limit < len(rows),
        "published_count": sum(r["published"] for r in rows),
        "completed_count": sum(r["full_research_completed"] for r in rows),
        "recovery_task_ids": [r["task_id"] for r in rows if r["recovery_required"]],
        "publication_is_full_completion": False,
    }


def report_detail(report_id, *, reports=None):
    if reports is None:
        from research_archive import load_document
        reports = load_document("research.json", "ROBIN_RESEARCH_FILE")
    report = next((r for r in reports["items"] if r.get("id") == report_id), None)
    if report is None:
        return None
    return {"ok": True, "report": {**report, "body": report.get("body") or report.get("summary", "")}}
