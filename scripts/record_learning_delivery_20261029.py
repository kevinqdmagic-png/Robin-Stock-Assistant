#!/usr/bin/env python3
"""Append the immutable production verification event for the T29 review."""
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "backend/data/task_runs.json"
COMMIT = "c1001494cf6d52b8233575b4a6e6196f00862447"
DEPLOYMENT = "2bc3592d-bf61-443d-8b70-e216859c7d67"
WORKFLOW = "40938495174"


def main():
    document = json.loads(PATH.read_text(encoding="utf-8"))
    event_id = "learning-review-20261029-scheduled-forward-v1-delivery-verified-c100149"
    if any(row["id"] == event_id for row in document["items"]):
        raise ValueError("delivery_receipt_already_exists")
    now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    document["items"].append({
        "id": event_id,
        "run_id": "learning-review-20261029-scheduled-forward-v1",
        "task_id": "learning_review",
        "date": "2026-10-29",
        "trigger": "scheduled",
        "started_at": now,
        "recorded_at": now,
        "completed_at": now,
        "status": "completed",
        "summary": "10月29日学习快照、盘中v2/对照原始证据、发布恢复审计、独立报告与回执已通过研究CI、Railway终态SUCCESS及公开health、learning、strategy-lab、delivery、两档live/performance、报告和回执接口读回。",
        "report_ids": ["learning-review-20261029-forward-v1"],
        "recommendation_ids": [],
        "analysis_completed": True,
        "learning_snapshot_id": "forward-learning-2026-10-29",
        "eligible_for_integrated_research": False,
        "strategy_active_rules_changed": False,
        "model_weights_updated": False,
        "delivery_status": "production_verified",
        "deployed_commit": COMMIT,
        "railway_deployment_id": DEPLOYMENT,
        "public_build_observed": COMMIT,
        "github_actions_run_id": WORKFLOW,
        "public_readback": {
            "learning_latest": "forward-learning-2026-10-29",
            "strategy_lab_snapshot_date": "2026-10-29",
            "delivery_verified": 6,
            "early_live_total": 11,
            "late_live_total": 11,
            "early_performance_total": 49,
            "late_performance_total": 48,
            "actual_trades_verified": 0,
        },
        "sources": [
            f"https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/commit/{COMMIT}",
            f"https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/actions/runs/{WORKFLOW}",
            "https://robin-stock-api-production.up.railway.app/health",
            "https://robin-stock-api-production.up.railway.app/api/learning",
            "https://robin-stock-api-production.up.railway.app/api/strategy-lab",
            "https://robin-stock-api-production.up.railway.app/api/operations/delivery",
            "https://robin-stock-api-production.up.railway.app/api/intraday-live?slot=early_pair",
            "https://robin-stock-api-production.up.railway.app/api/intraday-live?slot=late_pair",
            "https://robin-stock-api-production.up.railway.app/api/intraday-performance?slot=early_pair",
            "https://robin-stock-api-production.up.railway.app/api/intraday-performance?slot=late_pair",
            "https://robin-stock-api-production.up.railway.app/api/research?task=learning_review",
            "https://robin-stock-api-production.up.railway.app/api/task-runs?task=learning_review",
        ],
    })
    PATH.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"event_id": event_id, "recorded_at": now}, ensure_ascii=False))


if __name__ == "__main__":
    main()
