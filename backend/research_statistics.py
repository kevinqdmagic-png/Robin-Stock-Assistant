"""Separate frequency and payoff research, using frozen price observations only."""
from collections import Counter, defaultdict
import math
from statistics import mean, median


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError, OverflowError):
        return None


def dual_statistics(events):
    """Never pool horizons, early/late windows, baselines or strategy versions.

    Rankings are descriptive even when sample-count floors are met; they are
    not matched experiments, trade win rates, net returns or portfolio drawdowns.
    """
    grouped = defaultdict(lambda: defaultdict(list))
    dimensions = ("family", "slot", "basis", "market_regime", "horizon", "strategy", "version")
    for event in events:
        key = tuple(event.get(k, "unknown") for k in dimensions)
        identity = (event.get("code"), event.get("anchor_date"))
        if all(identity):
            grouped[key][identity].append(event)
    groups, anchor_sets = [], {}
    for key, samples in sorted(grouped.items(), key=lambda x: str(x[0])):
        row = dict(zip(dimensions, key))
        row["id"] = "|".join(map(str, key))
        values, adverse, anchors = [], [], set()
        states = Counter()
        conflicts = duplicates = 0
        for (_code, anchor), attempts in samples.items():
            duplicates += len(attempts) - 1
            observed = [e for e in attempts if e.get("status") == "observed"]
            numbers = {finite(e.get("return_pct")) for e in observed}
            if observed and (None in numbers or len(numbers) != 1):
                conflicts += 1
                states["invalid_or_conflicting_observation"] += 1
                continue
            if not observed:
                states["|".join(sorted({str(e.get("status", "unknown")) for e in attempts}))] += 1
                continue
            values.append(numbers.pop())
            anchors.add(str(anchor))
            # Duplicate track records must not multiply path observations.
            paths = [finite(e.get("mae_pct")) for e in observed]
            paths = [p for p in paths if p is not None]
            if paths:
                adverse.append(min(paths))
            states["observed"] += 1
        wins, losses = [v for v in values if v > 0], [v for v in values if v < 0]
        average_win = mean(wins) if wins else None
        average_loss = mean(losses) if losses else None
        r = lambda value: round(value, 3) if value is not None else None
        row.update(
            sample_count=len(values), distinct_anchor_dates=len(anchors),
            expected_event_count=len(samples), status_counts=dict(states),
            duplicates_excluded=duplicates, conflicting_events_excluded=conflicts,
            positive_count=len(wins), negative_count=len(losses),
            positive_price_rate_pct=r(100 * len(wins) / len(values)) if values else None,
            mean_price_change_pct=r(mean(values)) if values else None,
            median_price_change_pct=r(median(values)) if values else None,
            average_positive_change_pct=r(average_win), average_negative_change_pct=r(average_loss),
            payoff_ratio=r(average_win / abs(average_loss)) if wins and losses else None,
            worst_close_change_pct=r(min(values)) if values else None,
            path_mae_sample_count=len(adverse), worst_path_mae_pct=r(min(adverse)) if adverse else None,
            minimum_sample_floor_met=len(values) >= 36 and len(anchors) >= 20,
            actual_trade_win_rate_pct=None, actual_net_return_pct=None,
            advantage_verified=False,
        )
        groups.append(row)
        anchor_sets[row["id"]] = anchors
    comparisons = defaultdict(list)
    for row in groups:
        if row["sample_count"]:
            comparisons[tuple(row[k] for k in dimensions[:5])].append(row)
    rankings = []
    for key, peers in sorted(comparisons.items(), key=lambda x: str(x[0])):
        common = set.intersection(*(anchor_sets[p["id"]] for p in peers))
        rankings.append({
            **dict(zip(dimensions[:5], key)),
            "by_positive_rate": [r["id"] for r in sorted(peers, key=lambda p: (
                -p["positive_price_rate_pct"], -p["mean_price_change_pct"], p["id"]))],
            "by_mean_return": [r["id"] for r in sorted(peers, key=lambda p: (
                -p["mean_price_change_pct"], -p["positive_price_rate_pct"], p["id"]))],
            "common_anchor_date_count": len(common),
            "matched_sample_comparison": False,
            "ranking_is_verified_advantage": False,
        })
    return {
        "mode": "exploratory_price_observations_only", "groups": groups, "rankings": rankings,
        "positive_rate_label": "上涨成功率观察", "mean_return_label": "平均收益观察",
        "actual_trade_win_rate_pct": None, "actual_net_return_pct": None,
        "automatic_weight_updates": False,
        "warning": "两榜分别排序；样本、日期与版本须同看。价格观察不是成交胜率或净收益；路径MAE不是组合最大回撤。",
    }


def snapshot_statistics(snapshot):
    events = []
    for field, family in (("evaluations", "recommendation_close_proxy"),
                          ("low_position_evaluations", "low_position_structure")):
        for record in snapshot.get(field) or []:
            if record.get("status") not in {"observed", "partially_observed"}:
                continue
            task = record.get("task_id")
            for outcome in record.get("horizons") or []:
                events.append({
                    "family": family,
                    "slot": task if task in {"early_pair", "late_pair"} else "close_research",
                    "basis": record.get("basis", "unknown"),
                    "market_regime": record.get("market_regime", "unknown"),
                    "strategy": record.get("strategy", "unknown"),
                    "version": record.get("selection_model_version", "legacy_not_frozen"),
                    "code": record.get("code"),
                    "anchor_date": record.get("anchor_date") or record.get("signal_date"),
                    "horizon": outcome.get("h"), "status": outcome.get("status"),
                    "return_pct": outcome.get("close_pct"), "mae_pct": outcome.get("mae_pct"),
                })
    return dual_statistics(events)


def intraday_statistics(entries):
    return dual_statistics([{
        "family": "intraday_quote_proxy", "slot": r.get("task_id", "unknown"),
        "basis": "frozen_quote_to_future_close", "market_regime": r.get("market_regime", "unknown"),
        "strategy": r.get("cohort", "unknown"), "version": r.get("model_version", "unknown"),
        "code": r.get("code"), "anchor_date": r.get("signal_date"),
        "horizon": r.get("horizon"), "status": "observed",
        "return_pct": r.get("price_change_from_quote_pct"),
        # The intraday tracker has no verified minute path. Do not infer MAE.
    } for r in entries])
