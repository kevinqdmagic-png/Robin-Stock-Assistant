#!/usr/bin/env python3
"""Append the immutable production verification event for the T30 review."""
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "backend/data/task_runs.json"
COMMIT = "88e04c86c16f1e40bd8aa6ab8026aece91d0de73"
DEPLOYMENT = "4788654d-4f51-4abe-9a96-1d59f5bf7505"
WORKFLOW = "41117504021"
SMOKE_WORKFLOW = "41117504537"


def main():
    document = json.loads(PATH.read_text(encoding="utf-8"))
    event_id = "learning-review-20261030-scheduled-forward-v1-delivery-verified-88e04c8"
    if any(row["id"] == event_id for row in document["items"]):
        raise ValueError("delivery_receipt_already_exists")
    now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    document["items"].append({
        "id": event_id,
        "run_id": "learning-review-20261030-scheduled-forward-v1",
        "task_id": "learning_review",
        "date": "2026-10-30",
        "trigger": "scheduled",
        "started_at": now,
        "recorded_at": now,
        "completed_at": now,
        "status": "completed",
        "summary": "10月30日学习快照、v2首个T+1/对照原始证据、发布恢复持续审计、独立报告与回执已通过218项本地测试、GitHub Research correctness、Railway终态SUCCESS及公开接口读回。",
        "report_ids": ["learning-review-20261030-forward-v1"],
        "recommendation_ids": [],
        "analysis_completed": True,
        "learning_snapshot_id": "forward-learning-2026-10-30",
        "eligible_for_integrated_research": False,
        "strategy_active_rules_changed": False,
        "model_weights_updated": False,
        "delivery_status": "production_verified",
        "deployed_commit": COMMIT,
        "railway_deployment_id": DEPLOYMENT,
        "public_build_observed": COMMIT,
        "github_actions_run_id": WORKFLOW,
        "production_smoke_run_id": SMOKE_WORKFLOW,
        "public_readback": {
            "learning_latest": "forward-learning-2026-10-30",
            "strategy_lab_snapshot_date": "2026-10-30",
            "strategy_lab_distinct_stock_dates": 16,
            "delivery_verified": 6,
            "early_live_total": 12,
            "late_live_total": 12,
            "early_performance_total": 59,
            "late_performance_total": 58,
            "report_id": "learning-review-20261030-forward-v1",
            "repository_receipt_id": "learning-review-20261030-scheduled-forward-v1-completed",
            "actual_trades_verified": 0,
            "app_auto_trading_enabled": False,
            "automatic_weight_updates": False,
            "issue_23_state": "closed",
        },
        "sources": [
            f"https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/commit/{COMMIT}",
            f"https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/actions/runs/{WORKFLOW}",
            f"https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/actions/runs/{SMOKE_WORKFLOW}",
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
            "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/23",
        ],
    })
    PATH.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"event_id": event_id, "recorded_at": now}, ensure_ascii=False))


if __name__ == "__main__":
    main()
