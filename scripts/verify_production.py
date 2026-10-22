"""Verify that the deployed API includes this commit's frozen research data."""
import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.request import urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from task_center import data_revision
from research_archive import verify_append_only
from research_stocks import validate_catalog, verify_catalog_history
from learning_loop import validate_learning_archive

parser = argparse.ArgumentParser()
parser.add_argument("--base", default="https://robin-stock-api-production.up.railway.app")
parser.add_argument("--wait", type=int, default=600)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
app_source = (root / "backend/app.py").read_text(encoding="utf-8")
version_match = re.search(r'^API_VERSION\s*=\s*"([^"]+)"', app_source, re.MULTILINE)
if version_match is None:
    version_match = re.search(r'FastAPI\(title=.*?version="([^"]+)"', app_source)
if version_match is None:
    raise RuntimeError("backend version declaration not found")
version = version_match[1]
expected_revision = data_revision()
expected = {name: json.loads((root / "backend/data" / name).read_text(encoding="utf-8"))
            for name in ("tasks.json", "task_runs.json", "research.json", "recommendations.json", "research_stocks.json", "capital_watch.json")}


def get(path):
    with urlopen(args.base.rstrip("/") + path, timeout=15) as response:
        payload = json.load(response)
    if not payload.get("ok"):
        raise RuntimeError(path + ": API unavailable")
    return payload


def all_rows(path):
    rows = []
    separator = "&" if "?" in path else "?"
    while True:
        page = get(path + separator + "limit=100&offset=" + str(len(rows)))
        current = page.get("items", [])
        rows.extend(current)
        if not page.get("has_more"):
            return {"items": rows}
        if not current:
            raise RuntimeError("pagination did not advance")


deadline = time.monotonic() + args.wait
last_error = "not checked"
while True:
    try:
        health = get("/health")
        if health.get("version") != version:
            raise RuntimeError("waiting for backend version " + version)
        tasks = get("/api/tasks")
        if not {r["id"] for r in expected["tasks.json"]["items"]}.issubset({r["id"] for r in tasks["items"]}):
            raise RuntimeError("task registry not yet deployed")
        actual_tasks = {r["id"]: r for r in tasks["items"]}
        for task in expected["tasks.json"]["items"]:
            fields = ("enabled", "schedule", "timezone", "timing_mode", "execution_mode",
                      "executor_task_id", "effective_enabled", "executes_missing_tasks")
            if any(actual_tasks[task["id"]].get(key) != task.get(key) for key in fields):
                raise RuntimeError("task configuration not yet deployed: " + task["id"])
        live_1440 = get("/api/intraday-live?slot=late_pair")
        live_0950 = get("/api/intraday-live?slot=early_pair")
        if any(result.get("scheduler_started") is not True or
               result.get("store_writable") is not True or
               result.get("storage") != "railway_persistent_volume" or
               result.get("strategy_validated") is not False or
               result.get("recommendation_executable") is not False
               for result in (live_1440, live_0950)):
            raise RuntimeError("resident intraday scheduler or persistent store not ready: " +
                               repr({"1440_started":live_1440.get("scheduler_started"),
                                     "1440_writable":live_1440.get("store_writable"),
                                     "1440_storage":live_1440.get("storage"),
                                     "1440_backtest":live_1440.get("strategy_validated"),
                                     "1440_executable":live_1440.get("recommendation_executable"),
                                     "0950_started":live_0950.get("scheduler_started"),
                                     "0950_writable":live_0950.get("store_writable")}))
        if live_1440.get("slot") != "late_pair" or live_0950.get("slot") != "early_pair":
            raise RuntimeError("resident intraday slot mismatch")
        reports = all_rows("/api/research")
        receipts = all_rows("/api/task-runs")
        recommendations = all_rows("/api/recommendations")
        online_learning = get("/api/learning")
        repo_learning = validate_learning_archive(json.loads(
            (root / "backend/data/learning.json").read_text(encoding="utf-8")))
        if online_learning.get("snapshot_count", 0):
            last = online_learning.get("latest") or {}
            if repo_learning["runs"] and last.get("date", "") < repo_learning["runs"][-1]["date"]:
                raise RuntimeError("daily learning data not yet deployed")
        elif repo_learning["runs"]:
            raise RuntimeError("daily learning archive not yet deployed")
        if online_learning.get("automatic_training") is not False:
            raise RuntimeError("unverified training claim")

        from capital_watch import verify_append_only as verify_watch_append_only
        capital_watch = get("/api/capital-watch")
        if capital_watch.get("selection_validated") is not False or capital_watch.get("manual_query_available") is not True:
            raise RuntimeError("capital watch manual query / validation flags incorrect")
        # A newer production scan can have more immutable records than this commit.
        capital_items = []
        for summary in capital_watch.get("history", []):
            if not isinstance(summary, dict) or not summary.get("date"):
                raise RuntimeError("capital watch history schema invalid")
        if expected["capital_watch.json"]["items"]:
            latest_expected = expected["capital_watch.json"]["items"][-1]
            if capital_watch.get("latest") is None or capital_watch["latest"]["date"] < latest_expected["date"]:
                raise RuntimeError("daily capital watch archive not yet deployed")
        stock_catalog = get("/api/research-stocks")
        validate_catalog(stock_catalog, reports)
        verify_catalog_history(expected["research_stocks.json"], stock_catalog)
        for stock in expected["research_stocks.json"]["items"]:
            detail = get("/api/stocks/" + stock["code"] + "/research")
            verify_catalog_history({"items": [stock]}, {"items": [detail["stock"]]})
            linked = all_rows("/api/research?code=" + stock["code"])
            report_ids = {r["id"] for r in linked["items"]}
            required = {r for entry in stock["history"] for r in entry["report_ids"]}
            acknowledged_gaps = {gap["report_id"] for gap in detail.get("archive_gaps", [])}
            if not (required - acknowledged_gaps).issubset(report_ids):
                raise RuntimeError("stock research links not yet deployed: " + stock["code"])
        # A newer concurrent deployment may legitimately append records.
        for filename, actual, kind in (("research.json", reports, "research"),
                                        ("task_runs.json", receipts, "task_runs"),
                                        ("recommendations.json", recommendations, "recommendations")):
            verify_append_only(expected[filename], actual, kind)
        print(json.dumps({"verified": True, "version": version, "tasks": len(tasks["items"]),
                          "reports": len(reports["items"]), "receipts": len(receipts["items"]),
                          "recommendations": len(recommendations["items"]),
                          "research_stocks": len(stock_catalog["items"]),
                          "data_revision_matches": health.get("data_revision") == expected_revision,
                          "intraday_scheduler_running": live_1440.get("scheduler_started"),
                          "intraday_storage_writable": live_1440.get("store_writable"),
                          "late_pair_status": live_1440.get("current_status"),
                          "base": args.base}, ensure_ascii=False))
        break
    except Exception as exc:
        last_error = type(exc).__name__ + ": " + str(exc)
        if time.monotonic() >= deadline:
            raise SystemExit("Production verification failed: " + last_error)
        print("Waiting: " + last_error, flush=True)
        time.sleep(10)
