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
            for name in ("tasks.json", "task_runs.json", "research.json", "recommendations.json", "research_stocks.json")}


def get(path):
    with urlopen(args.base.rstrip("/") + path, timeout=15) as response:
        payload = json.load(response)
    if not payload.get("ok"):
        raise RuntimeError(path + ": API unavailable")
    return payload


def all_rows(path):
    rows = []
    while True:
        page = get(path + "?limit=100&offset=" + str(len(rows)))
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
        reports = all_rows("/api/research")
        receipts = all_rows("/api/task-runs")
        recommendations = all_rows("/api/recommendations")
        stock_catalog = get("/api/research-stocks")
        validate_catalog(stock_catalog, reports)
        verify_catalog_history(expected["research_stocks.json"], stock_catalog)
        for stock in expected["research_stocks.json"]["items"]:
            detail = get("/api/stocks/" + stock["code"] + "/research")
            verify_catalog_history({"items": [stock]}, {"items": [detail["stock"]]})
            linked = get("/api/research?code=" + stock["code"] + "&limit=100")
            report_ids = {r["id"] for r in linked["items"]}
            required = {r for entry in stock["history"] for r in entry["report_ids"]}
            if not required.issubset(report_ids):
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
                          "base": args.base}, ensure_ascii=False))
        break
    except Exception as exc:
        last_error = type(exc).__name__ + ": " + str(exc)
        if time.monotonic() >= deadline:
            raise SystemExit("Production verification failed: " + last_error)
        print("Waiting: " + last_error, flush=True)
        time.sleep(10)
