"""Immutable daily accumulation-shape watch archive (research, not trades)."""
from datetime import datetime
import re
from research_archive import load_document

TASK = "capital_watch_daily"
STAGES = {"accumulation_candidate", "late_accumulation_candidate"}
STATUSES = {"completed", "no_matches", "blocked", "skipped"}


def validate_archive(doc):
    if doc.get("schema_version") != 1 or not isinstance(doc.get("items"), list):
        raise ValueError("invalid_capital_watch_archive")
    ids = set()
    for record in doc["items"]:
        key = record.get("id")
        if not isinstance(key, str) or key in ids or not re.fullmatch(r"capital-watch-[0-9]{8}-[0-9]+", key):
            raise ValueError("invalid_capital_watch_id")
        ids.add(key)
        date = record.get("date", "")
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(date)):
            raise ValueError("invalid_capital_watch_date")
        stamp = datetime.fromisoformat(record["published_at"])
        if stamp.tzinfo is None or record.get("status") not in STATUSES:
            raise ValueError("invalid_capital_watch_clock_or_status")
        candidates = record.get("candidates")
        if not isinstance(candidates, list) or len(candidates) > 5:
            raise ValueError("too_many_capital_watch_candidates")
        if record.get("status") != "completed" and candidates:
            raise ValueError("candidates_on_unverified_run")
        if record.get("status") == "completed" and not candidates:
            raise ValueError("empty_completed_research")
        seen = set()
        for item in candidates:
            code = item.get("code")
            if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code) or code in seen:
                raise ValueError("invalid_candidate_code")
            seen.add(code)
            if item.get("stage") not in STAGES or item.get("as_of") != date:
                raise ValueError("unverified_capital_watch_candidate")
            if not item.get("source") or not item.get("evidence") or not item.get("risk"):
                raise ValueError("missing_capital_watch_evidence")
        if not isinstance(record.get("scanned"), int) or record["scanned"] < 0:
            raise ValueError("invalid_capital_watch_scope")
        if not isinstance(record.get("valid_daily"), int) or record["valid_daily"] < 0:
            raise ValueError("invalid_daily_sample_count")
    return doc


def verify_append_only(old, new):
    validate_archive(old)
    validate_archive(new)
    by_id = {x["id"]: x for x in new["items"]}
    for row in old["items"]:
        if by_id.get(row["id"]) != row:
            raise ValueError("capital_watch_history_mutated")


def page(limit=10):
    doc = validate_archive(load_document("capital_watch.json", "ROBIN_CAPITAL_WATCH_FILE"))
    rows = sorted(doc["items"], key=lambda r: (r["date"], r["published_at"], r["id"]), reverse=True)
    latest = rows[0] if rows else None
    return {
        "latest": latest, "history": [{
            "date": x["date"], "status": x["status"],
            "candidate_count": len(x["candidates"]), "scanned": x["scanned"],
            "valid_daily": x["valid_daily"], "published_at": x["published_at"]
        } for x in rows[:max(1, min(int(limit), 30))]],
        "total_runs": len(rows), "execution_source": "published_github_actions_archives",
        "manual_query_available": True, "selection_validated": False,
    }
