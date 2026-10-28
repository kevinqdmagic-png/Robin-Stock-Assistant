#!/usr/bin/env python3
"""Retrospectively recover the missing 2026-10-21 volume-price archive.

The output is intentionally ineligible for the original integrated decision:
future outcomes were already known when this recovery was executed.
"""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import statistics
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
T = "2026-10-21"
T1 = "2026-10-22"
REPORT_ID = "volume-price-20261021-historical-recovery-v1"
COHORT_ID = "volume-price-20261021-historical-recovery-v1-cohort"
VALIDATION_ID = "volume-price-20261020-validation-20261021-recovery-v1"
T1_VALIDATION_ID = "volume-price-20261021-validation-20261022-recovery-v1"
EVIDENCE_FILE = "docs/research/volume-price-2026-10-21-recovery-evidence.json"


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def save(path, value):
    (ROOT / path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sym(code):
    if code.startswith(("5", "6")):
        return "sh" + code
    if code.startswith(("8", "9")):
        return "bj" + code
    return "sz" + code


def fetch(code):
    symbol = sym(code)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param={symbol},day,,,180"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as response:
        payload = json.loads(response.read().decode("utf-8"))
    node = payload.get("data", {}).get(symbol, {})
    raw = node.get("day") or node.get("qfqday") or []
    bars = [{"date": r[0], "open": float(r[1]), "close": float(r[2]), "high": float(r[3]),
             "low": float(r[4]), "volume": float(r[5])} for r in raw if r[0] <= T1]
    if not any(x["date"] == T for x in bars):
        raise RuntimeError(f"missing {T}")
    return code, {"source": url, "bars": bars}


def fetch_many(codes):
    results, errors = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        futures = {pool.submit(fetch, code): code for code in codes}
        for future in concurrent.futures.as_completed(futures):
            code = futures[future]
            try:
                _, value = future.result()
                results[code] = value
            except Exception as exc:
                errors[code] = f"{type(exc).__name__}: {exc}"
    return results, errors


def pct(value, base):
    return round((value / base - 1) * 100, 3) if base else None


def snapshot(code, name, sector, history):
    bars = history["bars"]
    idx = next(i for i, x in enumerate(bars) if x["date"] == T)
    cur, prev, prior = bars[idx], bars[idx - 1], bars[:idx]
    def rvol(n):
        seq = prior[-n:]
        return cur["volume"] / statistics.mean(x["volume"] for x in seq) if len(seq) == n else None
    def ma(n):
        seq = bars[max(0, idx - n + 1):idx + 1]
        return statistics.mean(x["close"] for x in seq) if len(seq) == n else None
    def pos(n):
        seq = bars[max(0, idx - n + 1):idx + 1]
        if len(seq) != n:
            return None
        lo, hi = min(x["low"] for x in seq), max(x["high"] for x in seq)
        return (cur["close"] - lo) / (hi - lo) * 100 if hi > lo else None
    def val(f):
        return round(f, 6) if f is not None else None
    clv = ((cur["close"] - cur["low"]) / (cur["high"] - cur["low"])) if cur["high"] > cur["low"] else None
    ma20 = ma(20)
    upper_wick = (cur["high"] - max(cur["open"], cur["close"])) / prev["close"] * 100
    lower_wick = (min(cur["open"], cur["close"]) - cur["low"]) / prev["close"] * 100
    out = {"code": code, "name": name, "sector": sector, **cur, "previous_close": prev["close"],
           "change_pct": pct(cur["close"], prev["close"]), "amplitude_pct": pct(cur["high"], cur["low"]),
           "rvol5": val(rvol(5)), "rvol10": val(rvol(10)), "rvol20": val(rvol(20)),
           "ma20": val(ma20), "distance_ma20_pct": pct(cur["close"], ma20) if ma20 else None,
           "position20_pct": val(pos(20)), "position60_pct": val(pos(60)), "position120_pct": val(pos(120)),
           "clv": val(clv), "upper_wick_pct": round(upper_wick, 3), "lower_wick_pct": round(lower_wick, 3),
           "turnover_pct": None, "tail_price_change_pct": None, "tail_volume_share": None,
           "source": history["source"],
           "missing": ["historical turnover", "full minute OHLC/volume sequence", "auction", "order book", "verified fill"]}
    nxt = next((x for x in bars if x["date"] == T1), None)
    if nxt:
        out["T_plus_1_price_observation"] = {**nxt, "open_pct": pct(nxt["open"], cur["close"]),
                                             "mfe_pct": pct(nxt["high"], cur["close"]),
                                             "mae_pct": pct(nxt["low"], cur["close"]),
                                             "close_pct": pct(nxt["close"], cur["close"]),
                                             "executed_trade": False}
    return out


def classify(x):
    pos = x.get("position120_pct")
    r20 = x.get("rvol20")
    clv = x.get("clv")
    change = x.get("change_pct")
    upper = x.get("upper_wick_pct")
    if None in (pos, r20, clv, change):
        return "数据不足"
    if pos <= 55 and r20 >= 1.5 and change > 1.5 and clv >= 0.7:
        return "低位首次放量/推进待确认"
    if r20 >= 1.8 and change > 2 and clv >= 0.75:
        return "放量突破/再转强待确认"
    if r20 >= 1.8 and (change <= 0 or clv < 0.35 or upper >= 3):
        return "放量滞涨或长上影风险"
    if r20 < 0.8 and change > 0:
        return "缩量上涨"
    if r20 >= 1.5 and change < -2:
        return "放量下跌"
    return "常规对照"


def main():
    research = load("backend/data/research.json")
    runs = load("backend/data/task_runs.json")
    ledger = load("backend/data/volume_price_samples.json")
    market = load("docs/research/market-review-2026-10-21-evidence.json")
    if any(x["id"] == REPORT_ID for x in research["items"]):
        print("already recovered")
        return

    started = dt.datetime.now(dt.timezone.utc)
    stamp_cn = started.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    pool = {}
    for row in market["candidate_pool"]:
        pool.setdefault(row["code"], row)
    prior_cohort = next(x for x in ledger["items"] if x.get("id") == "volume-price-20261020-close-v1-cohort")
    prior_samples = prior_cohort["samples"]
    codes = sorted(set(pool) | {x["code"] for x in prior_samples})
    histories, errors = fetch_many(codes)

    structures = [snapshot(code, row["name"], row.get("sector", "未分类"), histories[code])
                  for code, row in pool.items() if code in histories]
    for row in structures:
        row["structure"] = classify(row)
        row["provenance"] = "retrospective_gap_recovery"
        row["eligible_for_model_statistics"] = False

    # Preserve several structure families rather than selecting only winners.
    groups = {}
    for row in structures:
        groups.setdefault(row["structure"], []).append(row)
    for rows in groups.values():
        rows.sort(key=lambda x: ((x.get("rvol20") or 0), abs(x.get("change_pct") or 0)), reverse=True)
    order = ["低位首次放量/推进待确认", "放量突破/再转强待确认", "放量滞涨或长上影风险",
             "放量下跌", "缩量上涨", "常规对照", "数据不足"]
    deep = []
    while len(deep) < 28:
        moved = False
        for name in order:
            rows = groups.get(name, [])
            if rows and len(deep) < 28:
                deep.append(rows.pop(0)); moved = True
        if not moved:
            break

    prior_validations = []
    for sample in prior_samples:
        hist = histories.get(sample["code"])
        if not hist:
            prior_validations.append({"code": sample["code"], "name": sample["name"], "status": "unavailable"})
            continue
        bar = next((x for x in hist["bars"] if x["date"] == T), None)
        ref = float(sample.get("close") or sample.get("reference_price") or sample.get("signal_close") or sample.get("day0_close"))
        if not bar:
            prior_validations.append({"code": sample["code"], "name": sample["name"], "status": "unavailable"})
            continue
        prior_validations.append({"code": sample["code"], "name": sample["name"], "status": "price_observed",
                                  "reference_close": ref, "date": T, "open": bar["open"], "high": bar["high"],
                                  "low": bar["low"], "close": bar["close"], "open_pct": pct(bar["open"], ref),
                                  "mfe_pct": pct(bar["high"], ref), "mae_pct": pct(bar["low"], ref),
                                  "close_pct": pct(bar["close"], ref), "executed_trade": False,
                                  "trigger_status": "not_reconstructed", "executable_net_return_pct": None,
                                  "source": hist["source"]})

    t1_validations = [{"code": x["code"], "name": x["name"], "structure": x["structure"],
                       **x["T_plus_1_price_observation"]}
                      for x in deep if x.get("T_plus_1_price_observation")]
    observed_prior = [x for x in prior_validations if x["status"] == "price_observed"]
    prior_stats = {
        "count": len(observed_prior), "positive_close_count": sum(x["close_pct"] > 0 for x in observed_prior),
        "mean_close_pct": round(statistics.mean(x["close_pct"] for x in observed_prior), 3) if observed_prior else None,
        "median_close_pct": round(statistics.median(x["close_pct"] for x in observed_prior), 3) if observed_prior else None,
        "mean_mfe_pct": round(statistics.mean(x["mfe_pct"] for x in observed_prior), 3) if observed_prior else None,
        "mean_mae_pct": round(statistics.mean(x["mae_pct"] for x in observed_prior), 3) if observed_prior else None,
        "executed_trade_count": 0,
    }
    t1_stats = {"count": len(t1_validations), "positive_close_count": sum(x["close_pct"] > 0 for x in t1_validations)}
    if t1_validations:
        t1_stats.update({"mean_close_pct": round(statistics.mean(x["close_pct"] for x in t1_validations), 3),
                         "median_close_pct": round(statistics.median(x["close_pct"] for x in t1_validations), 3),
                         "mean_mfe_pct": round(statistics.mean(x["mfe_pct"] for x in t1_validations), 3),
                         "mean_mae_pct": round(statistics.mean(x["mae_pct"] for x in t1_validations), 3),
                         "executed_trade_count": 0})

    # Pick representative examples, including both support and risk structures.
    displays = []
    for label in ["低位首次放量/推进待确认", "放量突破/再转强待确认", "放量滞涨或长上影风险", "放量下跌", "缩量上涨"]:
        match = next((x for x in deep if x["structure"] == label), None)
        if match:
            displays.append(match)
    displays = displays[:5]

    completed = dt.datetime.now(dt.timezone.utc)
    completed_cn = completed.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    evidence = {"id": "volume-price-20261021-historical-recovery-evidence-v1", "date": T,
                "started_at": started.isoformat(timespec="seconds"), "completed_at": completed.isoformat(timespec="seconds"),
                "recorded_at": completed_cn, "provenance": "retrospective_gap_recovery",
                "market": market["market_stats"],
                "coverage": {"frozen_market_entries": len(pool), "daily_histories_recovered": len(histories),
                             "history_errors": errors, "technical_rows": len(structures), "deep_pool": len(deep),
                             "previous_deep_pool_expected": len(prior_samples), "previous_deep_pool_validated": len(observed_prior)},
                "deep_pool": deep, "display_samples": displays,
                "previous_pool_validations": prior_validations, "previous_pool_statistics": prior_stats,
                "T_plus_1_deep_pool_validations": t1_validations, "T_plus_1_statistics": t1_stats,
                "sources": market["sources"] + [{"name": "腾讯历史日线", "url": "https://web.ifzq.gtimg.cn/appstock/app/kline/kline", "scope": "原价OHLCV历史补证"}],
                "limitations": ["not a contemporaneous full-A scan", "turnover and full minute sequence not recovered",
                                "future outcome was known at recovery time", "no auction/order/fill evidence",
                                "ineligible for original integrated decision and model-performance statistics"]}
    save(EVIDENCE_FILE, evidence)

    cohort_samples = []
    for x in deep:
        cohort_samples.append({"id": f"volume-price-20261021-{x['code']}-historical-v1", "code": x["code"], "name": x["name"],
                               "sector": x["sector"], "signal_date": T, "frozen_at": completed_cn,
                               "rule_version": "volume_price_close_v4_historical_recovery", "structure": x["structure"],
                               "snapshot": {k: x.get(k) for k in ["open", "high", "low", "close", "volume", "change_pct", "amplitude_pct",
                                                                             "rvol5", "rvol10", "rvol20", "position20_pct", "position60_pct",
                                                                             "position120_pct", "clv", "upper_wick_pct", "lower_wick_pct",
                                                                             "distance_ma20_pct", "turnover_pct", "tail_price_change_pct"]},
                               "trigger": "historical hypothesis only; contemporaneous trigger not reconstructed",
                               "invalid": "historical recovery cannot create a tradable T+1 instruction",
                               "eligible_for_model_statistics": False, "is_recommendation": False,
                               "sources": [x["source"]], "report_ids": [REPORT_ID],
                               "results": ([{"as_of": T1, "observation_type": "price_observation",
                                             **x["T_plus_1_price_observation"], "trigger_happened": None,
                                             "executable_net_return_pct": None}]
                                           if x.get("T_plus_1_price_observation") else [])})
    ledger["items"].extend([
        {"id": VALIDATION_ID, "date": T, "recorded_at": completed_cn, "task_id": "volume_price",
         "kind": "historical_gap_recovery_validation", "origin_cohort_id": prior_cohort["id"],
         "origin_report_ids": prior_cohort["report_ids"], "report_ids": [REPORT_ID],
         "rule_version": "volume_price_close_v4", "full_validation_completed": len(observed_prior) == len(prior_samples),
         "full_pool_summary": prior_stats, "full_pool_validations": prior_validations,
         "executable_sample_count": 0, "eligible_for_model_statistics": False},
        {"id": COHORT_ID, "date": T, "task_id": "volume_price", "frozen_at": completed_cn,
         "report_ids": [REPORT_ID], "rule_version": "volume_price_close_v4_historical_recovery",
         "data_cutoff_at": completed_cn, "broad_pool_count": len(pool), "broad_pool_verified_count": len(structures),
         "deep_screen_count": len(deep), "eligible_for_model_statistics": False,
         "provenance": "retrospective_gap_recovery", "samples": cohort_samples},
        {"id": T1_VALIDATION_ID, "date": T1, "recorded_at": completed_cn, "task_id": "volume_price",
         "kind": "historical_gap_recovery_validation", "origin_cohort_id": COHORT_ID,
         "origin_report_ids": [REPORT_ID], "report_ids": [REPORT_ID], "rule_version": "volume_price_close_v4_historical_recovery",
         "full_validation_completed": len(t1_validations) == len(deep), "full_pool_summary": t1_stats,
         "full_pool_validations": t1_validations, "executable_sample_count": 0, "eligible_for_model_statistics": False},
    ])

    lines = [
        f"本报告于{completed_cn}补齐2026-10-21量价档案。它是历史缺口恢复，不是当日收盘时完成的荐股，也不满足原综合决策的事前前置。",
        f"当日市场：上证-0.60%、深证-0.82%、创业板-1.62%，成交约1.4294万亿元；上涨1981、下跌3364、平223，50只封板/73只触板。",
        f"覆盖：复用当日冻结的{len(pool)}只候选入口，恢复{len(structures)}只完整日线结构并深筛{len(deep)}只；不是事后伪称的全A完整扫描。历史换手率和完整分钟量价序列未恢复。",
        f"上一批28只完整验证：{len(observed_prior)}只获得T日日线；收盘为正{prior_stats['positive_close_count']}只，均值{prior_stats['mean_close_pct']}%，中位{prior_stats['median_close_pct']}%，平均MFE {prior_stats['mean_mfe_pct']}%、平均MAE {prior_stats['mean_mae_pct']}%；实际成交0。",
        f"本次恢复深池的T+1日线验证：{len(t1_validations)}只，收盘为正{t1_stats.get('positive_close_count')}只，均值{t1_stats.get('mean_close_pct')}%，中位{t1_stats.get('median_close_pct')}%，平均MFE {t1_stats.get('mean_mfe_pct')}%、平均MAE {t1_stats.get('mean_mae_pct')}%；这些是价格观察，不是可执行T+1策略收益。",
        "典型样本：",
    ]
    for x in displays:
        n = x.get("T_plus_1_price_observation", {})
        lines.append(f"{x['code']} {x['name']}｜{x['structure']}：T涨{x['change_pct']}%，RVOL5/10/20={x['rvol5']}/{x['rvol10']}/{x['rvol20']}，CLV={x['clv']}，120日位置={x['position120_pct']}%，上影={x['upper_wick_pct']}%；T+1收盘观察{n.get('close_pct')}%。")
    lines += [
        "有效/风险反馈：成交放大且收盘靠近高位，只能说明当日推进较好；没有分时杀跌—承接—再突破的完整序列时，不认定真正分歧转一致。高RVOL配合低CLV、长上影或收跌继续列为假转强/兑现风险。缩量上涨单列，不与放量确认混算。",
        "对筛选的具体影响：保留位置×相对量×CLV×板块环境四项交叉；因历史换手与分钟序列缺失，本次不新增正式候选，不调整权重，不把席位或盘口行为认定为资金身份。",
        "待证伪假设：1）低位RVOL≥1.5且CLV≥0.7能否在弱宽度市场优于高位放量；2）高RVOL+长上影的T+1退出质量是否显著更差；3）缩量上涨若次日竞价无板块共振，是否更易回落。均需未来严格前推样本。",
        "成本与T+1：20bp仍只是未校准占位；没有双侧成交、滑点、涨跌停/停牌可成交证据，净收益、胜率、盈亏比和9:50/14:40可执行统计均N/A。",
    ]
    report = {"id": REPORT_ID, "date": T, "task_id": "volume_price", "track": "volume_price",
              "title": "量价研究与每日验证｜2026-10-21历史缺口恢复", "summary": f"恢复{len(structures)}只日线结构、28只深池及上一批28只T日验证；因事后恢复与分钟/换手缺失，不作当时荐股。",
              "body": "\n\n".join(lines), "sources": [EVIDENCE_FILE, "docs/research/market-review-2026-10-21-evidence.json",
                                                              "https://www.dabanke.com/index-20261021.html",
                                                              "https://web.ifzq.gtimg.cn/appstock/app/kline/kline"],
              "report_type": "historical_gap_recovery", "eligible_for_integrated_research": False,
              "provenance": "retrospective_gap_recovery", "published_at": completed_cn, "recorded_at": completed_cn,
              "data_cutoff_at": completed_cn, "run_id": "volume-price-20261021-manual-recovery-v1",
              "broad_pool_count": len(pool), "technical_rows": len(structures), "deep_pool_count": len(deep),
              "formal_candidate_count": 0, "executed_trade_count": 0, "rule_version": "volume_price_close_v4_historical_recovery"}
    research["items"].append(report)
    runs["items"].append({"id": "volume-price-20261021-manual-recovery-v1-completed",
                           "run_id": "volume-price-20261021-manual-recovery-v1", "task_id": "volume_price", "date": T,
                           "trigger": "manual", "started_at": stamp_cn, "recorded_at": completed_cn,
                           "completed_at": completed_cn, "status": "completed",
                           "summary": "历史缺口恢复完成；非原定时执行，不具原综合前置资格。",
                           "report_ids": [REPORT_ID], "recommendation_ids": [], "sources": [EVIDENCE_FILE]})
    save("backend/data/volume_price_samples.json", ledger)
    save("backend/data/research.json", research)
    save("backend/data/task_runs.json", runs)
    (ROOT / "docs/research/volume-price-20261021-historical-recovery-v1.md").write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"report": REPORT_ID, "coverage": evidence["coverage"], "prior_stats": prior_stats,
                      "T1_stats": t1_stats, "display": [(x["code"], x["name"], x["structure"]) for x in displays]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
