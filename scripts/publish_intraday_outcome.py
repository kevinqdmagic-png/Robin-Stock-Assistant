#!/usr/bin/env python3
"""Publish an honest scheduled intraday execution receipt, never a made-up pick.

A GitHub Actions success from the evidence gate is not proof of a completed
selection. The outcome is appended to the immutable execution-receipt ledger.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from task_center import validate_runs
from research_archive import load_document, verify_append_only

CN = ZoneInfo("Asia/Shanghai")


def record_outcome(ledger, outcome, run_id, recorded_at=None):
    now = (recorded_at or datetime.now(CN)).astimezone(CN)
    slot = outcome.get("task_id")
    if slot not in ("early_pair", "late_pair"):
        raise ValueError("unsupported_intraday_task")
    day = outcome.get("market_date")
    datetime.strptime(day, "%Y-%m-%d")
    if not str(run_id).isdigit():
        raise ValueError("invalid_github_run_id")
    result = outcome.get("status")
    # No unsupported publication of "completed", even if a caller supplies it.
    if result not in ("insufficient_evidence", "skipped"):
        raise ValueError("unpublished_or_unverified_outcome")
    event_status = ("blocked" if result == "insufficient_evidence" else
                    "failed" if outcome.get("reason") == "outside_intraday_execution_window" else "waiting")
    started_at = datetime.fromisoformat(outcome["checked_at"])
    if started_at.tzinfo is None or started_at.astimezone(CN) > now:
        raise ValueError("invalid_execution_time")
    source = "https://github.com/" + "kevinqdmagic-png/Robin-Stock-Assistant/actions/runs/" + str(run_id)
    reason = outcome.get("reason") or "unknown"
    if outcome.get("recommendations") or outcome.get("market_data_verified"):
        raise ValueError("unverified_selection_not_publishable")
    explanations = {
        "no_live_feed_supplied": "未接入合规且经核验的当时行情，不能产生真实荐股",
        "snapshot_only_no_verified_selection_model": "行情快照存在但缺乏经验证的选股模型，不能冒充荐股完成",
        "outside_intraday_execution_window": "GitHub定时调度延迟，已错过有效选股窗口",
        "not_a_verified_trading_session": "非已核验的交易时段，未运行选股",
    }
    summary = "GitHub调度检查：" + explanations.get(reason, "证据不足：" + reason) + "；实际检查北京时间 " + started_at.astimezone(CN).strftime("%H:%M:%S") + "。"
    receipt_id = slot + "-" + day.replace("-", "") + "-gh-" + str(run_id)
    new = dict(ledger)
    original = ledger.get("items", [])
    existing = next((row for row in original if row.get("id") == receipt_id), None)
    if existing is not None:
        return ledger, False
    receipt = {
        "id": receipt_id, "run_id": "github-actions-" + str(run_id),
        "task_id": slot, "date": day, "trigger": "scheduled",
        "started_at": started_at.isoformat(), "recorded_at": now.isoformat(),
        "status": event_status, "summary": summary,
        "report_ids": [], "recommendation_ids": [],
        "sources": [source], "analysis_completed": False,
        "eligible_for_integrated_research": False,
        "reason_code": reason,
    }
    if event_status in ("blocked", "failed"):
        receipt["completed_at"] = now.isoformat()
    new["items"] = original + [receipt]
    validate_runs(new, load_document("tasks.json", "ROBIN_TASKS_FILE"))
    verify_append_only(ledger, new, "task_runs")
    return new, True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--ledger", default=str(ROOT / "backend/data/task_runs.json"))
    parser.add_argument("--summary-output", default="intraday_publish_status.json")
    args = parser.parse_args()
    outcome = json.loads(Path(args.outcome).read_text(encoding="utf-8"))
    path = Path(args.ledger)
    original = json.loads(path.read_text(encoding="utf-8"))
    updated, changed = record_outcome(original, outcome, args.run_id)
    if changed:
        path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status = {"changed": changed, "status": outcome["status"], "reason": outcome.get("reason"),
              "run_id": args.run_id, "task_id": outcome["task_id"]}
    Path(args.summary_output).write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
