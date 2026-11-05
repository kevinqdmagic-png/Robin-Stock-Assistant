"""Validated, dated SH/SZ history with explicit provider fallback and units."""
import json
import math
import re
from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from baostock_snapshot import CODE_RE

ROOT = Path(__file__).resolve().parent / "data"
SOURCES = (("baostock", "baostock"),
           ("eastmoney_https_unofficial", "https_daily_full"),
           ("sina_close_snapshot", "sina_daily_full"))
STOCK_CODE_RE = re.compile(r"^(?:sh\.6\d{5}|sz\.(?:00|30)\d{4})$")


def validate_snapshot(payload, day, provider):
    if (payload.get("provider") != provider or payload.get("trade_date") != day
            or payload.get("status") != "historical_observation_only"):
        raise ValueError("snapshot_identity_invalid")
    rows, errors = payload.get("rows", []), payload.get("errors", [])
    coverage = payload.get("coverage", {})
    checked = coverage.get("checked", 0)
    if (checked < 5000 or coverage.get("verified") != len(rows)
            or checked != len(rows) + len(errors)
            or len(rows) / checked < .90
            or abs(coverage.get("coverage_ratio", 0) - len(rows) / checked) > .000001):
        raise ValueError("snapshot_coverage_invalid")
    codes = [r.get("code", "") for r in rows + errors]
    if len(set(codes)) != checked or any(not CODE_RE.fullmatch(c) for c in codes):
        raise ValueError("snapshot_codes_invalid")
    normalized = []
    for row in rows:
        if (row.get("date") != day or row.get("provider") != provider
                or row.get("adjustment") != "none"):
            raise ValueError("snapshot_row_identity_invalid")
        if provider == "sina_close_snapshot":
            stamp = datetime.fromisoformat(row.get("quote_as_of", ""))
            if stamp.tzinfo is None:
                raise ValueError("close_snapshot_timezone_required")
            stamp = stamp.astimezone(ZoneInfo("Asia/Shanghai"))
            if (stamp.date().isoformat() != day or (stamp.hour, stamp.minute) < (15, 0)
                    or row.get("volume_unit") != "shares"):
                raise ValueError("close_snapshot_not_verified_close")
        values = [float(row[k]) for k in ("open", "high", "low", "close", "volume", "amount")]
        o, h, l, c, v, a = values
        if not all(math.isfinite(x) for x in values) or not (0 < l <= min(o, c) <= max(o, c) <= h and v >= 0 and a >= 0):
            raise ValueError("snapshot_ohlcv_invalid")
        item = dict(row)
        # Eastmoney f56 is lots of 100 shares; BaoStock is shares. Preserve raw
        # quantity and explicitly normalize only at the shared read boundary.
        unit = row.get("volume_unit", "shares" if provider == "baostock" else "lots_100_shares")
        if unit not in ("shares", "lots_100_shares"):
            raise ValueError("snapshot_volume_unit_unknown")
        item.update(volume=v * (100 if unit == "lots_100_shares" else 1),
                    volume_unit="shares", native_volume=v, native_volume_unit=unit)
        normalized.append(item)
    # The older sz.3-prefix universe also admitted 399xxx Shenzhen indices.
    # Preserve frozen raw files, but never count those as A-share stocks.
    stocks = [r for r in normalized if STOCK_CODE_RE.fullmatch(r["code"])]
    stock_errors = [e for e in errors if STOCK_CODE_RE.fullmatch(e["code"])]
    stock_checked = len(stocks) + len(stock_errors)
    if stock_checked < 5000 or len(stocks) / stock_checked < .90:
        raise ValueError("stock_only_coverage_invalid")
    return {**payload, "rows": stocks, "errors": stock_errors,
            "source_coverage": payload.get("source_coverage", coverage),
            "excluded_non_stock_count": checked - stock_checked,
            "coverage": {**coverage, "checked": stock_checked, "verified": len(stocks),
                         "errors": len(stock_errors), "coverage_ratio": round(len(stocks) / stock_checked, 6)}}


def read_snapshot(day, root=None):
    day = date.fromisoformat(day).isoformat()
    root = Path(root) if root is not None else ROOT
    failures = []
    for provider, folder in SOURCES:
        try:
            payload = json.loads((root / folder / (day + ".json")).read_text())
            result = validate_snapshot(payload, day, provider)
            return {**result, "ok": True, "fallback_used": provider != "baostock",
                    "source_errors": failures, "historical_only": True}
        except (OSError, ValueError, TypeError, KeyError) as exc:
            failures.append({"provider": provider, "reason": type(exc).__name__ + ":" + str(exc)[:90]})
    return {"ok": False, "trade_date": day, "rows": [], "historical_only": True,
            "status": "validated_daily_snapshot_unavailable", "source_errors": failures}


def history(day, code="", limit=100, offset=0, root=None):
    if code and not CODE_RE.fullmatch(code):
        raise ValueError("invalid_shanghai_shenzhen_code")
    if not 1 <= limit <= 500 or offset < 0:
        raise ValueError("invalid_pagination")
    result = read_snapshot(day, root)
    rows = [r for r in result["rows"] if r["code"] == code] if code else result["rows"]
    return {**result, "count": len(rows), "offset": offset, "rows": rows[offset:offset + limit]}


def source_status(day, root=None):
    root = Path(root) if root is not None else ROOT
    result = read_snapshot(day, root)
    sources = []
    for provider, folder in SOURCES:
        files = sorted((root / folder).glob("20??-??-??.json"), reverse=True)
        sources.append({"provider": provider, "latest_archived_date": files[0].stem if files else None})
    attempt = root / "market_source_status" / ("baostock-" + day + ".json")
    try:
        last_attempt = json.loads(attempt.read_text())
    except (OSError, ValueError):
        last_attempt = None
    return {k: v for k, v in {**result, "sources": sources, "last_baostock_attempt": last_attempt,
            "error_reasons": dict(Counter(e.get("reason", "unknown") for e in result.get("errors", [])))}.items()
            if k not in ("rows", "errors")}
