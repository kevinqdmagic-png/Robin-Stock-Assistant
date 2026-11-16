#!/usr/bin/env python3
"""Compact public prose and build the immutable linked archive bundle."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "volume-price-20261116-close-v1"
HISTORY_ID = "volume-price-20261113-t1-supplement-20261116-v1"
RUN_IDS = {
    "volume-price-20261116-scheduled-close-v1-completed",
    "volume-price-20261113-t1-supplement-20261116-v1-manual-completed",
}
PREFIX = "- 东方财富免费收盘元数据："
COMPACT = (
    "- 东方财富免费收盘元数据：56页中仅2页成功，200/5564只；其余54页均为"
    "HTTP 502对应的`curl_exit_22`。完整逐页错误保留在证据JSON。该源失败后，"
    "腾讯免费收盘报价仍独立交叉深池28/28并补换手，未用局部榜单冒充全市场。"
)


def compact_body(body: str) -> str:
    lines = body.splitlines()
    return "\n".join(COMPACT if line.startswith(PREFIX) else line for line in lines) + "\n"


research_path = ROOT / "backend/data/research.json"
runs_path = ROOT / "backend/data/task_runs.json"
research_doc = json.loads(research_path.read_text(encoding="utf-8"))
runs_doc = json.loads(runs_path.read_text(encoding="utf-8"))

reports = []
for row in research_doc["items"]:
    if row.get("id") in {REPORT_ID, HISTORY_ID}:
        if row.get("id") == REPORT_ID:
            row["body"] = compact_body(row["body"])
        reports.append(row)

runs = [row for row in runs_doc["items"] if row.get("id") in RUN_IDS]
for row in reports + runs:
    if isinstance(row.get("sources"), list):
        row["sources"] = [
            source.replace(
                "backend/data/sina_daily_full/2026-11-16.json",
                "backend/data/sina_daily_full/2026-11-16.json.gz",
            )
            for source in row["sources"]
        ]
if {row["id"] for row in reports} != {REPORT_ID, HISTORY_ID} or {row["id"] for row in runs} != RUN_IDS:
    raise SystemExit("linked_bundle_records_missing")

report_path = ROOT / "docs/research/volume-price-20261116-close-v1.md"
report_path.write_text(compact_body(report_path.read_text(encoding="utf-8")), encoding="utf-8")

bundle_path = ROOT / "research_backfills/linked-volume-price-20261116-v1.json"
bundle_path.write_text(
    json.dumps({"research": reports, "task_runs": runs}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps({"bundle": str(bundle_path), "research": len(reports), "task_runs": len(runs)}, ensure_ascii=False))
