"""Bounded, process-local evidence on market-data transport and freshness.

Operational telemetry only: counters reset on restart and are not trading data.
Every event describes an actual provider attempt, never inferred market breadth.
"""
from collections import Counter, deque
from datetime import datetime
from threading import Lock
from zoneinfo import ZoneInfo

CN = ZoneInfo("Asia/Shanghai")
MAX_EVENTS = 400
_guard = Lock()
_events = deque(maxlen=MAX_EVENTS)
KINDS = {"quote_batch", "minute", "daily"}


def assess_event(kind, requested, rows, source, errors, *, now=None, quote_max_age=120):
    if kind not in KINDS:
        raise ValueError("unsupported_provider_kind")
    now = (now or datetime.now(CN)).astimezone(CN)
    requested = max(0, int(requested))
    rows = list(rows or [])
    count = min(len(rows), requested)
    error_types = sorted({str(e).split(":", 1)[-1].split(" ", 1)[0][:60]
                          for e in (errors or []) if e})
    stale = 0
    unknown = 0
    if kind == "quote_batch":
        for q in rows:
            try:
                stamp = datetime.fromisoformat(str(q.get("as_of", "")))
                if stamp.tzinfo is None:
                    unknown += 1
                    continue
                age = (now - stamp.astimezone(CN)).total_seconds()
                if age < -120 or age > quote_max_age:
                    stale += 1
            except (ValueError, TypeError, AttributeError):
                unknown += 1
    if count == 0:
        status = "unavailable"
    elif count < requested or stale or unknown or error_types:
        status = "degraded"
    else:
        status = "ok"
    return {
        "kind": kind, "at_cn": now.isoformat(timespec="seconds"),
        "requested": requested, "returned": count, "status": status,
        "source": source if source in {
            "eastmoney_batch_quote", "tencent_batch_quote", "mixed_batch_quote",
            "eastmoney_trends", "tencent_minute", "eastmoney_qfq_daily",
            "eastmoney_unadjusted_daily", "tencent_qfq_daily",
            "tencent_unadjusted_daily"
        } else "other_or_missing",
        "stale_quotes": stale, "unknown_quote_timestamps": unknown,
        "errors": error_types,
    }


def record_provider_event(kind, requested, rows, source, errors, *, now=None):
    event = assess_event(kind, requested, rows, source, errors, now=now)
    with _guard:
        _events.append(event)
    return event


def quality_summary():
    with _guard:
        events = list(_events)
    by_kind = {}
    for kind in sorted(KINDS):
        records = [e for e in events if e["kind"] == kind]
        statuses = Counter(e["status"] for e in records)
        errors = Counter(code for row in records for code in row["errors"])
        last = records[-1] if records else None
        by_kind[kind] = {
            "attempts": len(records), "ok": statuses["ok"],
            "degraded": statuses["degraded"], "unavailable": statuses["unavailable"],
            "latest_status": last["status"] if last else "no_observations",
            "latest_at_cn": last["at_cn"] if last else None,
            "latest_source": last["source"] if last else None,
            "latest_requested": last["requested"] if last else None,
            "latest_returned": last["returned"] if last else None,
            "errors": dict(errors.most_common(8)),
        }
    return {
        "ok": True, "status": "observational",
        "scope": "current_process_bounded_provider_attempts",
        "persistent_across_deployments": False,
        "no_observations_means_healthy": False,
        "sample_count": len(events), "by_kind": by_kind,
        "automatic_trade_permission": False,
    }
