#!/usr/bin/env python3
"""Fail-closed, read-only audit of six A-share full research deliveries.

It does not make a new recommendation, infer trades, backfill prices, or change
immutable reports. Supplementary evidence and partial GitHub scans do not pass.
"""
import argparse
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from trading_calendar import session_state

CN = ZoneInfo("Asia/Shanghai")
REQUIRED = (
    "market_review", "volume_price", "low_position", "dragon_tiger",
    "combined_pair", "limitup_single",
)
INTEGRATED = set(REQUIRED) - {"limitup_single"}
INVALID_SCOPE = {"partial_research_universe", "dependency_audit_only"}
INVALID_STATUS = {
    "partial", "blocked", "waiting", "failed", "evidence_only",
    "missing_original_report", "completed_with_data_gaps",
}


def latest_closed_session(now):
    """Return the most recent *official-calendar-known* finished trading day."""
    local = now.astimezone(CN)
    for back in range(33):
        candidate = local.date() - timedelta(days=back)
        end = datetime.combine(candidate, time(16, 0), tzinfo=CN)
        if end > local:
            continue
        state = session_state(end)
        if state["code"] == "after_close":
            return candidate.isoformat()
        if state["code"] == "unknown":
            raise ValueError("calendar_year_unknown")
    raise ValueError("closed_session_not_found")


def full_report(report, task, day):
    """The original complete analysis, not an addendum or a partial proxy."""
    rid = str(report.get("id", "")).lower()
    if report.get("task_id") != task or report.get("date") != day:
        return False
    if any(word in rid for word in ("supplement", "partial", "snapshot", "audit-only")):
        return False
    if report.get("status") != "completed" or report.get("analysis_completed") is not True:
        return False
    if report.get("report_type") not in {"full_daily_research", "full_trading_research"}:
        return False
    if report.get("execution_scope") in INVALID_SCOPE:
        return False
    if report.get("run_status") in INVALID_STATUS:
        return False
    if task in INTEGRATED and report.get("eligible_for_integrated_research") is not True:
        return False
    if not str(report.get("body") or "").strip() or not report.get("sources"):
        return False
    return True


def audit(day, reports, runs, observed_at):
    by_id = {report.get("id"): report for report in reports.get("items", [])}
    result = {
        "date": day, "checked_at": observed_at.astimezone(CN).isoformat(timespec="seconds"),
        "required": list(REQUIRED), "complete": [], "missing": [], "rejected": {},
        "status": "missing_full_delivery",
        "meaning": "Repository evidence only; production API and deployment separately required",
    }
    for task in REQUIRED:
        matches = [run for run in runs.get("items", [])
                   if run.get("task_id") == task and run.get("date") == day]
        passed = None
        rejected = []
        for run in matches:
            if run.get("status") != "completed":
                rejected.append({"receipt": run.get("id"), "reason": "not_completed"})
                continue
            linked = [by_id.get(rid) for rid in run.get("report_ids", [])]
            qualified = [r for r in linked if r and full_report(r, task, day)]
            if qualified:
                passed = {
                    "task_id": task, "receipt_id": run.get("id"),
                    "report_ids": [r["id"] for r in qualified],
                    "trigger": run.get("trigger"),
                }
                break
            rejected.append({"receipt": run.get("id"), "reason": "supplement_or_partial_or_missing_report"})
        if passed:
            result["complete"].append(passed)
        else:
            result["missing"].append(task)
            result["rejected"][task] = rejected or [{"reason": "no_same_day_receipt"}]
    if not result["missing"]:
        result["status"] = "full_reports_in_repository_verified"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD; otherwise use latest completed China session")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=Path("full_delivery_audit.json"))
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    now = datetime.now(CN)
    try:
        day = date.fromisoformat(args.date).isoformat() if args.date else latest_closed_session(now)
        folder = args.root / "backend" / "data"
        reports = json.loads((folder / "research.json").read_text(encoding="utf-8"))
        runs = json.loads((folder / "task_runs.json").read_text(encoding="utf-8"))
        result = audit(day, reports, runs, now)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        result = {"status": "audit_error", "checked_at": now.isoformat(),
                  "error": type(exc).__name__ + ": " + str(exc)[:250],
                  "required": list(REQUIRED)}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_complete and result["status"] != "full_reports_in_repository_verified":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
