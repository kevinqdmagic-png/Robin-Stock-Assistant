#!/usr/bin/env python3
"""Publish the independent 2026-10-26 learning review and its raw evidence."""
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CN = ZoneInfo("Asia/Shanghai")
MARKET_DATE = "2026-10-26"
SNAPSHOT_ID = "forward-learning-2026-10-26"
REPORT_ID = "learning-review-20261026-forward-v1"
RUN_ID = "learning-review-20261026-scheduled-forward-v1"
EVIDENCE = "docs/research/learning-review-20261026-evidence.json"
PREREQUISITES = {
    "market_review": "market-review-20261026-close-v1",
    "volume_price": "volume-price-20261026-close-v1",
    "low_position": "low-position-20261026-close-v1",
    "dragon_tiger": "dragon-tiger-20261026-close-v1",
}


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def dump(path, value):
    (ROOT / path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def horizon_stats(rows, horizon):
    points = []
    states = Counter()
    for row in rows:
        point = next((p for p in row.get("horizons", []) if p["h"] == horizon), None)
        states[point["status"] if point else "not_applicable"] += 1
        if point and point["status"] == "observed":
            points.append(point["close_pct"])
    return {
        "observed_count": len(points),
        "pending_count": states["pending"],
        "not_applicable_or_unavailable_count": len(rows) - len(points) - states["pending"],
        "mean_close_pct": round(mean(points), 3) if points else None,
        "median_close_pct": round(median(points), 3) if points else None,
        "positive_close_rate_pct": round(sum(p > 0 for p in points) / len(points) * 100, 2)
        if points else None,
    }


def main():
    learning = load("backend/data/learning.json")
    research = load("backend/data/research.json")
    task_runs = load("backend/data/task_runs.json")
    snapshot = next(row for row in learning["runs"] if row["id"] == SNAPSHOT_ID)
    if snapshot["date"] != MARKET_DATE:
        raise ValueError("learning_snapshot_date_mismatch")

    reports = {row["id"]: row for row in research["items"]}
    receipts = task_runs["items"]
    prerequisite_rows = []
    for task_id, report_id in PREREQUISITES.items():
        report = reports.get(report_id)
        if not report or report.get("date") != MARKET_DATE \
                or report.get("report_type") != "full_daily_research" \
                or report.get("eligible_for_integrated_research") is not True \
                or report.get("analysis_completed") is not True:
            raise ValueError(f"incomplete_prerequisite:{task_id}")
        receipt = next((row for row in receipts if report_id in row.get("report_ids", [])
                        and row.get("status") == "completed"), None)
        if not receipt:
            raise ValueError(f"missing_prerequisite_receipt:{task_id}")
        prerequisite_rows.append({
            "task_id": task_id,
            "report_id": report_id,
            "report_type": report["report_type"],
            "eligible_for_integrated_research": True,
            "analysis_completed": True,
            "receipt_id": receipt["id"],
            "receipt_status": receipt["status"],
        })

    now = datetime.now(CN).isoformat()
    metrics = {str(h): horizon_stats(snapshot["evaluations"], h) for h in (1, 2, 5, 10)}
    attributions = dict(Counter(
        reason for row in snapshot["evaluations"] for reason in row.get("attribution", [])))
    provider_errors = dict(Counter(
        error for group in ("evaluations", "low_position_evaluations")
        for row in snapshot[group] for error in row.get("provider_errors", [])))
    unavailable_codes = sorted({
        row["code"] for group in ("evaluations", "low_position_evaluations")
        for row in snapshot[group] if row.get("status") == "provider_unavailable"})

    evidence = {
        "schema_version": 1,
        "id": "learning-review-20261026-evidence-v1",
        "market_date": MARKET_DATE,
        "collected_at": now,
        "data_cutoff_at": f"{MARKET_DATE}T15:00:00+08:00",
        "latest_completed_session_selection": {
            "snapshot_date": MARKET_DATE,
            "actual_recorded_at": snapshot["recorded_at"],
            "backdated_execution_time": False,
        },
        "same_day_prerequisites": prerequisite_rows,
        "learning_snapshot": snapshot,
        "derived_horizon_statistics": metrics,
        "failure_attributions": attributions,
        "provider_error_counts": provider_errors,
        "provider_unavailable_unique_codes": unavailable_codes,
        "limitations": [
            "All horizon changes use signal-day unadjusted close as a price proxy, not a verified fill.",
            "Provider failures remain missing; no price or return is imputed.",
            "The learning archive does not provide an independent dragon-tiger outcome cohort.",
            "No model weights, active selection rules, or thresholds are changed by this review.",
        ],
    }
    dump(EVIDENCE, evidence)

    m1, m2, m5, m10 = (metrics[str(h)] for h in (1, 2, 5, 10))
    validation = snapshot["validation"]
    low = snapshot["low_position_summary"]
    low1, low2 = low["horizons"]["1"], low["horizons"]["2"]
    body = f"""研究交易日T={MARKET_DATE}；本轮在北京时间凌晨运行，按真实时钟回退到最近已完成的中国交易日10月26日。快照实际记录时间为{snapshot['recorded_at']}，没有把执行时间倒填为收盘时刻。10月26日market_review、volume_price、low_position、dragon_tiger四份完整研究及各自completed回执均已核对；量化痕迹不在研究或前置项中。

一、样本与成熟度
学习归档新增{SNAPSHOT_ID}。31条正式历史记录中，当前16条可观察、9条回溯来源不合格、6条因行情源不可用而缺失；共请求23个唯一代码，主源超时后备用源恢复了大部分数据，但仍有{len(unavailable_codes)}个唯一代码不可用。缺失没有填零，也没有沿用旧快照冒充本日新行情。

|信号后交易日|已观察N|均值%|中位数%|正变化率%|待成熟N|
|---|---:|---:|---:|---:|---:|
|T+1|{m1['observed_count']}|{m1['mean_close_pct']}|{m1['median_close_pct']}|{m1['positive_close_rate_pct']}|{m1['pending_count']}|
|T+2|{m2['observed_count']}|{m2['mean_close_pct']}|{m2['median_close_pct']}|{m2['positive_close_rate_pct']}|{m2['pending_count']}|
|T+5|{m5['observed_count']}|{m5['mean_close_pct']}|{m5['median_close_pct']}|{m5['positive_close_rate_pct']}|{m5['pending_count']}|
|T+10|{m10['observed_count']}|{m10['mean_close_pct']}|{m10['median_close_pct']}|{m10['positive_close_rate_pct']}|{m10['pending_count']}|

这些是从信号日未复权收盘起算的价格代理，不是成交收益。因本次6条正式记录行情缺失，16条可观察子集不能与10月23日22条完整可观察集直接比较，也不能据此宣称策略变好或变差。T+2预设失败归因中，6条收盘代理亏损超过2%，8条盘中不利观察超过5%，2条虽收盘为正但经历深回撤。

具备T+2特征且本轮行情可得的样本为{validation['total_mature_t2_featured']}条、{validation['unique_cohort_dates']}个独立信号日；预设门槛为{validation['minimum_samples']}条和{validation['minimum_unique_dates']}日。当前状态仍为{validation['status']}，promotion_authorized=false、strategy_active_rules_changed=false、model_weights_updated=false；不存在足够训练/留出样本，也没有可称为已验证策略的依据。

二、低位与龙虎榜独立留档
低位形态组仍为4条、1个信号日；本次只有1条行情可得。该单条T+1为{low1['mean_close_pct']}%，T+2为{low2['mean_close_pct']}%，T+2路径MAE中位{low2['median_intraperiod_mae_pct']}%；其余3条提供方不可用。N=1且只有一个日期，不能概括为低位策略结果，更不能与正式推荐混算。10月26日低位报告新增3条非交易研究样本，但其未来节点尚未成熟。

龙虎榜10月26日报告已独立归档并核对，但当前learning快照没有独立龙虎榜前推结果组；因此不把71股、9只席位或5只条件观察写成胜率或收益。后续只能从原时点冻结的席位与价格标签开始累计。

三、失败归因与下一轮影子假设
1. 数据完整性门：同日指标必须同时报告可得率和缺失代码；在提供方覆盖恢复前，不用跨日均值变化触发规则调整。该项先作为审计门，不是选股规则。
2. 左尾路径假设：本轮T+2正变化率为{m2['positive_close_rate_pct']}%，但均值{m2['mean_close_pct']}%低于中位数{m2['median_close_pct']}%，且8条出现MAE超过5%，提示少数左尾和路径风险可能比终点方向更关键。未来按预先冻结的MAE分层，在达到独立日期门槛后再做留出检验。
3. 低位延续假设：唯一成熟样本T+1转正、T+2转负且路径深回撤，只能提出“次日冲高不等于两日承接”的可证伪问题；至少积累5个独立信号日并恢复完整行情后再比较行业共振与量价承接。
4. 龙虎榜背离假设：机构/股通净买、价格强弱和后续承接必须作为三维冻结标签；在形成独立T+1/T+2/T+5组前，不从席位净买直接推断持续持仓。

以上假设均未经样本外验证，不自动修改现行规则、阈值或权重。APP没有内置大模型，也不会因使用次数增加而自行提高胜率。"""

    report = {
        "id": REPORT_ID,
        "date": MARKET_DATE,
        "market_date": MARKET_DATE,
        "task_id": "learning_review",
        "track": "market_review",
        "run_id": RUN_ID,
        "title": "每日学习复核｜10月26日行情缺口、成熟度与左尾路径假设",
        "summary": "31条正式记录中16条可观察、9条回溯排除、6条行情缺失；T+2特征样本16条/7日，未达36条/20日门槛，规则与权重不变。",
        "body": body,
        "sources": [
            "https://robin-stock-api-production.up.railway.app/api/learning",
            EVIDENCE,
            "backend/data/learning.json",
        ],
        "report_type": "full_daily_research",
        "eligible_for_integrated_research": False,
        "analysis_completed": True,
        "status": "completed_with_data_gaps",
        "published_at": now,
        "recorded_at": now,
        "data_cutoff_at": f"{MARKET_DATE}T15:00:00+08:00",
        "provenance": "forward_snapshot_review_with_provider_gaps",
        "research_rule_version": "forward_learning_v1",
        "learning_snapshot_id": SNAPSHOT_ID,
        "sample_count": snapshot["sample_count"],
        "mature_t2_featured": validation["total_mature_t2_featured"],
        "unique_cohort_dates": validation["unique_cohort_dates"],
        "promotion_authorized": False,
        "strategy_active_rules_changed": False,
        "model_weights_updated": False,
        "candidate_count": 0,
        "recommendation_ids": [],
        "evidence_file": EVIDENCE,
    }
    receipt = {
        "id": RUN_ID + "-completed",
        "run_id": RUN_ID,
        "task_id": "learning_review",
        "date": MARKET_DATE,
        "trigger": "scheduled",
        "started_at": snapshot["recorded_at"],
        "recorded_at": now,
        "completed_at": now,
        "status": "completed",
        "summary": report["summary"],
        "report_ids": [REPORT_ID],
        "recommendation_ids": [],
        "analysis_completed": True,
        "learning_snapshot_id": SNAPSHOT_ID,
        "eligible_for_integrated_research": False,
        "strategy_active_rules_changed": False,
        "model_weights_updated": False,
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
