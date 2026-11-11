"""Regressions for cross-date, offline and concurrent publication failures."""
import importlib.util
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from daily_results import daily_results
from delivery_health import resident_intraday_health

def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

publisher = script("publish_linked_archives")
preparer = script("prepare_task_context")
CN = ZoneInfo("Asia/Shanghai")

def report(rid="study"):
    return {"id": rid, "date": "2026-11-11", "task_id": "market_review", "track": "market_review",
            "title": "研究", "summary": "摘要", "body": "真实研究", "sources": ["https://example.org/evidence"],
            "status": "partial", "report_type": "manual_recovery_research", "published_at": "2026-11-11T19:00:00+08:00"}

def receipt(rid="study-receipt", report_id="study"):
    stamp = "2026-11-11T19:00:00+08:00"
    return {"id": rid, "run_id": rid, "task_id": "market_review", "date": "2026-11-11",
            "status": "partial", "trigger": "scheduled", "started_at": stamp,
            "completed_at": stamp, "recorded_at": stamp, "report_ids": [report_id]}

class RecoveryTests(unittest.TestCase):
    def test_retry_does_not_hide_research_candidates(self):
        detailed = report()
        detailed["research_shadow_candidates"] = [{"task_id": "market_review", "code": "600000"}]
        retry_report = {**report("retry"), "published_at": "2026-11-11T20:00:00+08:00",
                        "report_type": None, "execution_scope": "partial_research_universe"}
        retry = {**receipt("retry-receipt", "retry"), "recorded_at": "2026-11-11T20:00:00+08:00"}
        row = daily_results("2026-11-11", documents=(
            {"items": [{"id": "market_review", "title": "复盘"}]},
            {"items": [receipt(), retry]}, {"items": [detailed, retry_report]}))["items"][0]
        self.assertEqual(row["report_id"], "study")
        self.assertEqual(row["receipt_id"], "study-receipt")
        self.assertEqual(row["latest_attempt_receipt_id"], "retry-receipt")
        self.assertEqual(len(row["research_shadow_candidates"]), 1)
        self.assertFalse(row["full_research_completed"])

    def test_midnight_audit_reads_original_session(self):
        def store(slot):
            return {"ok": True, "store_writable": True, "storage": "railway_persistent_volume",
                    "latest": {"date": "2026-11-12", "status": "observed", "candidates": []},
                    "items": [{"date": "2026-11-11", "status": "observed", "candidates": [{}, {}]}]}
        result = resident_intraday_health(now=datetime(2026, 11, 12, 4, tzinfo=CN),
                                          provider=store, session_day="2026-11-11")
        self.assertEqual(result["date_cn"], "2026-11-11")
        self.assertEqual(result["status"], "complete")

    def test_offline_production_does_not_stop_repository_research(self):
        result = preparer.prepare(now=datetime(2026, 11, 12, 4, tzinfo=CN),
            documents=({"items": []}, {"items": []}, {"items": []}),
            fetcher=lambda path: {"ok": False, "path": path, "errors": ["DNS"]},
            snapshot_reader=lambda day: {"ok": True, "trade_date": day, "provider": "baostock"})
        self.assertEqual(result["research_date"], "2026-11-11")
        self.assertTrue(result["research_can_continue_from_repository"])
        self.assertFalse(result["production_readback_verified"])

    def test_immutable_and_conflicting_records_abort(self):
        base = {"schema_version": 1, "items": [report()]}
        with self.assertRaises(ValueError):
            publisher.merge_append_only(base, {**base, "items": []}, base, "research")
        with self.assertRaisesRegex(ValueError, "conflicting_new_record"):
            publisher.merge_append_only({"items": []}, base,
                {"items": [{**report(), "body": "other writer"}]}, "research")

    def test_broken_receipt_links_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "receipt_report_link_invalid"):
            publisher.check_links({"items": []}, {"items": [receipt()]}, {"study-receipt"})

    def test_bundle_is_idempotent_and_rejects_links_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'backend/data'
            folder.mkdir(parents=True)
            for name in ('research', 'task_runs'):
                (folder / (name + '.json')).write_text(json.dumps({'schema_version': 1, 'items': []}))
            (folder/'tasks.json').write_text(json.dumps({'items': [{'id':'market_review'}]}))
            bundle = {'research': [report()], 'task_runs': [receipt()]}
            publisher.stage_bundle(bundle, cwd=tmp)
            before = {p.name: p.read_bytes() for p in folder.glob('*.json')}
            publisher.stage_bundle(bundle, cwd=tmp)
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.glob('*.json')})
            with self.assertRaisesRegex(ValueError, 'receipt_report_link_invalid'):
                publisher.stage_bundle({'research': [report('new')],
                    'task_runs': [receipt('new-receipt', 'missing')]}, cwd=tmp)
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.glob('*.json')})

    def test_real_git_preserves_concurrent_append_and_other_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            remote, local, other = (tmp / n for n in ("remote.git", "local", "other"))
            def git(cwd, *args):
                return subprocess.check_output(["git", *args], cwd=cwd, stderr=subprocess.DEVNULL).decode().strip()
            git(tmp, "init", "--bare", str(remote))
            git(tmp, "clone", str(remote), str(local))
            git(local, "checkout", "-b", "main")
            for name in ("user.name", "user.email"):
                git(local, "config", name, "test@example.org")
            folder = local / "backend/data"
            folder.mkdir(parents=True)
            for name, doc in (("research", {"schema_version": 1, "items": []}),
                              ("task_runs", {"schema_version": 1, "items": []}),
                              ("tasks", {"items": [{"id": "market_review"}]})):
                (folder / (name + ".json")).write_text(json.dumps(doc))
            git(local, "add", ".")
            git(local, "commit", "-m", "base")
            git(local, "push", "origin", "main")
            base = git(local, "rev-parse", "HEAD")
            git(tmp, "clone", "--branch", "main", str(remote), str(other))
            for name in ("user.name", "user.email"):
                git(other, "config", name, "test@example.org")
            for name, row in (("research", report("other-study")), ("task_runs", receipt("other-receipt", "other-study"))):
                (other / "backend/data" / (name + ".json")).write_text(json.dumps({"schema_version": 1, "items": [row]}))
            (other / "keep.txt").write_text("other writer code")
            git(other, "add", ".")
            git(other, "commit", "-m", "concurrent")
            git(other, "push", "origin", "main")
            for name, row in (("research", report()), ("task_runs", receipt())):
                (folder / (name + ".json")).write_text(json.dumps({"schema_version": 1, "items": [row]}))
            result = publisher.publish(base, cwd=local)
            self.assertTrue(result["published"])
            git(local, "fetch", "origin", "main")
            doc = json.loads(git(local, "show", "origin/main:backend/data/research.json"))
            self.assertEqual({r["id"] for r in doc["items"]}, {"study", "other-study"})
            self.assertEqual(git(local, "show", "origin/main:keep.txt"), "other writer code")
            repeated = publisher.publish(base, cwd=local)
            self.assertFalse(repeated["changed"])
            self.assertEqual(repeated["commit"], result["commit"])

if __name__ == "__main__":
    unittest.main()
