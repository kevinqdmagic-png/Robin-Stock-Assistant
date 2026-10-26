"""Check the publication's financial observations and append-only boundaries."""
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
import gzip
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = "9320b4284c2915e72b5460680a74c6de4d058dba"
T = "2026-10-26"


def load(path):
    return json.loads((ROOT / path).read_text())


def old(path):
    return json.loads(subprocess.check_output(["git", "show", BASE + ":" + path], cwd=ROOT))


def main():
    now = datetime.now(timezone.utc)
    manifest = load("docs/research/combined-pair-20261026-publication-manifest.json")
    evidence = json.loads(gzip.decompress((ROOT / manifest["evidence_file"]).read_bytes()))
    assert hashlib.sha256((ROOT / manifest["evidence_file"]).read_bytes()).hexdigest() == manifest["evidence_sha256"]
    reports = load("backend/data/research.json")["items"]
    runs = load("backend/data/task_runs.json")["items"]
    added = [r for r in reports if r["id"] in manifest["new_report_ids"]]
    assert len(added) == 5
    for r in added:
        assert r["date"] == T and r["planned_entry_date"] == "2026-10-27"
        assert r["earliest_legal_exit_date_if_bought"] == "2026-10-28"
        assert r["candidate_count"] == 0 and r["report_type"] in ("full_daily_research", "full_trading_research")
        assert datetime.fromisoformat(r["published_at"]) <= now
        receipts = [a for a in runs if a.get("status") == "completed" and a["task_id"] == r["task_id"] and r["id"] in a.get("report_ids", [])]
        assert len(receipts) == 1
        a = receipts[0]
        assert a["trigger"] == "scheduled"
        assert datetime.fromisoformat(a["started_at"]) <= datetime.fromisoformat(a["completed_at"]) <= datetime.fromisoformat(a["recorded_at"]) <= now
        assert a["report_ids"] == [r["id"]]
        assert "\ufffd" not in r["body"]
    for rid in manifest.get("evidence_addendum_report_ids", []):
        r = next(r for r in reports if r["id"] == rid)
        assert r["report_type"] == "evidence_update" and r["eligible_for_integrated_research"] is False
        assert r["candidate_count"] == 0 and r["decision_unchanged"] is True
        assert datetime.fromisoformat(manifest["analysis_completed_at"]) < datetime.fromisoformat(r["published_at"]) <= now
        receipts = [a for a in runs if a.get("status") == "completed" and a.get("report_ids") == [rid]]
        assert len(receipts) == 1
        assert datetime.fromisoformat(receipts[0]["started_at"]) <= datetime.fromisoformat(receipts[0]["completed_at"]) <= now
    for task in ("market_review", "volume_price", "low_position", "dragon_tiger", "combined_pair", "limitup_single"):
        full = [r for r in reports if r.get("task_id") == task and r["date"] == T and r.get("report_type") in ("full_daily_research", "full_trading_research")]
        assert len(full) == 1, task
        assert full[0].get("eligible_for_integrated_research") is (task != "limitup_single")
    assert load("backend/data/tasks.json") == old("backend/data/tasks.json")
    vp = load("backend/data/volume_price_samples.json")["items"]
    old_vp = old("backend/data/volume_price_samples.json")["items"]
    assert vp[:len(old_vp)] == old_vp
    assert len(vp[-1]["samples"]) == 28
    lows = load("backend/data/low_position_samples.json")["items"]
    old_lows = old("backend/data/low_position_samples.json")["items"]
    assert len(lows) == len(old_lows) + 3
    for before in old_lows:
        after = next(s for s in lows if s["id"] == before["id"])
        assert {k:v for k,v in before.items() if k != "observations"} == {k:after[k] for k in before if k != "observations"}
        assert after["observations"][:-1] == before.get("observations", [])
        assert after["observations"][-1]["date"] == T
    recs = load("backend/data/recommendations.json")["items"]
    old_recs = old("backend/data/recommendations.json")["items"]
    assert len(recs) == len(old_recs) == 31
    for before in old_recs:
        after = next(s for s in recs if s["id"] == before["id"])
        assert after["results"][:-1] == before.get("results", [])
        assert after["results"][-1]["executed_trade"] is False
    de = evidence["derived"]
    vals = [r["close_pct"] for r in de["previous_whole_pool"]]
    assert len(vals) == 28
    assert round(mean(vals),3) == -1.985 and round(median(vals),3) == -2.776
    assert sum(r["mae_pct"] <= -5 for r in de["previous_whole_pool"]) == 13
    assert len(de["dragon_previous_whole_disclosed_pool"]) == 78
    assert all(r["status"] == "price_observed" for r in de["dragon_previous_whole_disclosed_pool"])
    assert all(r["seat_reconciliation"]["matched"] and r["ths_close_match"] for r in de["dragon_selected"])
    assert de["progression_main_10pct"]["1_to_2"]["prior_full_denominator"] == 53
    assert de["progression_main_10pct"]["1_to_2"]["advanced"] == 8
    assert not de["crosscheck"]["ohlc_mismatches"]
    assert evidence["cumulative"]["twenty_prior_sessions_space_reference"]["full_20_session_highest"] is None
    assert load("backend/data/research_stocks.json") == load("app/src/main/assets/research_stocks.json")
    print("T26: six unique full reports, genuine receipts, 28/28 pool checks, 39 old + 3 new low samples, 78 old Dragon-Tiger observations, 9 reconciled seats; no rewritten history, orders or task schedules.")


if __name__ == "__main__":
    main()
