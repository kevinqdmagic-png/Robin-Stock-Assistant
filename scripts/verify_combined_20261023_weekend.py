"""Verify the dated publication's evidence, reuse and non-retroactive accounting."""
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def baseline(path):
    return json.loads(subprocess.check_output(["git", "show", "origin/main:" + path], cwd=ROOT))


reports = read("backend/data/research.json")["items"]
runs = read("backend/data/task_runs.json")["items"]
evidence = read("docs/research/combined-pair-20261023-decision-evidence.json")
tasks = {r["id"]: r for r in read("backend/data/tasks.json")["items"]}
manifest = read("docs/research/combined-pair-20261023-publication-manifest.json")
index = {r["id"]: r for r in reports}
combined = index["combined-pair-20261023-close-v1"]
assert sum(r.get("task_id") == "combined_pair" and r["date"] == "2026-10-23"
           and r.get("eligible_for_integrated_research") is True for r in reports) == 1
assert combined["candidate_count"] == 0 and combined["recommendation_ids"] == []
assert combined["planned_entry_date"] == "2026-10-26"
assert combined["earliest_legal_exit_date_if_bought"] == "2026-10-27"

deps = evidence["collection_attempts"]["first_pass"]["dependency_audit"]
assert set(deps) == {"market_review", "volume_price", "low_position", "dragon_tiger"}
assert set(combined["dependency_report_ids"]) == {d["report_id"] for d in deps.values()}
for task, dep in deps.items():
    r = index[dep["report_id"]]
    assert r["task_id"] == task and r["date"] == "2026-10-23"
    assert r["report_type"] == "full_daily_research" and r["eligible_for_integrated_research"] is True
    assert hashlib.sha256(r["body"].encode()).hexdigest() == dep["body_sha256"]
    assert any(e["task_id"] == task and e["status"] == "completed" and r["id"] in e["report_ids"] for e in runs)

first = evidence["collection_attempts"]["first_pass"]
assert len({r["code"] for r in first["recomputed_broad_pool"]}) == 120
assert len({r["code"] for r in first["deep_pool"]}) == 28
assert len(first["prior_whole_pool"]) == 28
for item in first["recomputed_broad_pool"]:
    if item["high"] > item["low"]:
        expected = (item["close"] - item["low"]) / (item["high"] - item["low"])
        assert abs(item["clv"] - expected) < .00006

original = index[manifest["reused_limitup_report_id"]]
addendum = index["limitup-single-20261023-weekend-evidence-v2"]
assert original["planned_entry_date"] == "2026-10-26" and original["candidate_count"] == 0
assert addendum["reused_full_report_id"] == original["id"]
assert addendum["creates_new_decision"] is False and addendum["creates_new_recommendation"] is False
assert addendum["eligible_for_integrated_research"] is False
assert tasks["combined_pair"]["dependencies"] == list(deps)
assert tasks["combined_pair"]["also_executes_task_ids"] == ["limitup_single"]
assert tasks["limitup_single"]["executor_task_id"] == "combined_pair"
assert tasks["limitup_single"]["independent_schedule_enabled"] is False
assert tasks["limitup_single"]["research_rule_version"] == "limitup_single_v2"
old_tasks = {r["id"]: r for r in baseline("backend/data/tasks.json")["items"]}
assert all(r == tasks[k] for k, r in old_tasks.items() if k not in ("combined_pair", "limitup_single"))

for path in ("backend/data/recommendations.json", "backend/data/volume_price_samples.json",
             "backend/data/research_stocks.json", "app/src/main/assets/research_stocks.json"):
    assert read(path) == baseline(path), "Unexpected new samples or rewritten historical conditions: " + path
now = datetime.now(timezone.utc)
new_ids = set(manifest["report_ids"])
new_receipts = [e for e in runs if new_ids.intersection(e["report_ids"])]
assert len(new_receipts) == 3
for r in [index[key] for key in new_ids]:
    assert datetime.fromisoformat(r["published_at"]) <= now
for e in new_receipts:
    assert datetime.fromisoformat(e["started_at"]) <= datetime.fromisoformat(e["completed_at"]) <= now
    assert e["trigger"] == ("manual" if "orchestration" in e["run_id"] else "scheduled")
    assert e["status"] == "completed" and e["recommendation_ids"] == []
print(json.dumps({"verified": True, "prerequisites": 4, "reused_broad": 120, "reused_deep": 28,
                  "previous_pool_checked": 28, "combined_candidates": 0, "limitup_candidates": 0,
                  "historical_conditions_unchanged": True, "future_timestamps": 0}))
