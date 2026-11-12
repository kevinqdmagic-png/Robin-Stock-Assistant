#!/usr/bin/env python3
"""Prepare the small linked archive bundle and compact public evidence for 2026-11-12.

The linked bundle lets the repository workflow append research and receipts against
the latest main atomically.  Large source data is retained as a deterministic gzip
archive while the public evidence index keeps the fields needed to audit the report.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_IDS = {
    "market-review-20261112-close-v1",
    "market-review-20261111-event-ecosystem-supplement-v1",
}
RUN_IDS = {
    "market-review-20261112-scheduled-close-v1-completed",
    "market-review-20261111-historical-event-supplement-v1-receipt",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    research_path = ROOT / "backend/data/research.json"
    runs_path = ROOT / "backend/data/task_runs.json"
    research_items = [
        item for item in load(research_path)["items"] if item.get("id") in RESEARCH_IDS
    ]
    run_items = [item for item in load(runs_path)["items"] if item.get("id") in RUN_IDS]
    if {item["id"] for item in research_items} != RESEARCH_IDS:
        raise SystemExit("missing expected research items")
    if {item["id"] for item in run_items} != RUN_IDS:
        raise SystemExit("missing expected task-run items")

    raw_snapshot = ROOT / "backend/data/sina_daily_full/2026-11-12.json"
    compressed_snapshot = raw_snapshot.with_suffix(".json.gz")
    raw_bytes = raw_snapshot.read_bytes()
    with compressed_snapshot.open("wb") as raw_output:
        with gzip.GzipFile(
            filename="2026-11-12.json",
            mode="wb",
            compresslevel=9,
            fileobj=raw_output,
            mtime=0,
        ) as output:
            output.write(raw_bytes)

    full_evidence_path = ROOT / "docs/research/market-review-20261112-evidence.json"
    evidence = load(full_evidence_path)
    compact = {
        key: value
        for key, value in evidence.items()
        if key not in {"broad_pool"}
    }
    compact["broad_pool_archive"] = {
        "count": len(evidence.get("broad_pool", [])),
        "omitted_from_compact_index": True,
        "reason": "完整120只广池包含于本地冻结证据；仓库保留原始新浪快照gzip与28只深筛以便复核。",
    }
    compact["sina_snapshot_archive"] = {
        "path": "backend/data/sina_daily_full/2026-11-12.json.gz",
        "compression": "gzip",
        "uncompressed_bytes": len(raw_bytes),
        "sha256_uncompressed": hashlib.sha256(raw_bytes).hexdigest(),
        "coverage": evidence.get("snapshots", {}).get("sina_close"),
    }
    dump(full_evidence_path, compact)

    for item in research_items:
        item["sources"] = [
            source.replace(
                "backend/data/sina_daily_full/2026-11-12.json",
                "backend/data/sina_daily_full/2026-11-12.json.gz",
            )
            for source in item.get("sources", [])
        ]
    for item in run_items:
        item["sources"] = [
            source.replace(
                "backend/data/sina_daily_full/2026-11-12.json",
                "backend/data/sina_daily_full/2026-11-12.json.gz",
            )
            for source in item.get("sources", [])
        ]

    dump(
        ROOT / "research_backfills/linked-market-review-20261112-v1.json",
        {"research": research_items, "task_runs": run_items},
    )

    research_path.write_bytes(
        subprocess.check_output(
            ["git", "show", "origin/main:backend/data/research.json"], cwd=ROOT
        )
    )
    runs_path.write_bytes(
        subprocess.check_output(
            ["git", "show", "origin/main:backend/data/task_runs.json"], cwd=ROOT
        )
    )
    raw_snapshot.unlink()


if __name__ == "__main__":
    main()
