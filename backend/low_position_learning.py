"""Strict, append-only low-position observation -> future daily-bar proxy analysis.

The signal is frozen on its actual publication date. It is not a recommendation,
verified trade, brokerage fill, market-wide scan or self-updating trading model.
Multiple after-close retries must not inflate the number of independent signals.
"""
from collections import Counter
from datetime import date, datetime, timedelta, time
from statistics import mean, median
from zoneinfo import ZoneInfo
import math
import re

CN = ZoneInfo("Asia/Shanghai")
MODEL = "low_position_shape_proxy_v1"
METRIC_HORIZONS = (1, 2, 5, 10, 30)
MAX_AGE_DAYS = 70


def extract_observations(research, as_of):
    """Take the earliest real, date-verified matching report per (day, code).

    Only structured real-time frozen observations qualify. Retrospective reports,
    inferred historical winners, older method versions and failed attempts do not.
    """
    if isinstance(as_of, datetime):
        as_of = as_of.astimezone(CN).date()
    if not isinstance(as_of, date):
        raise ValueError("as_of_must_be_date")
    rows = []
    for report in research:
        if (not isinstance(report, dict) or report.get("task_id") != "low_position"
                or report.get("shape_method_version") != MODEL
                or report.get("provenance") != "contemporaneous_observation_not_recommendation"
                or report.get("validation_status") != "partial_not_tradeable"
                or report.get("analysis_completed") is not False):
            continue
        try:
            day = date.fromisoformat(report["date"])
            stamp = datetime.fromisoformat(report["published_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                continue
            stamp = stamp.astimezone(CN)
            if (day > as_of or day < as_of - timedelta(days=MAX_AGE_DAYS)
                    or stamp.date() != day or stamp.time() < time(15, 10)):
                continue
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
        for obs in report.get("signal_observations", [])[:10]:
            if not isinstance(obs, dict):
                continue
            code = str(obs.get("code") or "")
            if (not re.fullmatch(r"\d{6}", code)
                    or obs.get("date") != day.isoformat()
                    or obs.get("source") != "tencent_qfq_daily"
                    or obs.get("eligible_for_trading") is not False):
                continue
            features = {}
            for key in ("close_qfq", "day_pct_proxy", "relative_volume20",
                        "close_location", "distance_ma20_pct", "distance_60d_low_pct"):
                value = obs.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    features = {}
                    break
                features[key] = value
            if (len(features) != 6 or features["close_qfq"] <= 0
                    or features["relative_volume20"] <= 0 or
                    not 0 <= features["close_location"] <= 1):
                continue
            rows.append({
                "id": "low-position-proxy-" + day.strftime("%Y%m%d") + "-" + code,
                "date": day.isoformat(), "published_at": stamp.isoformat(timespec="seconds"),
                "code": code, "provenance": "contemporaneous",
                "strategy": MODEL, "task_id": "low_position", "is_recommendation": False,
                "signal_source_report_id": report["id"],
                "frozen_features": features, "trade_execution_verified": False,
            })
    rows.sort(key=lambda row: (row["date"], row["published_at"], row["id"], row["signal_source_report_id"]))
    deduped = {}
    for row in rows:
        deduped.setdefault((row["date"], row["code"]), row)
    return list(deduped.values())


def horizon_statistics(evaluations):
    """Descriptive CLOSE-to-CLOSE proxy statistics, never claimed trading alpha."""
    counts = dict(Counter(row.get("status") for row in evaluations))
    result = {
        "status": "descriptive_forward_validation_only",
        "method": MODEL, "sample_count": len(evaluations),
        "unique_signal_dates": len({row.get("signal_date") for row in evaluations}),
        "status_counts": counts, "horizons": {},
        "selection_rules_changed": False, "sample_out_of_market_census": False,
        "holds_out_future_dates_for_rule_selection": False,
        "executable_pnl": False,
    }
    for horizon in METRIC_HORIZONS:
        valid = []
        for row in evaluations:
            for r in row.get("horizons", []):
                if r.get("h") == horizon and r.get("status") == "observed":
                    if all(isinstance(r.get(k), (int, float)) and
                           math.isfinite(r[k]) for k in ("close_pct", "mae_pct", "mfe_pct")):
                        valid.append(r)
                    break
        if valid:
            rets = [r["close_pct"] for r in valid]
            adverse = [r["mae_pct"] for r in valid]
            result["horizons"][str(horizon)] = {
                "matured_count": len(valid),
                "mean_close_pct": round(mean(rets), 3),
                "median_close_pct": round(median(rets), 3),
                "positive_close_rate_pct": round(100 * sum(r > 0 for r in rets) / len(rets), 2),
                "median_intraperiod_mae_pct": round(median(adverse), 3),
                "return_basis": "signal_day_close_unadjusted_proxy_not_t1_fill",
            }
        else:
            result["horizons"][str(horizon)] = {
                "matured_count": 0, "mean_close_pct": None,
                "median_close_pct": None, "positive_close_rate_pct": None,
                "median_intraperiod_mae_pct": None,
                "return_basis": "signal_day_close_unadjusted_proxy_not_t1_fill",
            }
    return result
