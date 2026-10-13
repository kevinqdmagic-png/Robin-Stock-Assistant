#!/usr/bin/env python3
"""Run after a verified A-share close and stage a single immutable ledger snapshot.

No AI weights are trained; candidate thresholds are evaluated in chronological
shadow validation only. GitHub Actions uploads this with a blob-SHA compare gate.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import _get_daily
from learning_loop import build_snapshot, append_snapshot, validate_learning_archive
from research_archive import load_document

CN = ZoneInfo("Asia/Shanghai")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "backend" / "data" / "learning.json"))
    parser.add_argument("--now", help="ISO timestamp for deterministic local testing")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(CN)
    if now.tzinfo is None:
        parser.error("--now must include a UTC offset")
    path = Path(args.output)
    document = json.loads(path.read_text(encoding="utf-8"))
    validate_learning_archive(document)
    recs = load_document("recommendations.json", "ROBIN_RECOMMENDATIONS_FILE")["items"]

    def provider(code):
        return _get_daily(code, adjust="0")  # Unadjusted, do not mix with adjusted reference.
    snapshot = build_snapshot(recs, provider, now=now)
    updated, changed = append_snapshot(document, snapshot)
    if changed:
        validate_learning_archive(updated)
        path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "changed": changed, "date": snapshot["date"],
        "status": snapshot["status"], "sample_count": snapshot.get("sample_count", 0),
        "validation": (snapshot.get("validation") or {}).get("status"),
    }, ensure_ascii=False))
    # In a real market session, do not quietly treat a total provider outage as progress.
    if changed and snapshot.get("sample_count") and snapshot["status_counts"].get(
            "provider_unavailable", 0) == snapshot["sample_count"]:
        print("All providers unavailable; preserve a visible failure rather than committing an empty success.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
