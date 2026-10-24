"""Restore the two known damaged blobs without dropping published records."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "7a0eb47b508b93a7d007459a4bd080eed899aed0"

def load(path):
    return json.loads((ROOT / path).read_bytes())

def recover():
    # This one-off recovery must never overwrite a later valid publication.
    current = ROOT / 'backend/data/research.json'
    try:
        existing = json.loads(current.read_bytes())
    except (ValueError, UnicodeDecodeError):
        existing = None
    if existing is not None:
        raise RuntimeError('Archive is already readable; refusing to replace published history')
    before = {}
    for name in ("research.json", "volume_price_samples.json"):
        path = "backend/data/" + name
        before[name] = json.loads(subprocess.check_output(["git", "show", BASE + ":" + path], cwd=ROOT))
    report = load("docs/research/volume-price-20261023-close-v1.json")
    evidence = load("docs/research/volume-price-20261023-close-evidence.json")
    research = before["research.json"]
    volume = before["volume_price_samples.json"]
    research["items"].append(report)
    stamp = report["recorded_at"]
    volume["items"].extend([
        {
            "id": "volume-price-20261022-validation-20261023-v1", "date": "2026-10-23",
            "recorded_at": stamp, "task_id": "volume_price", "kind": "full_forward_price_validation",
            "origin_cohort_id": evidence["previous_cohort_id"],
            "origin_report_ids": ["volume-price-20261022-close-v1"], "report_ids": [report["id"]],
            "rule_version": "volume_price_close_v4", "full_validation_completed": True,
            "full_pool_summary": evidence["previous_pool_statistics"],
            "full_pool_validations": evidence["previous_pool_validation"],
            "executed_trade_count": 0, "executable_strategy_statistics": None,
        },
        {
            "id": "volume-price-20261023-close-v1-cohort", "date": "2026-10-23", "task_id": "volume_price",
            "frozen_at": stamp, "report_ids": [report["id"]], "rule_version": "volume_price_close_v4",
            "data_cutoff_at": "2026-10-23T15:00:00+08:00", "broad_pool_count": 120,
            "broad_pool_verified_count": 120, "deep_screen_count": 28,
            "deep_adjusted_history_verified_count": 28, "eligible_for_model_statistics": True,
            "provenance": "contemporaneous_full_market_research", "samples": evidence["deep_pool"],
        },
    ])
    volume["validation_status"] = "append_only_forward_validation_current_through_2026-10-23"
    for name, document in before.items():
        (ROOT / "backend/data" / name).write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("Recovered 111 historical reports plus the original 23 October report; 18 historical volume records plus its two original records.")

if __name__ == "__main__":
    recover()
