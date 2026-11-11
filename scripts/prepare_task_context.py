#!/usr/bin/env python3
"""Prepare research inputs even when the production API cannot be reached.

Repository evidence permits research to continue; it never proves deployment.
No writes, trades, retroactive signals or status promotions occur here.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from daily_results import daily_results
from daily_snapshot import read_snapshot
from delivery_health import build_delivery_health
from learning_loop import latest_completed_session, is_session
from research_recovery import recovery_backlog
from task_center import context

CN = ZoneInfo("Asia/Shanghai")
BASE = "https://robin-stock-api-production.up.railway.app"


def fetch(path, *, base=BASE, attempts=3, opener=urlopen):
    errors = []
    for attempt in range(attempts):
        try:
            with opener(base.rstrip("/") + path, timeout=8) as response:
                payload = json.load(response)
            if not isinstance(payload, dict) or payload.get("ok") is not True:
                raise ValueError("api_payload_not_ok")
            return {"ok": True, "path": path, "attempts": attempt + 1, "payload": payload,
                    "errors": errors}
        except Exception as exc:
            errors.append({"type": type(exc).__name__, "detail": str(exc)[:240]})
            if attempt + 1 < attempts:
                time.sleep(.25 * (attempt + 1))
    return {"ok": False, "path": path, "attempts": attempts, "errors": errors}


def prepare(*, day=None, now=None, fetcher=fetch, documents=None, snapshot_reader=read_snapshot):
    now = (now or datetime.now(CN)).astimezone(CN)
    completed = latest_completed_session(now)
    if completed is None:
        raise ValueError("completed_session_calendar_unverified")
    if day is not None:
        from datetime import date
        selected = date.fromisoformat(day)
        if selected > completed or is_session(selected) is not True:
            raise ValueError("research_day_not_completed_session")
    else:
        selected = completed
    day = selected.isoformat()
    documents = documents or context()
    tasks, runs, reports = documents
    local_results = daily_results(day, documents=documents, now=now)
    paths = ("/health", "/api/daily-results?date=" + day,
             "/api/operations/delivery?date=" + day,
             "/api/market/data-status?date=" + day)
    with ThreadPoolExecutor(max_workers=4) as pool:
        checks = list(pool.map(fetcher, paths))
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        sha = None
    health = checks[0].get("payload", {})
    production_same_revision = bool(sha and health.get("build_commit") == sha and all(c["ok"] for c in checks))
    backlog = recovery_backlog(limit=200, documents=documents, now=now)
    for key in ("items", "pending_not_yet_due"):
        backlog[key] = [{k: r.get(k) for k in ("date", "task_id", "status", "report_id", "due_at_cn")}
                        for r in backlog[key]]
    snapshot = snapshot_reader(day)
    return {
        "research_date": day, "prepared_at_cn": now.isoformat(timespec="seconds"),
        "repository_sha": sha, "research_can_continue_from_repository": True,
        "production_readback_verified": production_same_revision,
        "production_checks": checks,
        "repository_delivery": build_delivery_health(tasks, runs, reports, now=now, session_day=day),
        "repository_daily_results": local_results,
        "repository_backlog": backlog,
        "archived_daily": {k: snapshot.get(k) for k in
                           ("ok", "trade_date", "provider", "coverage", "fallback_used", "source_errors")},
        "instructions": "Use linked report bodies and raw evidence to finish missing research. API failure blocks production verification only. Never relabel a partial study as complete or invent past signals.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date")
    parser.add_argument("--output", default="task-context.json")
    args = parser.parse_args()
    result = prepare(day=args.date)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("research_date", "repository_sha", "production_readback_verified", "archived_daily")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
