"""CI gate: append-only published reports and recommendations."""
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from research_archive import validate_document, verify_append_only

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
print("Archive schemas and historical-record integrity passed.")
