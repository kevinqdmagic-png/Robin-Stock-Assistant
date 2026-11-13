#!/usr/bin/env python3
"""Create the connector-sized linked archive bundle for this frozen run."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
research = json.loads((ROOT / "backend/data/research.json").read_text())["items"]
runs = json.loads((ROOT / "backend/data/task_runs.json").read_text())["items"]
report_ids = {"volume-price-20261113-close-v1", "volume-price-20261112-t1-supplement-v1"}
run_ids = {"volume-price-20261113-scheduled-close-v1-completed", "volume-price-20261112-t1-supplement-v1-manual-completed"}
bundle = {
    "research": [x for x in research if x.get("id") in report_ids],
    "task_runs": [x for x in runs if x.get("id") in run_ids],
}
for group in bundle.values():
    for row in group:
        row["sources"] = [s.replace("backend/data/sina_daily_full/2026-11-13.json", "backend/data/sina_daily_full/2026-11-13.json.gz") for s in row.get("sources", [])]
if len(bundle["research"]) != 2 or len(bundle["task_runs"]) != 2:
    raise SystemExit("linked_bundle_records_missing")
target = ROOT / "research_backfills/linked-volume-price-20261113-v1.json"
target.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n")
print(target)
