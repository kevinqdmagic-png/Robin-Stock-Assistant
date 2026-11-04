"""Read-only validated BaoStock historical snapshot. No live price claims."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "data" / "baostock"
DATE_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}$")
CODE_RE = re.compile(r"^(sh\.6|sz\.[03])\d{5}$")


def load_snapshot(day: str, code: str = "", limit: int = 100, offset: int = 0):
    if not DATE_RE.fullmatch(day):
        raise ValueError("invalid_trade_date")
    if code and not CODE_RE.fullmatch(code):
        raise ValueError("invalid_shanghai_shenzhen_code")
    if limit < 1 or limit > 500 or offset < 0:
        raise ValueError("invalid_pagination")
    path = ROOT / (day + ".json")
    if not path.is_file():
        return {"ok": False, "status": "validated_snapshot_not_deployed", "trade_date": day, "rows": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    coverage = payload.get("coverage") or {}
    rows = payload.get("rows") or []
    if (payload.get("provider") != "baostock" or payload.get("trade_date") != day
            or payload.get("status") != "historical_observation_only"
            or len(rows) != coverage.get("verified")
            or coverage.get("checked", 0) < 5000
            or coverage.get("coverage_ratio", 0) < 0.90
            or any(not CODE_RE.fullmatch(str(row.get("code", ""))) or row.get("date") != day for row in rows)):
        return {"ok": False, "status": "snapshot_validation_failed", "trade_date": day, "rows": []}
    selected = [row for row in rows if row["code"] == code] if code else rows
    return {"ok": True, "status": "validated_historical_observation", "trade_date": day,
            "provider": "baostock", "scope": "Shanghai+Shenzhen; Beijing excluded",
            "coverage": coverage, "count": len(selected), "offset": offset,
            "rows": selected[offset:offset + limit]}
