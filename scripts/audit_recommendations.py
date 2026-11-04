"""Audit archived recommendation provenance without changing historical records.

Usage: python scripts/audit_recommendations.py [path-to-recommendations.json]
Outputs aggregate evidence counts; never treats a filled results field as a verified trade.
"""
import json
import sys
from collections import Counter
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / "backend" / "data" / "recommendations.json"

def audit(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("recommendations.items must be a list")
    ids = [r.get("id") for r in items]
    if any(not x for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("missing or duplicate recommendation IDs")
    provenance = Counter(r.get("provenance") or "missing" for r in items)
    stages = Counter(r.get("current_stage") or "missing" for r in items)
    task_ids = Counter(r.get("task_id") or "missing" for r in items)
    evidence = {
        "has_reference_price": sum(r.get("reference_price") is not None for r in items),
        "has_results_field": sum("results" in r for r in items),
        "eligible_for_existing_price_observation": sum(
            r.get("provenance") == "contemporaneous"
            and r.get("published_at")
            and r.get("reference_price") is not None
            for r in items
        ),
        "requires_distinct_close_research_validation": sum(
            r.get("provenance") == "contemporaneous_close_research" for r in items
        ),
    }
    return {
        "archive": str(path), "total": len(items),
        "provenance": dict(sorted(provenance.items())),
        "stages": dict(sorted(stages.items())),
        "task_ids": dict(sorted(task_ids.items())),
        "evidence": evidence,
        "caveat": "Eligibility is not verified performance; forward daily bars, corporate actions, and entry feasibility must be checked.",
    }

if __name__ == "__main__":
    print(json.dumps(audit(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT), ensure_ascii=False, indent=2))
