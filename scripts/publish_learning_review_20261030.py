#!/usr/bin/env python3
"""Publish the independent T30 learning and intraday forward review."""
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from statistics import mean, median
from urllib.request import urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CN = ZoneInfo("Asia/Shanghai")
T = "2026-10-30"
SNAPSHOT_ID = "forward-learning-2026-10-30"
REPORT_ID = "learning-review-20261030-forward-v1"
RUN_ID = "learning-review-20261030-scheduled-forward-v1"
EVIDENCE = "docs/research/learning-review-20261030-evidence.json"
BASE = "https://robin-stock-api-production.up.railway.app"
HEAD = "2651a2d643edee28938ae376615057df1cd0a819"
DEPLOYMENT = "ac06f164-004c-45e1-a9fd-479995d0500f"
TARGET = "e7f5de229a72a510bc7d6caf0814b60432888746"
REQUIRED = {
    "market_review": "market-review-20261030-close-v1",
    "volume_price": "volume-price-20261030-close-v1",
    "low_position": "low-position-20261030-close-v1",
    "dragon_tiger": "dragon-tiger-20261030-close-v1",
    "combined_pair": "combined-pair-20261030-close-v1",
    "limitup_single": "limitup-single-20261030-close-v2",
}


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def dump(path, value):
    (ROOT / path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get(path):
    with urlopen(BASE + path, timeout=30) as response:
        return json.load(response)


def strategy_breakdown(snapshot):
    """Descriptive per-strategy rows; overlapping market events stay disclosed."""
    unique = {}
    for row in snapshot.get("evaluations", []):
        if row.get("status") not in {"observed", "partially_observed"}:
            continue
        key = (row.get("strategy"), row.get("code"), row.get("signal_date"))
        unique.setdefault(key, row)
    result = []
    for strategy in sorted({key[0] for key in unique}):
        rows = [row for key, row in unique.items() if key[0] == strategy]
        item = {
            "strategy": strategy,
            "stock_date_count": len(rows),
            "independent_signal_dates": len({row["signal_date"] for row in rows}),
            "overlaps_other_strategies": True,
            "horizons": {},
        }
        for horizon in (1, 2, 5, 10):
            pool = []
            for row in rows:
                observation = next((value for value in row.get("horizons", [])
                                    if value.get("h") == horizon
                                    and value.get("status") == "observed"), None)
                if observation:
                    pool.append((row, observation))
            values = [float(value["close_pct"]) for _, value in pool]
            adverse = [float(value["mae_pct"]) for _, value in pool
                       if value.get("mae_pct") is not None]
            item["horizons"][str(horizon)] = {
                "matured_count": len(values),
                "independent_signal_dates": len({row["signal_date"] for row, _ in pool}),
                "mean_close_pct": round(mean(values), 3) if values else None,
                "median_close_pct": round(median(values), 3) if values else None,
                "worst_close_pct": round(min(values), 3) if values else None,
                "worst_mae_pct": round(min(adverse), 3) if adverse else None,
                "executable_net_return": None,
            }
        result.append(item)
    return result


def main():
    import sys
    sys.path.insert(0, str(ROOT / "backend"))
    from strategy_lab import summarize_snapshot

    learning = load("backend/data/learning.json")
    research = load("backend/data/research.json")
    task_runs = load("backend/data/task_runs.json")
    snapshot = next(row for row in learning["runs"] if row["id"] == SNAPSHOT_ID)
    reports = {row["id"]: row for row in research["items"]}
    receipts = task_runs["items"]
    delivery_rows = []
    for task_id, report_id in REQUIRED.items():
        report = reports.get(report_id)
        receipt = next((row for row in receipts if report_id in row.get("report_ids", [])
                        and row.get("status") == "completed"), None)
        if not report or report.get("date") != T or report.get("analysis_completed") is not True:
            raise ValueError("incomplete_report:" + task_id)
        if task_id in {"market_review", "volume_price", "low_position", "dragon_tiger"}:
            if (report.get("report_type") != "full_daily_research"
                    or report.get("eligible_for_integrated_research") is not True):
                raise ValueError("invalid_integrated_prerequisite:" + task_id)
        if not receipt:
            raise ValueError("missing_receipt:" + task_id)
        delivery_rows.append({
            "task_id": task_id, "report_id": report_id,
            "report_type": report.get("report_type"), "analysis_completed": True,
            "eligible_for_integrated_research": report.get("eligible_for_integrated_research"),
            "receipt_id": receipt["id"], "receipt_status": receipt["status"],
        })

    now = datetime.now(CN).isoformat()
    health = get("/health")
    delivery = get("/api/operations/delivery")
    providers = get("/api/operations/providers")
    production_strategy = get("/api/strategy-lab")
    production_learning = get("/api/learning")
    intraday, performance = {}, {}
    for slot in ("early_pair", "late_pair"):
        live = get(f"/api/intraday-live?slot={slot}&limit=20")
        perf = get(f"/api/intraday-performance?slot={slot}")
        row = next((item for item in live.get("items", []) if item.get("date") == T), None)
        if not row:
            raise ValueError("missing_resident_intraday:" + slot)
        intraday[slot] = row
        performance[slot] = {
            "status": perf.get("status"), "version": perf.get("version"),
            "total": perf.get("total"), "groups": perf.get("groups", []),
            "matured_t29_items": [item for item in perf.get("items", [])
                                    if item.get("signal_date") == "2026-10-29"],
            "strategy_validated": perf.get("strategy_validated"),
            "automatic_strategy_promotion": perf.get("automatic_strategy_promotion"),
            "executed_trades_verified": perf.get("executed_trades_verified"),
        }

    if health.get("build_commit") != HEAD:
        raise ValueError("production_head_changed:" + str(health.get("build_commit")))
    if delivery.get("date_cn") != T or delivery.get("verified_count") != 6:
        raise ValueError("production_delivery_not_six_of_six")
    if production_learning.get("latest", {}).get("id") != SNAPSHOT_ID:
        raise ValueError("production_learning_snapshot_mismatch")

    strategy = summarize_snapshot(snapshot)
    breakdown = strategy_breakdown(snapshot)
    errors = dict(Counter(error for row in snapshot.get("evaluations", [])
                          for error in row.get("provider_errors", [])))
    low_errors = dict(Counter(error for row in snapshot.get("low_position_evaluations", [])
                              for error in row.get("provider_errors", [])))
    matured = [item for slot in performance.values() for item in slot["matured_t29_items"]]
    distinct_intraday_events = len({(item["code"], item["signal_date"]) for item in matured})

    evidence = {
        "schema_version": 1,
        "id": "learning-review-20261030-evidence-v1",
        "market_date": T,
        "collected_at": now,
        "data_cutoff_at": T + "T15:30:13+08:00",
        "repository_head_observed": HEAD,
        "release_recovery": {
            "original_target": TARGET,
            "deployed_descendant": HEAD,
            "github_compare": {"status": "ahead", "ahead_by": 14, "behind_by": 0,
                               "merge_base": TARGET},
            "railway_deployment_id": DEPLOYMENT,
            "railway_status": "SUCCESS",
            "no_active_build_and_no_retry_triggered": True,
            "public_health": health,
            "issue_23": {"state": "closed", "state_reason": "completed",
                         "closed_at_utc": "2026-10-29T19:13:02Z", "comments": 2},
            "failed_build_evidence": {
                "deployment_ids": [
                    "c461dbc3-9a01-4b0b-b311-deee8427667d",
                    "66f49d2e-4df4-436a-8a36-502b36c44bc8",
                    "68c47427-f7be-4ce2-a78c-bcc82c4b3e14",
                ],
                "status": "FAILED",
                "error": "buildkitd.sock use of closed network connection",
            },
        },
        "six_complete_research_items": delivery_rows,
        "production_delivery_snapshot": delivery,
        "production_provider_snapshot": providers,
        "production_strategy_snapshot_before_this_delivery": production_strategy,
        "production_learning_snapshot_before_this_delivery": production_learning,
        "resident_intraday_20261030": intraday,
        "resident_intraday_performance": performance,
        "matured_intraday_t29_quote_events": len(matured),
        "matured_intraday_t29_distinct_stock_dates": distinct_intraday_events,
        "github_issues_observed": [
            {"number": 17, "state": "open", "scope": "provider quality and safe failover"},
            {"number": 18, "state": "open", "scope": "immutable daily research recovery"},
            {"number": 19, "state": "open", "scope": "executable T+1 shadow laboratory"},
            {"number": 20, "state": "open", "scope": "staged Android alert delivery"},
            {"number": 23, "state": "closed", "scope": "Railway BuildKit release blocker"},
        ],
        "learning_snapshot": snapshot,
        "deduplicated_strategy_summary": strategy,
        "per_strategy_descriptive_summary": breakdown,
        "learning_provider_error_counts": errors,
        "low_position_provider_error_counts": low_errors,
        "market_regime": {
            "signal_day_2026_10_29": "weak_strong_divergence_retreat",
            "outcome_day_2026_10_30": "weak_volume_expansion_decline",
            "strong_regime_observations_for_v2": 0,
            "source_report_ids": ["market-review-20261029-close-v1",
                                  "market-review-20261030-close-v1"],
        },
        "limitations": [
            "The v2/control T+1 groups contain one independent signal date; T+2/T+5/T+10 are not mature.",
            "The same 600853 stock-date appears at both intraday slots, so eight quote events are seven distinct stock-date events.",
            "Control rows use shallower Level-1 screening and cannot establish causal superiority or inferiority.",
            "Intraday coverage is partial; early and late records cannot be described as full-market research.",
            "Intraday forward records have no minute path, so v2/control MAE is unavailable.",
            "Production provider telemetry is process-bounded and does not persist across deployments.",
            "Price changes use unadjusted close proxies; they are not paper fills, executable net returns or real trades.",
            "No rule, threshold, weight, live order or automatic strategy promotion is changed.",
        ],
    }
    dump(EVIDENCE, evidence)

    h = strategy["horizons"]
    low = snapshot["low_position_summary"]
    early = intraday["early_pair"]
    late = intraday["late_pair"]
    groups = {slot: {(row["cohort"], row["model_version"], row["horizon"]): row
                     for row in value["groups"]}
              for slot, value in performance.items()}
    e_v2 = groups["early_pair"][("low_chase", "intraday_low_chase_shadow_v2", 1)]
    e_ctl = groups["early_pair"][("momentum_control", "intraday_momentum_quote_control_v1", 1)]
    l_v2 = groups["late_pair"][("low_chase", "intraday_low_chase_shadow_v2", 1)]
    l_ctl = groups["late_pair"][("momentum_control", "intraday_momentum_quote_control_v1", 1)]

    rows = {row["strategy"]: row for row in breakdown}
    table = "\n".join(
        f"|{name}|{row['stock_date_count']}|{row['independent_signal_dates']}|"
        f"{row['horizons']['2']['mean_close_pct']}|{row['horizons']['5']['mean_close_pct']}|"
        f"{row['horizons']['10']['mean_close_pct']}|{row['horizons']['10']['worst_mae_pct']}|"
        for name, row in rows.items())
    body = f"""研究交易日T={T}；实际复核时间{now}。本轮先核对最新main、Railway、生产API和真实回执，复用market_review、volume_price、low_position、dragon_tiger四份同T完整研究及combined_pair、limitup_single两份完整裁决。生产交付6/6；volume_price为独立完整报告。交付齐全不等于策略盈利。

一、学习快照、成熟度与分策略结果
本轮复用已经按实际时间生成、且生产可读的{SNAPSHOT_ID}（{snapshot['recorded_at']}），没有重复生成。31条历史信号行中22条可观察、9条回溯来源排除；同一证券+信号日去重后16个证券日/7个独立日期，剔除6条跨轨重叠。核心行提供方错误计数{errors}，低位形态附加行错误计数{low_errors}；错误被保留，没有填零。

|周期|去重N|独立日|均值%|中位数%|正变化率%|MAE≤-5%占比|
|---|---:|---:|---:|---:|---:|---:|
|T+1|{h['1']['sample_count']}|{h['1']['unique_signal_dates']}|{h['1']['average_price_change_pct']}|{h['1']['median_price_change_pct']}|{h['1']['positive_pct']}|{h['1']['adverse_below_minus_5_pct']}|
|T+2|{h['2']['sample_count']}|{h['2']['unique_signal_dates']}|{h['2']['average_price_change_pct']}|{h['2']['median_price_change_pct']}|{h['2']['positive_pct']}|{h['2']['adverse_below_minus_5_pct']}|
|T+5|{h['5']['sample_count']}|{h['5']['unique_signal_dates']}|{h['5']['average_price_change_pct']}|{h['5']['median_price_change_pct']}|{h['5']['positive_pct']}|{h['5']['adverse_below_minus_5_pct']}|
|T+10|{h['10']['sample_count']}|{h['10']['unique_signal_dates']}|{h['10']['average_price_change_pct']}|{h['10']['median_price_change_pct']}|{h['10']['positive_pct']}|{h['10']['adverse_below_minus_5_pct']}|

T+10只有14条/5日，另2个去重证券日未成熟。最差T+10收盘代理为300450的-27.082%；最差路径MAE为002487的-30.361%。这是信号日未复权收盘到未来收盘/区间的价格观察，不是纸面成交，更不是可执行净收益。

分策略描述（策略间共享证券日，不能横向相加成独立样本）：
|策略|证券日N|独立日|T+2均值%|T+5均值%|T+10均值%|T+10最差MAE%|
|---|---:|---:|---:|---:|---:|---:|
{table}

低位形态附加组仍只有{low['sample_count']}条/{low['unique_signal_dates']}个信号日；T+1/T+2/T+5均值分别{low['horizons']['1']['mean_close_pct']}%、{low['horizons']['2']['mean_close_pct']}%、{low['horizons']['5']['mean_close_pct']}%，T+10尚未成熟。它不是全市场普查，也不足以验证低位启动规则。龙虎榜仍没有可比的统一前推成交组。

二、9:50/14:40防追高v2与旧动量对照
10月29日第一批v2现已成熟T+1：
|时段|组别|N/独立日|均值%|中位数%|低于-5%|极端|
|---|---|---:|---:|---:|---:|---|
|09:50|v2低追高|{e_v2['sample_count']}/1|{e_v2['mean_price_change_pct']}|{e_v2['median_price_change_pct']}|{e_v2['below_minus_5_pct']}%|002421 -11.079%|
|09:50|momentum_control|{e_ctl['sample_count']}/1|{e_ctl['mean_price_change_pct']}|{e_ctl['median_price_change_pct']}|{e_ctl['below_minus_5_pct']}%|300006 -6.761%|
|14:40|v2低追高|{l_v2['sample_count']}/1|{l_v2['mean_price_change_pct']}|{l_v2['median_price_change_pct']}|{l_v2['below_minus_5_pct']}%|600853 -2.770%|
|14:40|momentum_control|{l_ctl['sample_count']}/1|{l_ctl['mean_price_change_pct']}|{l_ctl['median_price_change_pct']}|{l_ctl['below_minus_5_pct']}%|001270 -7.373%|

两时段共8个报价事件、按证券+信号日去重为7个事件，600853跨时段共享同一市场事件。信号日T29和结果日T30都属于弱市，强市分层N=0；T+2/T+5/T+10均未成熟，分钟路径与MAE缺失。早盘v2不优于对照、尾盘v2好于对照的相反方向恰好说明单日不能下因果或胜率结论。

T30新冻结：09:50扫描{early['scanned']}只/有效{early['fresh_quotes']}只/日线复核{early['daily_checked']}只，新组300223、000554，对照301079、002149；14:40扫描{late['scanned']}只/有效{late['fresh_quotes']}只/日线复核{late['daily_checked']}只，新组603382、000554，对照002991。新组MA20乖离分别1.703%、6.538%、9.157%、5.246%，近10日累计11.05%、7.143%、11.254%、7.143%。这是局部股票池；早盘有3条daily_validation:ValueError，尾盘有2条eastmoney_rank:HTTPError。下一交易日11月2日前没有T+1，不能补造结果。

三、发布恢复、失败归因与可证伪假设
原目标{TARGET[:12]}是当前main/生产{HEAD[:12]}的祖先，GitHub比较ahead 14、behind 0。Railway部署{DEPLOYMENT}为SUCCESS，公开/health精准返回{HEAD}，两档live/performance均可读且持久历史总数继续增长；#23保持closed。当前没有在建部署，不需要也没有重复触发构建。旧三次BuildKit失败ID及错误继续留档，但不代表当前服务失败。

生产providers为当前进程有界观察：分钟16次尝试、13次ok、3次degraded，ConnectionError/HTTPError各3次；daily和quote_batch无观察，不能解释为健康。#17—#20仍open，分别缺完整持久数据源质量、幂等恢复、可成交T+1实验和设备推送闭环。

下一轮仅验证，不改参数：①把“低MA20乖离/低10日涨幅能降低左尾”作为反证优先假设；002421的-11.079%已构成早期反例，若按日期隔离留出样本仍无左尾改善则否定。②对603382的above_ma20_7pct风险标签预注册比较，不事后移动阈值。③至少20个独立交易日、36条，并具备分钟成交、成本、限价可成交和强/弱市样本后，才讨论晋级。④低位启动、分歧回踩、龙头承接、首板/二板继续在各自完整报告和冻结影子样本验证，本任务不重复生成综合或打板报告。

全部仍为shadow_only；实际成交0、自动调权关闭、实盘下单关闭，不保证获利。"""

    report = {
        "id": REPORT_ID, "date": T, "market_date": T,
        "task_id": "learning_review", "track": "market_review", "run_id": RUN_ID,
        "title": "每日学习复核｜10月30日v2首个T+1、左尾反证与发布持续核验",
        "summary": "六项交付6/6；31条学习行去重为16个证券日/7日，T+5均值-6.398%、T+10均值-10.071%；v2首个T+1仅1日且早晚方向相反，不晋级。",
        "body": body,
        "sources": [
            BASE + "/api/operations/delivery", BASE + "/api/operations/providers",
            BASE + "/api/strategy-lab", BASE + "/api/learning",
            BASE + "/api/intraday-live?slot=early_pair",
            BASE + "/api/intraday-live?slot=late_pair",
            BASE + "/api/intraday-performance?slot=early_pair",
            BASE + "/api/intraday-performance?slot=late_pair", EVIDENCE,
            "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/17",
            "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/18",
            "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/19",
            "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/20",
            "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/23",
        ],
        "report_type": "full_daily_research",
        "eligible_for_integrated_research": False,
        "analysis_completed": True, "status": "completed_with_data_gaps",
        "published_at": now, "recorded_at": now,
        "data_cutoff_at": T + "T15:30:13+08:00",
        "provenance": "forward_snapshot_intraday_and_release_recovery_review",
        "research_rule_version": "forward_learning_v1_intraday_low_chase_shadow_v2",
        "learning_snapshot_id": SNAPSHOT_ID,
        "sample_count": snapshot["sample_count"],
        "deduplicated_signal_date_symbols": strategy["distinct_signal_date_symbols"],
        "unique_cohort_dates": h["2"]["unique_signal_dates"],
        "intraday_v2_independent_dates": 1,
        "promotion_authorized": False,
        "strategy_active_rules_changed": False,
        "model_weights_updated": False,
        "candidate_count": 0, "recommendation_ids": [], "evidence_file": EVIDENCE,
    }
    receipt = {
        "id": RUN_ID + "-completed", "run_id": RUN_ID,
        "task_id": "learning_review", "date": T, "trigger": "scheduled",
        "started_at": snapshot["recorded_at"], "recorded_at": now, "completed_at": now,
        "status": "completed", "summary": report["summary"],
        "report_ids": [REPORT_ID], "recommendation_ids": [],
        "analysis_completed": True, "learning_snapshot_id": SNAPSHOT_ID,
        "eligible_for_integrated_research": False,
        "strategy_active_rules_changed": False, "model_weights_updated": False,
        "delivery_status": "repository_prepared_not_yet_ci_or_production_verified",
        "sources": [EVIDENCE],
    }
    if any(row["id"] == REPORT_ID for row in research["items"]):
        raise ValueError("report_already_exists")
    if any(row["id"] == receipt["id"] for row in task_runs["items"]):
        raise ValueError("receipt_already_exists")
    research["items"].append(report)
    task_runs["items"].append(receipt)
    dump("backend/data/research.json", research)
    dump("backend/data/task_runs.json", task_runs)
    print(json.dumps({"report_id": REPORT_ID, "receipt_id": receipt["id"],
                      "evidence_file": EVIDENCE}, ensure_ascii=False))


if __name__ == "__main__":
    main()
