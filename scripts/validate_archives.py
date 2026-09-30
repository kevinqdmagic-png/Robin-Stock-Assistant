"""CI gate: append-only published reports and recommendations."""
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from research_archive import validate_document, verify_append_only
from task_center import validate_registry, validate_runs, checked_receipt

root = Path(__file__).resolve().parents[1]
base = sys.argv[1] if len(sys.argv) > 1 else None
for filename, kind in (("research.json", "research"), ("recommendations.json", "recommendations")):
    path = "backend/data/" + filename
    after = json.loads((root / path).read_text(encoding="utf-8"))
    validate_document(after, kind)
    if base:
        previous = subprocess.run(["git", "show", base + ":" + path], capture_output=True, text=True)
        if previous.returncode == 0:
            verify_append_only(json.loads(previous.stdout), after, kind)
tasks = json.loads((root / "backend/data/tasks.json").read_text(encoding="utf-8"))
runs = json.loads((root / "backend/data/task_runs.json").read_text(encoding="utf-8"))
reports = json.loads((root / "backend/data/research.json").read_text(encoding="utf-8"))
validate_registry(tasks)
validate_runs(runs, tasks)
for event in runs["items"]:
    if event["status"] == "completed" and checked_receipt(event, reports)["status"] != "completed":
        raise ValueError("completed_receipt_report_missing_or_wrong_task")
if base:
    previous = subprocess.run(["git", "show", base + ":backend/data/task_runs.json"], capture_output=True, text=True)
    if previous.returncode == 0:
        verify_append_only(json.loads(previous.stdout), runs, "task_runs")
print("Archive schemas, task report links and historical-record integrity passed.")
