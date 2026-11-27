#!/usr/bin/env python3
"""Append-only completion-contract correction for the full 2026-11-27 low study."""
from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research_backfills/linked-low-dragon-20261127-v1.json"
TARGET = ROOT / "research_backfills/linked-low-position-20261127-v2.json"
STAMP = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")

bundle = json.loads(SOURCE.read_text(encoding="utf-8"))
original = next(row for row in bundle["research"] if row["id"] == "low-position-20261127-close-v1")
report = dict(original)
report.update(
    id="low-position-20261127-close-v2",
    report_type="full_daily_research",
    recorded_at=STAMP,
    published_at=STAMP,
    title="11月27日低位启动完整研究v2｜全样本、旧30日跟踪与验收契约纠错",
    summary="沪深5219/5225；120广池、28深池、52条旧样本、5条新增；v2仅追加完整研究验收字段。",
    sources=list(original["source_urls"]),
)
receipt = {
    "id": "low-position-20261127-close-v2-scheduled-run",
    "run_id": "low-position-20261127-close-v2-scheduled",
    "task_id": "low_position",
    "date": "2026-11-27",
    "trigger": "scheduled",
    "started_at": STAMP,
    "recorded_at": STAMP,
    "completed_at": STAMP,
    "status": "completed",
    "summary": report["summary"],
    "report_ids": [report["id"]],
    "analysis_completed": True,
}
TARGET.write_text(json.dumps({"research": [report], "task_runs": [receipt]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"report_id": report["id"], "receipt_id": receipt["id"], "recorded_at": STAMP}, ensure_ascii=False))
