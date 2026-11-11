"""Small daily report index; publication and full-research completion stay distinct."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from delivery_health import _published_complete, DELIVERY_TASKS
from learning_loop import latest_completed_session
from task_center import context, checked_receipt

CN = ZoneInfo("Asia/Shanghai")
TASKS = (*DELIVERY_TASKS, "learning_review")
AUTOMATED_SCOPES = {"partial_research_universe", "dependency_audit_only", "retrospective_partial_evidence"}


def _beijing_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(CN).isoformat(timespec="minutes")
    except (TypeError, ValueError):
        return None


def _candidate_qualification(task_id, candidate, full):
    """Keep observation labels conservative unless the archived evidence is final."""
    if candidate.get("formal_buy_signal") is True:
        return "正式条件候选"
    if task_id == "limitup_single":
        return "打板观察"
    if (task_id == "combined_pair" and full
            and candidate.get("candidate_status") == "final_integrated_pair"):
        return "最终研究双标"
    if task_id == "combined_pair":
        return "待综合观察"
    return "研究观察"


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
        # Keep the latest attempt visible separately. A retry's abbreviated
        # evidence must not replace a substantive study or erase its candidates.
        latest = checked_receipt(receipts[0], reports) if receipts else None
        linked = [report_index[rid] for rid in (latest or {}).get("report_ids", [])
                  if rid in report_index and report_index[rid].get("task_id") == task_id
                  and report_index[rid].get("date") == day]
        complete = next((r for r in receipts if (
            _published_complete(task_id, r, reports) if task_id in DELIVERY_TASKS else
            checked_receipt(r, reports)["status"] == "completed")), None)
        full = complete is not None
        substantive = [r for r in versions if r.get("execution_scope") not in AUTOMATED_SCOPES
                       and r.get("report_type") in {"manual_recovery_research", "full_daily_research",
                                                    "full_trading_research", "daily_research"}]
        if complete:
            report = next((report_index[rid] for rid in complete.get("report_ids", [])
                           if rid in report_index), None)
        else:
            report = substantive[0] if substantive else (linked[0] if linked else (versions[0] if versions else None))
        report_receipt = next((r for r in receipts if report and report["id"] in r.get("report_ids", [])), None)
        state = "completed" if full else (latest or report or {}).get("status", "missing")
        if state == "completed" and not full:
            state = "unverified"
        candidates = []
        for candidate in (report or {}).get("research_shadow_candidates", []):
            if candidate.get("task_id") != task_id:
                continue
            item = {key: candidate.get(key) for key in (
                "code", "name", "reference_price", "reference_as_of", "actual_frozen_at",
                "reviewed_at", "planned_observation_date", "hypothesis", "risk",
                "trigger_condition", "abandon_condition", "candidate_status",
                "formal_buy_signal", "buy_order_allowed", "earliest_legal_exit_if_entered",
            )}
            item["display_qualification"] = _candidate_qualification(task_id, candidate, full)
            item["reference_as_of_cn"] = _beijing_time(candidate.get("reference_as_of"))
            candidates.append(item)
        rows.append({
            "task_id": task_id, "title": registry[task_id]["title"], "date": day,
            "status": state, "full_research_completed": full,
            "published": report is not None, "report_count": len(versions),
            "report_id": report["id"] if report else None,
            "report_title": report.get("title") if report else None,
            "report_status": (report or {}).get("status"),
            "summary": (report or latest or {}).get("summary", "本交易日暂无已发布报告，等待补做。"),
            "published_at": report.get("published_at") if report else None,
            "published_at_cn": _beijing_time(report.get("published_at")) if report else None,
            "detail_path": "/api/research/" + report["id"] if report else None,
            "receipt_id": (report_receipt or {}).get("id"),
            "latest_attempt_receipt_id": (latest or {}).get("id"),
            "latest_attempt_status": (latest or {}).get("status"),
            "latest_attempt_report_ids": (latest or {}).get("report_ids", []),
            "report_selection": "verified_complete" if full else
                ("substantive_research" if substantive else "latest_attempt"),
            "recovery_required": not full,
            "research_shadow_candidates": candidates,
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
