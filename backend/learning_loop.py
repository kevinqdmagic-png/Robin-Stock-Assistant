"""Auditable daily forward-learning ledger (observation, not verified trading P&L).

An immutable, date-stamped snapshot is appended after each valid A-share close.
An exchange-session calendar defines horizons, never the available candles alone.
The only inputs to exploratory feature gates predate the signal anchor.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from statistics import mean, median
from zoneinfo import ZoneInfo

from analytics import clean_bars
from trading_calendar import CLOSURES_2026

CN = ZoneInfo("Asia/Shanghai")
HORIZONS = (1, 2, 5, 10)
VERSION = "forward_learning_v1"
MIN_TRAIN = 24
MIN_TEST = 12
MIN_DATES = 20


def is_session(day):
    key = day.isoformat()
    if day.year != 2026:
        return None
    return day.weekday() < 5 and not any(a <= key <= b for a, b in CLOSURES_2026)


def nth_session_after(day, n):
    if n < 1:
        raise ValueError("horizon_must_be_positive")
    for _ in range(n):
        while True:
            day += timedelta(days=1)
            state = is_session(day)
            if state is None:
                return None
            if state:
                break
    return day


def _ts(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("unqualified_publication_time")
    return result.astimezone(CN)


def _number(value):
    try:
        result = float(value)
        if not 0 < result < 100000:
            return None
        return result
    except (ValueError, TypeError):
        return None


def _features_before_anchor(bars, anchor):
    earlier = [row for row in bars if row["date"] < anchor.isoformat()]
    if len(earlier) < 61:
        return {"available": False, "reason": "less_than_61_prior_daily_bars"}
    try:
        from capital_behavior import classify
        result = classify(earlier)
        return {"available": True, "as_of": earlier[-1]["date"],
                "model_version": result["version"],
                "score": result["exploratory_score"], "stage": result["stage"]}
    except (ValueError, TypeError) as error:
        return {"available": False, "reason": type(error).__name__}


def _corporate_action_issues(bars, anchor, end):
    """Flag price-change continuity conflicts; no adjusted-price assertions."""
    prior = None
    for row in bars:
        day = row["date"]
        if day > end:
            break
        if prior is not None and anchor <= day:
            reported = row.get("pct")
            if reported not in (None, ""):
                try:
                    observed = (row["close"] / prior["close"] - 1) * 100
                    if abs(observed - float(reported)) > 1:
                        return True
                except (TypeError, ValueError, ZeroDivisionError):
                    return True
        prior = row
    return False


def evaluate(record, raw_bars, source, *, as_of):
    """Price-observation cohorts only. Never claim filled orders or executable return."""
    anchor_str = record.get("date")
    output = {
        "signal_id": record.get("id"), "code": record.get("code"),
        "strategy": record.get("strategy") or record.get("model") or "unspecified",
        "task_id": record.get("task_id"),
        "signal_date": anchor_str,
        "basis": "signal_day_unadjusted_close_proxy_not_entry_fill",
        "executed_trade": False, "executable_net_return_pct": None,
        "source": source, "horizons": [],
    }
    if record.get("provenance") != "contemporaneous":
        return {**output, "status": "ineligible_retrospective"}
    if not record.get("published_at") or not anchor_str:
        return {**output, "status": "ineligible_missing_timestamp"}
    try:
        anchor = date.fromisoformat(record.get("planned_entry_date") or anchor_str)
        published = _ts(record["published_at"])
        if is_session(anchor) is not True:
            return {**output, "status": "ineligible_unknown_or_closed_anchor"}
        following = nth_session_after(anchor, 1)
        if following is None:
            return {**output, "status": "unknown_future_calendar"}
        cutoff = datetime.combine(following, time(9, 30), CN)
        if published >= cutoff:
            return {**output, "status": "ineligible_published_after_next_open"}
        if published.date() > anchor:
            return {**output, "status": "ineligible_late_publication"}
        if not raw_bars or not source:
            return {**output, "status": "provider_unavailable"}
        bars = clean_bars(raw_bars)
        by_day = {row["date"]: row for row in bars}
        base = by_day.get(anchor.isoformat())
        if base is None:
            return {**output, "status": "anchor_daily_bar_missing"}
        if not base.get("volume") or base["volume"] <= 0:
            return {**output, "status": "anchor_volume_unverified"}
        if _corporate_action_issues(bars, anchor.isoformat(), as_of.isoformat()):
            return {**output, "status": "quarantine_corporate_action_or_price_disagreement"}
        output.update(anchor_date=anchor.isoformat(), anchor_close=round(base["close"], 4),
                      feature_snapshot=_features_before_anchor(bars, anchor))
        for horizon in HORIZONS:
            maturity = nth_session_after(anchor, horizon)
            if maturity is None:
                output["horizons"].append({"h": horizon, "status": "unknown_calendar"})
                continue
            day = maturity.isoformat()
            if maturity > as_of:
                output["horizons"].append({"h": horizon, "date": day, "status": "pending"})
                continue
            target = by_day.get(day)
            # No shift to the next available stock bar: suspension is not a trading session.
            missing_days = [
                nth_session_after(anchor, j).isoformat()
                for j in range(1, horizon + 1)
                if nth_session_after(anchor, j) is not None
                and nth_session_after(anchor, j).isoformat() not in by_day
            ]
            if target is None or missing_days:
                output["horizons"].append({
                    "h": horizon, "date": day, "status": "missing_or_suspended_session",
                    "missing_dates": missing_days})
                continue
            path = [by_day[nth_session_after(anchor, j).isoformat()]
                    for j in range(1, horizon + 1)]
            output["horizons"].append({
                "h": horizon, "date": day, "status": "observed",
                "close_pct": round((target["close"] / base["close"] - 1) * 100, 3),
                "mfe_pct": round((max(row["high"] for row in path) / base["close"] - 1) * 100, 3),
                "mae_pct": round((min(row["low"] for row in path) / base["close"] - 1) * 100, 3),
            })
        mature2 = next(p for p in output["horizons"] if p["h"] == 2)
        output["status"] = "observed" if mature2["status"] == "observed" else (
            "pending" if mature2["status"] == "pending" else "partially_observed")
        if mature2["status"] == "observed":
            t2 = mature2["close_pct"]
            reasons = []
            if t2 <= -2:
                reasons.append("T2_price_proxy_loss_over_2pct")
            if mature2["mae_pct"] <= -5:
                reasons.append("T2_intraday_adverse_excursion_over_5pct")
            if t2 > 0 and mature2["mae_pct"] < -4:
                reasons.append("positive_close_but_deep_interim_drawdown")
            output["attribution"] = reasons or ["no_preset_failure_flag"]
        return output
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        return {**output, "status": "invalid_evidence",
                "error_code": type(error).__name__}


def _obs(row, horizon):
    return next((x for x in row.get("horizons", []) if x["h"] == horizon
                 and x["status"] == "observed"), None)


def _metric(rows):
    if not rows:
        return {"count": 0, "mean_t2_pct": None, "win_rate_t2_pct": None}
    vals = [_obs(row, 2)["close_pct"] for row in rows]
    adverse = [_obs(row, 2)["mae_pct"] for row in rows]
    return {"count": len(rows),
            "unique_signal_dates": len({r["signal_date"] for r in rows}),
            "mean_t2_pct": round(mean(vals), 3),
            "median_t2_pct": round(median(vals), 3),
            "win_rate_t2_pct": round(sum(x > 0 for x in vals) / len(vals) * 100, 2),
            "median_t2_mae_pct": round(median(adverse), 3)}


def evaluate_shadow_rules(evaluations):
    """Date-held-out threshold proposals. No auto-promotion or parameter overwrites."""
    eligible = [
        r for r in evaluations if _obs(r, 2) is not None
        and r.get("feature_snapshot", {}).get("available")
    ]
    # Freeze cohorts by prediction dates so the same day's correlated picks do not cross splits.
    dates = sorted({r["signal_date"] for r in eligible})
    info = {
        "model_version": VERSION, "total_mature_t2_featured": len(eligible),
        "unique_cohort_dates": len(dates), "promotion_authorized": False,
        "strategy_active_rules_changed": False, "rule_proposals": [],
    }
    if len(eligible) < MIN_TRAIN + MIN_TEST or len(dates) < MIN_DATES:
        return {**info, "status": "insufficient_verified_proxy_samples",
                "minimum_samples": MIN_TRAIN + MIN_TEST, "minimum_unique_dates": MIN_DATES}
    split = dates[max(1, int(len(dates) * 0.7))]
    train = [r for r in eligible if r["signal_date"] < split]
    test = [r for r in eligible if r["signal_date"] >= split]
    if len(train) < MIN_TRAIN or len(test) < MIN_TEST:
        return {**info, "status": "insufficient_chronological_split",
                "train_count": len(train), "holdout_count": len(test)}
    info.update(status="shadow_validation", training_end=train[-1]["signal_date"],
                holdout_start=split, training=_metric(train), holdout=_metric(test))
    options = []
    for threshold in (50, 65, 80):  # A priori, not optimized on holdout.
        picked_train = [r for r in train if r["feature_snapshot"]["score"] >= threshold]
        if len(picked_train) < 12:
            continue
        uplift = _metric(picked_train)["mean_t2_pct"] - _metric(train)["mean_t2_pct"]
        options.append((uplift, threshold, len(picked_train)))
    if not options:
        return {**info, "status": "no_threshold_with_enough_training_samples"}
    # Select on training ONLY, then report test. No backfit to test.
    train_uplift, threshold, count = max(options)
    picked_test = [r for r in test if r["feature_snapshot"]["score"] >= threshold]
    if len(picked_test) < 6:
        return {**info, "status": "holdout_subset_too_small",
                "chosen_threshold_train_only": threshold, "holdout_selected": len(picked_test)}
    test_uplift = _metric(picked_test)["mean_t2_pct"] - _metric(test)["mean_t2_pct"]
    info["rule_proposals"].append({
        "rule": "prior_day_capital_behavior_score_gte", "threshold": threshold,
        "train_selected": count, "holdout_selected": len(picked_test),
        "train_uplift_pct_points": round(train_uplift, 3),
        "holdout_uplift_pct_points": round(test_uplift, 3),
        "shadow_status": "worth_more_forward_testing"
            if train_uplift >= 1 and test_uplift >= 1 else "not_supported",
        "automatic_activation": False,
        "limitation": "Daily close-price observations, NOT verified fills, fees or live execution",
    })
    return info


def build_snapshot(recommendations, fetch_daily, *, now, low_position_observations=()):
    now = now.astimezone(CN)
    if now.year != 2026:
        return {"status": "calendar_unverified", "date": now.date().isoformat()}
    if is_session(now.date()) is not True:
        return {"status": "market_closed", "date": now.date().isoformat()}
    if now.time() < time(15, 15):
        return {"status": "before_verified_close", "date": now.date().isoformat()}
    as_of = now.date()
    rows = []
    cache = {}
    eligible = [r for r in recommendations if r.get("code") and r.get("id")]
    # Non-recommendation forward observations form a SEPARATE performance cohort.
    shape_signals = [r for r in low_position_observations if r.get("code") and r.get("id")
                     and r.get("is_recommendation") is False
                     and r.get("task_id") == "low_position"]
    for code in sorted({r["code"] for r in [*eligible, *shape_signals]}):
        try:
            cache[code] = fetch_daily(code)
        except Exception:
            cache[code] = ([], None, ["provider_exception"])
    for record in eligible:
        raw, source, errors = cache[record["code"]]
        # Do not include an uncompleted next-day candle even if the provider supplies it.
        raw = [r for r in raw if r.get("date", "") <= as_of.isoformat()]
        item = evaluate(record, raw, source, as_of=as_of)
        item["provider_errors"] = errors
        rows.append(item)
    low_rows = []
    for record in shape_signals:
        raw, source, errors = cache[record["code"]]
        completed = [r for r in raw if r.get("date", "") <= as_of.isoformat()]
        item = evaluate(record, completed, source, as_of=as_of)
        item["provider_errors"] = errors
        item["is_recommendation"] = False
        item["signal_source_report_id"] = record.get("signal_source_report_id")
        item["frozen_signal_features"] = record.get("frozen_features")
        low_rows.append(item)
    from low_position_learning import horizon_statistics
    scores = evaluate_shadow_rules(rows)  # formal recommendations only
    low_summary = horizon_statistics(low_rows)
    counts = dict(Counter(item["status"] for item in rows))
    return {
        "id": "forward-learning-" + as_of.isoformat(),
        "date": as_of.isoformat(), "recorded_at": now.isoformat(),
        "status": "completed_with_data_gaps" if any(
            r["status"] in {"provider_unavailable", "invalid_evidence"}
            for r in rows) else "evaluated",
        "version": VERSION, "sample_count": len(rows), "status_counts": counts,
        "provider_count": len(cache), "evaluations": rows,
        "validation": scores,
        "low_position_evaluations": low_rows,
        "low_position_summary": low_summary,
        "low_position_observations_are_recommendations": False,
        "training_stage": "shadow_only",
        "source_scope": "public_unadjusted_daily_candles",
        "trade_execution_verified": False,
        "model_weights_updated": False,
        "notes": [
            "T+1/T+2/T+5/T+10 are exchange sessions from the signal-date CLOSE, not assumed entry fills.",
            "Only pre-signal data can populate candidate features; no later quotes leak into scores.",
            "Missing session bars, corporate actions and unknown calendars are quarantined.",
            "Real strategy P&L and next-open execution require time-stamped order and fill evidence.",
            "Shadow threshold proposals never modify live stock-selection rules automatically.",
            "Low-position shape observations are separate from recommendation success metrics.",
        ],
    }


def append_snapshot(document, snapshot):
    if snapshot["status"] in ("calendar_unverified", "market_closed", "before_verified_close"):
        return document, False
    old = document.get("runs", [])
    if any(item["id"] == snapshot["id"] for item in old):
        return document, False  # Immutable daily snapshots; reruns are idempotent.
    return {"schema_version": 1, "updated_at": snapshot["recorded_at"],
            "runs": [*old, snapshot]}, True


def validate_learning_archive(document):
    if document.get("schema_version") != 1 or not isinstance(document.get("runs"), list):
        raise ValueError("invalid_learning_schema")
    ids = set()
    for row in document["runs"]:
        if row.get("id") in ids or row.get("id") != "forward-learning-" + row.get("date", ""):
            raise ValueError("invalid_or_duplicate_learning_run")
        ids.add(row["id"])
        if row.get("trade_execution_verified") is not False or row.get("model_weights_updated") is not False:
            raise ValueError("unsupported_live_training_claim")
    return document


def verify_append_only(before, after):
    original = before.get("runs", [])
    current = after.get("runs", [])
    if current[:len(original)] != original:
        raise ValueError("published_learning_snapshot_mutated_or_deleted")


def load_ledger():
    """Persisted snapshots, optionally mounted on a production volume."""
    import os
    import json
    from pathlib import Path
    override = os.environ.get("ROBIN_LEARNING_FILE")
    path = Path(override) if override else Path(__file__).resolve().parent / "data" / "learning.json"
    with path.open(encoding="utf-8") as file:
        document = json.load(file)
    return validate_learning_archive(document)
