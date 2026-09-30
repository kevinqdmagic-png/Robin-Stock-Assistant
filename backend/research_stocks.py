"""Dated research rationales for a watchlist, separate from daily trading picks."""
import re
from datetime import date

from research_archive import load_document
from task_center import belongs, paginate


def validate_catalog(document, reports):
    if document.get("schema_version") != 1:
        raise ValueError("invalid_stock_catalog_version")
    report_map = {r["id"]: r for r in reports["items"]}
    codes, episodes = set(), set()
    for stock in document.get("items", []):
        code = stock.get("code", "")
        if not re.fullmatch(r"[0-9]{6}", code) or code in codes or not stock.get("name"):
            raise ValueError("invalid_or_duplicate_stock")
        codes.add(code)
        if stock.get("role") not in {"core", "comparison", "research"}:
            raise ValueError("invalid_research_role")
        if not isinstance(stock.get("default_watch"), bool) or not stock.get("history"):
            raise ValueError("missing_stock_history")
        for entry in stock["history"]:
            if not entry.get("id") or entry["id"] in episodes:
                raise ValueError("duplicate_research_episode")
            episodes.add(entry["id"])
            date.fromisoformat(entry["date"])
            if not entry.get("reason") or not entry.get("evidence_status") or not entry.get("sources"):
                raise ValueError("missing_research_provenance")
            if not entry.get("validation") or not entry.get("risk") or not entry.get("report_ids"):
                raise ValueError("missing_research_conditions")
            for report_id in entry["report_ids"]:
                report = report_map.get(report_id)
                if report is None or stock["name"] not in report.get("body", ""):
                    raise ValueError("stock_report_link_invalid")


def verify_catalog_history(before, after):
    current = {s["code"]: s for s in after["items"]}
    for old in before.get("items", []):
        new = current.get(old["code"])
        if new is None or new["name"] != old["name"]:
            raise ValueError("historical_stock_deleted_or_renamed")
        episodes = {r["id"]: r for r in new["history"]}
        if any(episodes.get(r["id"]) != r for r in old["history"]):
            raise ValueError("historical_stock_reason_changed")


def catalog():
    document = load_document("research_stocks.json", "ROBIN_RESEARCH_STOCKS_FILE")
    reports = load_document("research.json", "ROBIN_RESEARCH_FILE")
    validate_catalog(document, reports)
    return document


def stock_research(code):
    if not re.fullmatch(r"[0-9]{6}", code):
        return {"ok": False, "status": "invalid_code"}
    document = catalog()
    stock = next((s for s in document["items"] if s["code"] == code), None)
    return {"ok": True, "status": "ok" if stock else "no_research_record",
            "stock": stock, "notice": document.get("notice", "")}


def stock_reports(code, task="", track="", day="", offset=0, limit=30):
    result = stock_research(code)
    if not result["ok"]:
        return {**result, "items": [], "total": 0, "has_more": False}
    ids = {report for entry in (result.get("stock") or {}).get("history", [])
           for report in entry["report_ids"]}
    reports = load_document("research.json", "ROBIN_RESEARCH_FILE")["items"]
    task_row = None
    if task:
        registry = load_document("tasks.json", "ROBIN_TASKS_FILE")["items"]
        task_row = next((r for r in registry if r["id"] == task), None)
        if task_row is None:
            raise ValueError("unknown_task")
    rows = [r for r in reports if r["id"] in ids and (not task_row or belongs(r, task_row))
            and (not track or r.get("track") == track) and (not day or r.get("date") == day)]
    return {"ok": True, **paginate(rows, offset, limit)}
