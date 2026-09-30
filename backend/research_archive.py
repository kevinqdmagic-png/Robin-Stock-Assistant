"""Versioned reports and immutable original recommendations backed by JSON."""
import json
import os
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
TRACKS = {"market_review", "dragon_tiger", "low_position", "quant_research", "volume_price", "high_elasticity"}
GROUPS = {"close", "0950", "1440"}
FROZEN = ("id", "date", "published_at", "code", "name", "group", "model", "reason",
          "reference_price", "trigger", "invalid", "sources", "provenance")


def load_document(name, env=None):
    # An explicit deployment override is authoritative; errors must not be hidden.
    override = os.environ.get(env) if env else None
    path = Path(override) if override else DATA / name
    if not override and name == "research.json" and Path("/data/research.json").exists():
        path = Path("/data/research.json")  # Preserve existing production archive.
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("invalid_archive")
    return payload


def validate_document(payload, kind):
    ids = set()
    for row in payload.get("items", []):
        if not isinstance(row, dict) or not row.get("id") or row["id"] in ids:
            raise ValueError("missing_or_duplicate_id")
        ids.add(row["id"])
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row.get("date", ""))):
            raise ValueError("invalid_date")
        if kind == "research":
            if row.get("track") not in TRACKS or not row.get("title") or not row.get("body"):
                raise ValueError("invalid_research_record")
        else:
            if not re.fullmatch(r"\d{6}", str(row.get("code", ""))) or row.get("group") not in GROUPS:
                raise ValueError("invalid_recommendation")
            if row.get("provenance") == "contemporaneous":
                if (not row.get("published_at") or not row.get("reference_price") or
                        not row.get("sources") or not row.get("trigger") or not row.get("invalid")):
                    raise ValueError("missing_contemporaneous_evidence")


def verify_append_only(before, after, kind):
    current = {r["id"]: r for r in after.get("items", [])}
    for old in before.get("items", []):
        new = current.get(old["id"])
        if new is None:
            raise ValueError("historical_record_deleted")
        keys = FROZEN if kind == "recommendations" else tuple(old.keys())
        if any(old.get(key) != new.get(key) for key in keys):
            raise ValueError("historical_record_changed")


def archive_page(track=None, day=None, offset=0, limit=30):
    payload = load_document("research.json", "ROBIN_RESEARCH_FILE")
    rows = payload["items"]
    # Support old production records, which predate id/body.
    rows = [dict(r, body=r.get("body") or r.get("summary", "")) for r in rows
            if isinstance(r, dict) and r.get("track") in TRACKS and r.get("date")]
    if track:
        rows = [r for r in rows if r.get("track") == track]
    if day:
        rows = [r for r in rows if r.get("date") == day]
    rows.sort(key=lambda r: (r["date"], r.get("published_at", "")), reverse=True)
    offset = max(0, int(offset))
    limit = max(1, min(100, int(limit)))
    return {"items": rows[offset:offset + limit], "total": len(rows),
            "offset": offset, "has_more": offset + limit < len(rows)}
