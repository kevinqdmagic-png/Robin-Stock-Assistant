#!/usr/bin/env python3
"""Collect reproducible 2026-10-15 evidence for missing combined modules.

The script deliberately separates raw price observations from executable
strategy outcomes. It reuses the already archived full-market scan, fetches
completed daily/minute history from Tencent, and obtains the same-day public
Dragon-Tiger list from Eastmoney and 10jqka. It does not identify accounts or
infer fills from daily highs/lows.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from io import BytesIO
import json
import math
from pathlib import Path
import statistics
import time
import urllib.parse
import urllib.request

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
T = "2026-10-15"
T_COMPACT = "20261015"
TARGET = ROOT / "docs/research/combined-pair-2026-10-15-evidence.json"
MARKET_EVIDENCE = ROOT / "docs/research/market-review-2026-10-15-evidence.json"
DAILY = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
FIVE_DAY = "https://web.ifzq.gtimg.cn/appstock/app/day/query"
LHB_EM = "https://datacenter-web.eastmoney.com/api/data/v1/get"
LHB_THS = "https://data.10jqka.com.cn/market/longhu/date/2026-10-15/"
UA = "Mozilla/5.0 (Robin Stock Assistant public research; no trading)"


def symbol(code: str) -> str:
    if code.startswith(("6", "9")):
        return "sh" + code
    if code.startswith(("4", "8")):
        return "bj" + code
    return "sz" + code


def request_bytes(url: str, params: dict | None = None, timeout: int = 40) -> bytes:
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Referer": "https://gu.qq.com/" if "gtimg" in url else "https://data.eastmoney.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def request_json(url: str, params: dict | None = None, attempts: int = 3) -> dict:
    error = None
    for attempt in range(attempts):
        try:
            return json.loads(request_bytes(url, params=params))
        except Exception as exc:  # provider is best effort; retain exact failures
            error = exc
            if attempt + 1 < attempts:
                time.sleep(0.7 * (attempt + 1))
    raise RuntimeError(f"provider_failed:{type(error).__name__}") from error


def daily_bars(code: str, adjusted: bool = True) -> list[dict]:
    sym = symbol(code)
    mode = "qfq" if adjusted else "none"
    payload = request_json(DAILY, {"param": f"{sym},day,,,180,{mode}"})
    node = (payload.get("data") or {}).get(sym) or {}
    rows = node.get("qfqday" if adjusted else "day") or []
    result = []
    for raw in rows:
        if len(raw) < 6:
            continue
        try:
            result.append(
                {
                    "date": str(raw[0]),
                    "open": float(raw[1]),
                    "close": float(raw[2]),
                    "high": float(raw[3]),
                    "low": float(raw[4]),
                    "volume": float(raw[5]),
                }
            )
        except (TypeError, ValueError):
            continue
    if not result or result[-1]["date"] != T:
        raise ValueError("missing_target_daily_bar")
    return result


def five_day_minutes(code: str) -> dict[str, list[dict]]:
    sym = symbol(code)
    payload = request_json(FIVE_DAY, {"code": sym})
    groups = (((payload.get("data") or {}).get(sym) or {}).get("data") or [])
    result: dict[str, list[dict]] = {}
    for group in groups:
        day = str(group.get("date") or "")
        points = []
        for raw in group.get("data") or []:
            fields = str(raw).split()
            if len(fields) < 4:
                continue
            try:
                points.append(
                    {
                        "clock": fields[0],
                        "price": float(fields[1]),
                        "cumulative_volume_provider_units": float(fields[2]),
                        "cumulative_amount_cny": float(fields[3]),
                    }
                )
            except ValueError:
                continue
        if day and points:
            result[day] = points
    return result


def load_report(report_id: str) -> dict:
    research = json.loads((ROOT / "backend/data/research.json").read_text())
    return next(row for row in research["items"] if row.get("id") == report_id)


def fetch_parallel(codes: list[str], func, workers: int = 10) -> tuple[dict, dict]:
    data, errors = {}, {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(func, code): code for code in codes}
        for future in as_completed(futures):
            code = futures[future]
            try:
                data[code] = future.result()
            except Exception as exc:
                errors[code] = f"{type(exc).__name__}:{exc}"
    return data, errors


def by_date(bars: list[dict], day: str) -> dict | None:
    return next((bar for bar in bars if bar["date"] == day), None)


def mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 3) if values else None


def median(values: list[float]) -> float | None:
    return round(statistics.median(values), 3) if values else None


def pct(value: float, base: float) -> float:
    return round((value / base - 1) * 100, 3)


def range_position(bars: list[dict], window: int) -> float | None:
    if len(bars) < window:
        return None
    rows = bars[-window:]
    low = min(row["low"] for row in rows)
    high = max(row["high"] for row in rows)
    return round((rows[-1]["close"] - low) / (high - low) * 100, 3) if high > low else None


def volume_mean(bars: list[dict], n: int) -> float | None:
    if len(bars) < n + 1:
        return None
    values = [row["volume"] for row in bars[-n - 1 : -1]]
    return statistics.fmean(values) if values and all(value >= 0 for value in values) else None


def classify(sample: dict) -> str:
    change = float(sample["daily_change_pct"])
    rvol = float(sample["rvol"]["20"])
    clv = sample.get("clv")
    pos = (sample.get("range_position_pct") or {}).get("120")
    tail = sample.get("tail_return_1400_to_1500_pct")
    if change >= 9.7 and rvol < 1.5:
        return "缩量封板/次日可成交风险"
    if change >= 9.7 and rvol >= 1.5:
        return "放量涨停/加速后等分歧"
    if pos is not None and pos <= 50 and rvol >= 1.5 and clv is not None and clv >= 0.7:
        return "低中位放量推进/待确认"
    if rvol >= 3 and change < 3:
        return "高量滞涨/分歧风险"
    if clv is not None and clv < 0.6:
        return "放量冲高回落/承接不足"
    if tail is not None and tail < -1:
        return "尾盘回落/兑现风险"
    return "放量推进/待后续承接"


def enrich_deep(deep: list[dict], histories: dict[str, list[dict]]) -> list[dict]:
    result = []
    for raw in deep:
        code = raw["code"]
        bars = histories.get(code)
        if not bars:
            continue
        current = by_date(bars, T)
        previous = bars[-2] if len(bars) > 1 else None
        if not current or not previous:
            continue
        ma = {
            str(n): round(statistics.fmean(row["close"] for row in bars[-n:]), 3)
            if len(bars) >= n
            else None
            for n in (5, 10, 20, 60)
        }
        rvol = {}
        for n in (5, 10, 20):
            denominator = volume_mean(bars, n)
            rvol[str(n)] = round(current["volume"] / denominator, 3) if denominator else None
        sample = {
            "code": code,
            "name": raw["name"],
            "date": T,
            "open": float(raw["open"]),
            "close": float(raw["trade"]),
            "high": float(raw["high"]),
            "low": float(raw["low"]),
            "previous_close": float(raw["settlement"]),
            "daily_change_pct": round(float(raw["changepercent"]), 3),
            "amount_cny": float(raw["amount"]),
            "turnover_pct": round(float(raw["turnoverratio"]), 3),
            "rvol": rvol,
            "ma": ma,
            "range_position_pct": {str(n): range_position(bars, n) for n in (20, 60, 120)},
            "prior20_high": round(max(row["high"] for row in bars[-21:-1]), 3) if len(bars) >= 21 else None,
            "clv": round(float(raw["clv"]), 3) if raw.get("clv") is not None else None,
            "amplitude_pct": round((float(raw["high"]) - float(raw["low"])) / float(raw["settlement"]) * 100, 3),
            "distance_ma20_pct": round(float(raw["dist_ma20"]), 3),
            "tail_return_1400_to_1500_pct": round(float(raw.get("tail_1400_close_pct") or 0), 3),
            "tail_volume_share_pct": round(float(raw.get("tail_volume_share") or 0) * 100, 3),
            "minute_price_points": raw.get("price_points") or {},
            "daily_source": f"{DAILY}?param={symbol(code)},day,,,180,qfq",
            "minute_source": "archived_market_review_same_day_evidence",
            "evidence_status": "verified_same_day_daily_and_archived_minute_price_points",
            "missing": ["auction_0925", "verified_minute_OHLC", "order_book", "tick_sequence", "verified_fill"],
        }
        sample["structure"] = classify(sample)
        result.append(sample)
    return result


def minute_checkpoints(points: list[dict], base: float) -> dict:
    wanted = ("0930", "0945", "1030", "1130", "1400", "1440", "1500")
    lookup = {point["clock"]: point for point in points}
    result = {}
    for clock in wanted:
        if clock in lookup:
            point = dict(lookup[clock])
            point["return_vs_prior_close_pct"] = pct(point["price"], base)
            result[clock] = point
    return result


def validate_previous_volume(codes: list[str], histories: dict, minutes: dict) -> tuple[list, dict]:
    rows = []
    for code in codes:
        bars = histories.get(code) or []
        base = by_date(bars, "2026-10-12")
        nxt = by_date(bars, "2026-10-13")
        if not base or not nxt:
            continue
        row = {
            "code": code,
            "reference_date": "2026-10-12",
            "validation_date": "2026-10-13",
            "reference_close_qfq": base["close"],
            "open_return_pct": pct(nxt["open"], base["close"]),
            "high_observation_pct": pct(nxt["high"], base["close"]),
            "low_observation_pct": pct(nxt["low"], base["close"]),
            "close_return_pct": pct(nxt["close"], base["close"]),
            "minute_checkpoints": minute_checkpoints((minutes.get(code) or {}).get("20261013", []), base["close"]),
            "executed_trade": False,
            "executable_net_return_pct": None,
            "trigger_status": "not_reconstructable_without_frozen_uniform_trigger",
            "evidence_status": "verified_daily_and_historical_minute_price_points",
        }
        rows.append(row)
    stats = {
        "expected_count": len(codes),
        "verified_count": len(rows),
        "positive_open_count": sum(row["open_return_pct"] > 0 for row in rows),
        "positive_close_count": sum(row["close_return_pct"] > 0 for row in rows),
        "mean_open_return_pct": mean([row["open_return_pct"] for row in rows]),
        "median_open_return_pct": median([row["open_return_pct"] for row in rows]),
        "mean_close_return_pct": mean([row["close_return_pct"] for row in rows]),
        "median_close_return_pct": median([row["close_return_pct"] for row in rows]),
        "mean_high_observation_pct": mean([row["high_observation_pct"] for row in rows]),
        "mean_low_observation_pct": mean([row["low_observation_pct"] for row in rows]),
        "executable_sample_count": 0,
        "strategy_win_rate": None,
        "mean_net_return_pct": None,
    }
    return rows, stats


def low_validations(samples: list[dict], raw_histories: dict[str, list[dict]]) -> list[dict]:
    results = []
    target_date = date.fromisoformat(T)
    for sample in samples:
        code = sample["code"]
        bars = raw_histories.get(code) or []
        reference_date = sample["date"]
        usable = [bar for bar in bars if reference_date <= bar["date"] <= T]
        current = by_date(bars, T)
        reference = by_date(bars, reference_date)
        if not current or not usable:
            results.append({"code": code, "name": sample["name"], "status": "unavailable"})
            continue
        ref = float(sample["day0_close"])
        path_high = max(bar["high"] for bar in usable)
        path_low = min(bar["low"] for bar in usable)
        observation = {
            "id": f"{sample['id']}-{code}-close-{T_COMPACT}",
            "code": code,
            "name": sample["name"],
            "date": T,
            "reference_date": reference_date,
            "reference_close": ref,
            "origin_cohort_id": sample["id"],
            "report_ids": ["low-position-20261015-close-v1"],
            "observation_type": "price_observation",
            "evidence_status": "single_provider_closed_daily_with_path",
            "full_validation_completed": True,
            "eligible_for_model_statistics": bool(sample.get("eligible_for_model_statistics")),
            "reference_verified_against_current_provider": bool(reference and abs(reference["close"] / ref - 1) <= 0.01),
            "trigger_status": "not_verified",
            "entry_fill_status": "not_verified",
            "executed_trade": False,
            "executable_net_return_pct": None,
            "executable_mfe_pct": None,
            "executable_mae_pct": None,
            "source_urls": [f"{DAILY}?param={symbol(code)},day,,,180,none"],
            "missing": ["independent_daily_crosscheck", "historical_minute_OHLC", "auction", "fill", "legal_exit"],
            "price_observation": {
                "open": current["open"],
                "high": current["high"],
                "low": current["low"],
                "close": current["close"],
                "previous_close": next((bars[i - 1]["close"] for i, bar in enumerate(bars) if bar["date"] == T and i > 0), None),
            },
            "open_return_pct": pct(current["open"], ref),
            "daily_high_price_excursion_pct": pct(current["high"], ref),
            "daily_low_price_excursion_pct": pct(current["low"], ref),
            "close_return_pct": pct(current["close"], ref),
            "clv": round((current["close"] - current["low"]) / (current["high"] - current["low"]), 3)
            if current["high"] > current["low"]
            else None,
            "elapsed_natural_days": (target_date - date.fromisoformat(reference_date)).days,
            "elapsed_trading_sessions": sum(reference_date < bar["date"] <= T for bar in bars),
            "invalid_close_below_original": sample.get("invalid_close_below"),
            "path_mfe_pct": pct(path_high, ref),
            "path_mae_pct": pct(path_low, ref),
            "thirty_natural_days_matured": (target_date - date.fromisoformat(reference_date)).days >= 30,
            "observed_close_below_original_invalid": bool(sample.get("invalid_close_below") and current["close"] < sample["invalid_close_below"]),
            "invalid_order_verified": False,
            "price_observation_note": "日线价格观察；不是触发后MFE/MAE或可执行策略收益。",
        }
        results.append(observation)
    return results


def choose_new_low(deep: list[dict], existing_codes: set[str]) -> list[dict]:
    rows = []
    for sample in deep:
        pos = sample["range_position_pct"].get("120")
        if (
            sample["code"] not in existing_codes
            and pos is not None
            and pos <= 55
            and 2 <= sample["rvol"]["20"] <= 6
            and sample["clv"] is not None
            and sample["clv"] >= 0.72
            and 1.5 <= sample["daily_change_pct"] <= 8
            and 0 <= sample["distance_ma20_pct"] <= 15
        ):
            rows.append(sample)
    rows.sort(key=lambda row: (row["range_position_pct"]["120"], -row["clv"], -row["rvol"]["20"]))
    return rows[:6]


def lhb_data() -> tuple[list[dict], list[pd.DataFrame]]:
    params = {
        "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
        "columns": "ALL",
        "filter": "(TRADE_DATE='2026-10-15')",
        "pageNumber": "1",
        "pageSize": "500",
        "source": "WEB",
        "client": "WEB",
    }
    payload = request_json(LHB_EM, params=params)
    rows = ((payload.get("result") or {}).get("data") or [])
    html = request_bytes(LHB_THS, timeout=60)
    tables = pd.read_html(BytesIO(html))
    return rows, tables


def normalize_code(value) -> str:
    try:
        return str(int(float(value))).zfill(6)
    except (TypeError, ValueError):
        return str(value).strip().zfill(6)


def seat_rows(frame: pd.DataFrame) -> list[dict]:
    result = []
    for _, row in frame.iterrows():
        values = row.tolist()
        if len(values) < 4:
            continue
        result.append(
            {
                "seat_public_label": str(values[0]),
                "buy_10k_cny": None if pd.isna(values[1]) else float(values[1]),
                "sell_10k_cny": None if pd.isna(values[2]) else float(values[2]),
                "net_10k_cny": None if pd.isna(values[3]) else float(values[3]),
            }
        )
    return result


def summarize_lhb(rows: list[dict], tables: list[pd.DataFrame], chosen_codes: list[str]) -> dict:
    unique = {}
    reasons = {}
    for row in rows:
        code = row.get("SECURITY_CODE")
        if not code or code.startswith(("1", "4", "8", "9")):
            # Counts remain in raw total; convertible bonds/BSE are not A-share integrated candidates.
            pass
        unique.setdefault(code, row)
        reasons.setdefault(code, set()).add(row.get("EXPLANATION") or "")
    summary_table = tables[5]
    table_index = {}
    for idx, row in summary_table.iterrows():
        code = normalize_code(row.iloc[1])
        table_index[code] = idx
    chosen = []
    for code in chosen_codes:
        row = unique.get(code)
        if not row:
            continue
        index = table_index.get(code)
        buys = seat_rows(tables[6 + 2 * index]) if index is not None and 6 + 2 * index < len(tables) else []
        sells = seat_rows(tables[7 + 2 * index]) if index is not None and 7 + 2 * index < len(tables) else []
        chosen.append(
            {
                "code": code,
                "name": row.get("SECURITY_NAME_ABBR"),
                "change_pct": row.get("CHANGE_RATE"),
                "turnover_pct": row.get("TURNOVERRATE"),
                "close": row.get("CLOSE_PRICE"),
                "buy_cny": row.get("BILLBOARD_BUY_AMT"),
                "sell_cny": row.get("BILLBOARD_SELL_AMT"),
                "net_cny": row.get("BILLBOARD_NET_AMT"),
                "billboard_deal_cny": row.get("BILLBOARD_DEAL_AMT"),
                "reasons": sorted(reason for reason in reasons.get(code, set()) if reason),
                "buy_seats": buys,
                "sell_seats": sells,
                "identity_warning": "公开席位标签不等于最终账户、资金身份、持仓周期或锁仓事实。",
            }
        )
    return {
        "raw_reason_rows": len(rows),
        "unique_security_count_including_bse_and_convertibles": len(unique),
        "ths_summary_unique_rows": len(summary_table),
        "selected_observation_count": len(chosen),
        "selected_observations": chosen,
        "all_unique": [
            {
                "code": code,
                "name": row.get("SECURITY_NAME_ABBR"),
                "change_pct": row.get("CHANGE_RATE"),
                "turnover_pct": row.get("TURNOVERRATE"),
                "net_cny": row.get("BILLBOARD_NET_AMT"),
                "reasons": sorted(reason for reason in reasons.get(code, set()) if reason),
            }
            for code, row in unique.items()
        ],
    }


def previous_dragon_validation(histories: dict, minutes: dict) -> list[dict]:
    codes = ["000420", "300364", "300369", "300413", "002487"]
    rows = []
    for code in codes:
        bars = histories.get(code) or []
        base = by_date(bars, "2026-10-12")
        nxt = by_date(bars, "2026-10-13")
        if not base or not nxt:
            continue
        rows.append(
            {
                "code": code,
                "reference_date": "2026-10-12",
                "validation_date": "2026-10-13",
                "open_return_pct": pct(nxt["open"], base["close"]),
                "high_observation_pct": pct(nxt["high"], base["close"]),
                "low_observation_pct": pct(nxt["low"], base["close"]),
                "close_return_pct": pct(nxt["close"], base["close"]),
                "minute_checkpoints": minute_checkpoints((minutes.get(code) or {}).get("20261013", []), base["close"]),
                "executed_trade": False,
                "executable_net_return_pct": None,
                "note": "上一龙虎榜观察样本的次日价格观察；未按统一触发成交。",
            }
        )
    return rows


def prior_combined_tracking(histories: dict, minutes: dict) -> dict:
    bars = histories.get("300450") or []
    base = by_date(bars, "2026-10-12")
    result = {
        "recommendation_id": "combined-pair-20261012-300450-close-v1",
        "code": "300450",
        "triggered_on_2026_10_13": False,
        "trigger_reason": "10月13日开盘低于冻结37.30元下界；不得事后按日内高低反推入场。",
        "executed_trade": False,
        "executable_return_pct": None,
        "price_observations": [],
    }
    if base:
        for day in ("2026-10-13", "2026-10-14", "2026-10-15"):
            bar = by_date(bars, day)
            if bar:
                result["price_observations"].append(
                    {
                        "date": day,
                        "open_return_pct": pct(bar["open"], base["close"]),
                        "high_observation_pct": pct(bar["high"], base["close"]),
                        "low_observation_pct": pct(bar["low"], base["close"]),
                        "close_return_pct": pct(bar["close"], base["close"]),
                        "minute_checkpoints": minute_checkpoints(
                            (minutes.get("300450") or {}).get(day.replace("-", ""), []), base["close"]
                        ),
                    }
                )
    return result


def main() -> None:
    market = json.loads(MARKET_EVIDENCE.read_text())
    previous_volume = load_report("volume-price-20261012-close-v1")
    previous_volume_codes = previous_volume["frozen_sample_codes"]
    low_document = json.loads((ROOT / "backend/data/low_position_samples.json").read_text())
    low_codes = [row["code"] for row in low_document["items"]]

    lhb_rows, lhb_tables = lhb_data()
    chosen_lhb = ["600869", "002945", "000892", "000823", "000530"]

    qfq_codes = sorted(
        set([row["code"] for row in market["deep_pool"]] + previous_volume_codes + low_codes + chosen_lhb
            + ["000420", "300364", "300369", "300413", "002487", "300450"])
    )
    raw_codes = sorted(set(low_codes + ["000420", "300364", "300369", "300413", "002487", "300450"]))
    minute_codes = sorted(set(previous_volume_codes + ["000420", "300364", "300369", "300413", "002487", "300450"]))

    qfq, qfq_errors = fetch_parallel(qfq_codes, lambda code: daily_bars(code, adjusted=True), workers=10)
    raw, raw_errors = fetch_parallel(raw_codes, lambda code: daily_bars(code, adjusted=False), workers=8)
    minutes, minute_errors = fetch_parallel(minute_codes, five_day_minutes, workers=8)

    deep = enrich_deep(market["deep_pool"], qfq)
    previous_rows, previous_stats = validate_previous_volume(previous_volume_codes, qfq, minutes)
    low_rows = low_validations(low_document["items"], raw)
    new_low = choose_new_low(deep, set(low_codes))
    lhb = summarize_lhb(lhb_rows, lhb_tables, chosen_lhb)

    names = {row["code"]: row["name"] for row in market["deep_pool"]}
    for row in lhb["selected_observations"]:
        names[row["code"]] = row["name"]
        bars = qfq.get(row["code"])
        if bars:
            current = by_date(bars, T)
            row["range_position_pct"] = {str(n): range_position(bars, n) for n in (20, 60, 120)}
            row["rvol20"] = round(current["volume"] / volume_mean(bars, 20), 3) if current and volume_mean(bars, 20) else None
            row["clv"] = round((current["close"] - current["low"]) / (current["high"] - current["low"]), 3) if current and current["high"] > current["low"] else None

    evidence = {
        "market_date": T,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision_policy": {
            "required_full_modules": ["market_review", "volume_price", "low_position", "dragon_tiger"],
            "quant_research_required": False,
            "t_plus_one_entry_date": "2026-10-16",
            "earliest_legal_exit_if_bought": "2026-10-19",
        },
        "market_review_reused": {
            "report_id": "market-review-20261015-close-v1",
            "full_scan": market["coverage"]["full_scan"],
            "broad_pool": market["coverage"]["broad_pool"],
            "deep_pool": market["coverage"]["deep_pool"],
            "market": market["market"],
        },
        "volume_price": {
            "rule_version": "volume_price_close_v3",
            "deep_samples": deep,
            "deep_expected": len(market["deep_pool"]),
            "deep_verified": len(deep),
            "previous_cohort_id": "volume-price-20261012-close-v1",
            "previous_validations": previous_rows,
            "previous_statistics": previous_stats,
            "executable_sample_count": 0,
            "cost_assumption_bps": 20,
            "statistics_limit": "价格观察与可执行净收益分离；无统一冻结触发和成交证据，策略统计N=0。",
        },
        "low_position": {
            "rule_version": "low_position_30d_v1",
            "existing_expected": len(low_document["items"]),
            "existing_validations": low_rows,
            "new_candidates": new_low,
            "matured_30_natural_days": sum(row.get("thirty_natural_days_matured", False) for row in low_rows),
            "statistics_limit": "尚无30自然日到期样本；旧快照中不满足统计条件的样本继续保留。",
        },
        "dragon_tiger": {
            "rule_version": "dragon_tiger_close_v2",
            **lhb,
            "previous_validations": previous_dragon_validation(qfq, minutes),
            "statistics_limit": "席位结构仅为公开通道数据；没有统一触发成交，策略胜率和净收益N/A。",
        },
        "prior_combined": prior_combined_tracking(qfq, minutes),
        "provider_failures": {
            "qfq_daily": qfq_errors,
            "raw_daily": raw_errors,
            "five_day_minutes": minute_errors,
        },
        "sources": [
            "docs/research/market-review-2026-10-15-evidence.json",
            DAILY,
            FIVE_DAY,
            LHB_EM,
            LHB_THS,
        ],
        "limitations": [
            "Tencent日线/五日分钟为公开单一提供者，未取得逐笔、盘口或9:25竞价。",
            "分钟为价格点和累计量额，不是核验OHLC；不推断分钟内先后或真实成交。",
            "龙虎榜席位标签不能识别最终账户、资金身份、锁仓或后续方向。",
            "公告检索结果只说明本轮检索范围，不能证明不存在未来风险。",
        ],
    }
    TARGET.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "target": str(TARGET),
        "deep": len(deep),
        "previous_volume": len(previous_rows),
        "low_validations": len(low_rows),
        "new_low": [row["code"] for row in new_low],
        "lhb_reason_rows": len(lhb_rows),
        "lhb_unique": lhb["unique_security_count_including_bse_and_convertibles"],
        "provider_failures": evidence["provider_failures"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
