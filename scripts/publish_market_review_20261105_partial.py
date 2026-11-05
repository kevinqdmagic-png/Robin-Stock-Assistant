#!/usr/bin/env python3
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "market-review-20261105-source-bounded-v1"
RUN_ID = "market-review-20261105-scheduled-close-source-bounded-v1"
MD = ROOT / "docs/research/market-review-20261105-source-bounded-v1.md"
EVIDENCE = ROOT / "docs/research/market-review-20261105-evidence.json"

def append_unique(path, item):
    data = json.loads(path.read_text(encoding="utf-8"))
    if any(x.get("id") == item["id"] for x in data["items"]):
        raise SystemExit(f"duplicate id: {item['id']}")
    data["items"].append(item)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def main():
    now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    body = MD.read_text(encoding="utf-8")
    sources = [
        "docs/research/market-review-20261105-source-bounded-v1.md",
        "docs/research/market-review-20261105-evidence.json",
        "https://news.10jqka.com.cn/20261105/c681500940.shtml",
        "https://fund.eastmoney.com/a/202611053923465485.html",
        "https://finance.eastmoney.com/a/202611053923486289.html",
        "https://www.toupage.com/stocks/limit-up",
        "https://www.kanpanba.com/limit/2026-11-05",
    ]
    codes = ["002578","603381","301697","002529","002309","603212","002506","002487","002081","600641","600206","002409","002156","603657","003033","603955","000700","300709","000017","605339","000995","605188","002329","000603","600988","000426","002192","002240"]
    report = {
        "id": REPORT_ID, "date": "2026-11-05", "market_date": "2026-11-05",
        "task_id": "market_review", "track": "market_review", "run_id": RUN_ID,
        "title": "每日复盘｜11月5日普涨放量修复与高位分歧（来源受限版）",
        "summary": "T=11/05指数普涨、沪深京成交21353亿元；事件广池130只、深池28只。BaoStock 8分片均登录失败，逐股OHLCV与上一池T+1验证受阻，正式0。",
        "body": body, "sources": sources, "report_type": "source_bounded_partial_daily_research",
        "eligible_for_integrated_research": False, "analysis_completed": False, "status": "partial",
        "published_at": now, "recorded_at": now, "data_cutoff_at": now,
        "market_data_cutoff_at": "2026-11-05T15:00:00+08:00",
        "provenance": "same_day_after_close_public_cross_source_partial",
        "research_rule_version": "market_review_close_v6_source_bounded",
        "candidate_count": 0, "recommendation_ids": [], "codes": codes,
        "full_scan_count": 0, "event_broad_pool_count": 130, "deep_pool_count": 28,
        "previous_pool_verified_count": 0, "planned_entry_date": "2026-11-06",
        "earliest_legal_exit_date_if_bought": "2026-11-09",
        "evidence_file": "docs/research/market-review-20261105-evidence.json"
    }
    receipt = {
        "id": RUN_ID + "-partial", "run_id": RUN_ID, "task_id": "market_review",
        "date": "2026-11-05", "trigger": "scheduled",
        "started_at": "2026-11-05T16:41:12+08:00", "completed_at": now,
        "recorded_at": now, "status": "partial",
        "summary": report["summary"] + " 未满足完整研究门槛，不得转completed。",
        "report_ids": [REPORT_ID], "recommendation_ids": [],
        "analysis_completed": False, "eligible_for_integrated_research": False,
        "trade_executed": False, "delivery_status": "repository_prepared_not_yet_verified",
        "sources": sources[:2]
    }
    append_unique(ROOT / "backend/data/research.json", report)
    append_unique(ROOT / "backend/data/task_runs.json", receipt)
    print(json.dumps({"report_id": REPORT_ID, "receipt_id": receipt["id"], "completed_at": now}, ensure_ascii=False))

if __name__ == "__main__":
    main()
