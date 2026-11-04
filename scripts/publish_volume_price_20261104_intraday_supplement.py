#!/usr/bin/env python3
"""Append the 2026-11-04 production intraday evidence supplement once."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "volume-price-20261104-intraday-supplement-v1"
RECEIPT_ID = "volume-price-20261104-scheduled-intraday-supplement-v1-blocked"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, document):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main():
    research_path = ROOT / "backend/data/research.json"
    runs_path = ROOT / "backend/data/task_runs.json"
    report_body = (ROOT / "docs/research/volume-price-20261104-intraday-supplement-v1.md").read_text(encoding="utf-8")

    research = load(research_path)
    if not any(item.get("id") == REPORT_ID for item in research["items"]):
        research["items"].append({
            "id": REPORT_ID,
            "date": "2026-11-04",
            "task_id": "volume_price",
            "track": "volume_price",
            "title": "量价研究补证｜11月4日9:50与14:40生产冻结时间窗复核",
            "summary": "复核Railway持久台账：9:50和14:40各扫描63只、均无低追涨候选；补入4只控制组的时点量比/换手。范围仍为部分观察池，不能替代28只深筛分钟顺序或全A换手。",
            "body": report_body,
            "sources": [
                "docs/research/volume-price-20261104-intraday-supplement-evidence.json",
                "https://robin-stock-api-production.up.railway.app/api/intraday-live?slot=early_pair&limit=3",
                "https://robin-stock-api-production.up.railway.app/api/intraday-live?slot=late_pair&limit=20",
                "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/25"
            ],
            "report_type": "evidence_supplement",
            "primary_report_id": "volume-price-20261104-partial-v1",
            "eligible_for_integrated_research": False,
            "analysis_completed": False,
            "status": "blocked",
            "published_at": "2026-11-04T18:56:34+08:00",
            "recorded_at": "2026-11-04T18:56:34+08:00",
            "market_data_cutoff_at": "2026-11-04T14:40:21+08:00",
            "data_cutoff_at": "2026-11-04T18:56:34+08:00",
            "research_rule_version": "volume_price_close_v5_partial_source_bounded",
            "candidate_count": 0,
            "recommendation_ids": [],
            "evidence_file": "docs/research/volume-price-20261104-intraday-supplement-evidence.json",
            "window_scan_count": {"early_pair": 63, "late_pair": 63},
            "verified_fill_count": 0,
            "blocked_modules": ["full_market_turnover", "sector_sync", "deep_pool_intraday_sequence", "beijing_coverage"]
        })
        save(research_path, research)

    runs = load(runs_path)
    if not any(item.get("id") == RECEIPT_ID for item in runs["items"]):
        runs["items"].append({
            "id": RECEIPT_ID,
            "run_id": "volume-price-20261104-scheduled-intraday-supplement-v1",
            "task_id": "volume_price",
            "date": "2026-11-04",
            "trigger": "scheduled",
            "started_at": "2026-11-04T18:53:47+08:00",
            "recorded_at": "2026-11-04T18:56:34+08:00",
            "completed_at": "2026-11-04T18:56:34+08:00",
            "status": "blocked",
            "summary": "复核同T主报告并补证生产9:50/14:40冻结时间窗：各扫描63只且均无候选；部分时点报价不能补齐全A换手、板块同步及28只深池分钟顺序，故维持blocked。",
            "report_ids": ["volume-price-20261104-partial-v1", REPORT_ID],
            "recommendation_ids": [],
            "analysis_completed": False,
            "eligible_for_integrated_research": False,
            "sources": [
                "docs/research/volume-price-20261104-intraday-supplement-evidence.json",
                "https://robin-stock-api-production.up.railway.app/api/intraday-live?slot=early_pair&limit=3",
                "https://robin-stock-api-production.up.railway.app/api/intraday-live?slot=late_pair&limit=20",
                "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/25"
            ],
            "blocked_modules": ["full_market_turnover", "sector_sync", "deep_pool_intraday_sequence", "beijing_coverage"],
            "verified_fill_count": 0
        })
        save(runs_path, runs)


if __name__ == "__main__":
    main()
