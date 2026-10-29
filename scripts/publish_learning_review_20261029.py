#!/usr/bin/env python3
"""Publish the independent T29 learning, intraday and release-recovery review."""
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CN = ZoneInfo("Asia/Shanghai")
T = "2026-10-29"
SNAPSHOT_ID = "forward-learning-2026-10-29"
REPORT_ID = "learning-review-20261029-forward-v1"
RUN_ID = "learning-review-20261029-scheduled-forward-v1"
EVIDENCE = "docs/research/learning-review-20261029-evidence.json"
BASE = "https://robin-stock-api-production.up.railway.app"
HEAD = "a92a7cd26b1b3505834e900fd8dfcf3a0424bdab"
DEPLOYMENT = "d227be2d-1822-433b-b259-bfa162368dc1"
TARGET = "e7f5de229a72a510bc7d6caf0814b60432888746"
REQUIRED = {
    "market_review": "market-review-20261029-close-v1",
    "volume_price": "volume-price-20261029-close-v1",
    "low_position": "low-position-20261029-close-v1",
    "dragon_tiger": "dragon-tiger-20261029-close-v1",
    "combined_pair": "combined-pair-20261029-close-v1",
    "limitup_single": "limitup-single-20261029-close-v2",
}


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def dump(path, value):
    (ROOT / path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get(path):
    with urlopen(BASE + path, timeout=30) as response:
        return json.load(response)


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
            "report_type": report.get("report_type"),
            "analysis_completed": True,
            "eligible_for_integrated_research": report.get("eligible_for_integrated_research"),
            "receipt_id": receipt["id"], "receipt_status": receipt["status"],
        })

    now = datetime.now(CN).isoformat()
    health = get("/health")
    delivery = get("/api/operations/delivery")
    providers = get("/api/operations/providers")
    production_strategy = get("/api/strategy-lab")
    production_learning = get("/api/learning")
    intraday = {}
    performance = {}
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
            "strategy_validated": perf.get("strategy_validated"),
            "automatic_strategy_promotion": perf.get("automatic_strategy_promotion"),
            "executed_trades_verified": perf.get("executed_trades_verified"),
        }

    if health.get("build_commit") != HEAD:
        raise ValueError("production_head_changed:" + str(health.get("build_commit")))
    strategy = summarize_snapshot(snapshot)
    errors = dict(Counter(
        error for group in ("evaluations", "low_position_evaluations")
        for row in snapshot[group] for error in row.get("provider_errors", [])))
    unavailable_codes = sorted({
        row["code"] for group in ("evaluations", "low_position_evaluations")
        for row in snapshot[group] if row.get("status") == "provider_unavailable"})

    evidence = {
        "schema_version": 1,
        "id": "learning-review-20261029-evidence-v1",
        "market_date": T,
        "collected_at": now,
        "data_cutoff_at": T + "T15:00:00+08:00",
        "repository_head_observed": HEAD,
        "release_recovery": {
            "original_target": TARGET,
            "deployed_descendant": HEAD,
            "github_compare": {"status": "ahead", "ahead_by": 5, "behind_by": 0,
                               "merge_base": TARGET},
            "railway_deployment_id": DEPLOYMENT,
            "railway_status": "SUCCESS",
            "public_health": health,
            "issue_23": {"state": "closed", "closed_at_utc": "2026-10-29T19:13:02Z",
                         "comment_id": 6506017695},
            "failed_build_evidence": {
                "deployment_id": "68c47427-f7be-4ce2-a78c-bcc82c4b3e14",
                "status": "FAILED",
                "error": "buildkitd.sock use of closed network connection",
            },
            "official_incident": {
                "url": "https://status.railway.com/incident/ILLVW9WG",
                "resolved_at_utc": "2026-10-28T10:40:00Z",
                "support": "https://station.railway.com",
            },
        },
        "six_complete_research_items": delivery_rows,
        "production_delivery_snapshot": delivery,
        "production_provider_snapshot": providers,
        "production_strategy_snapshot_before_this_delivery": production_strategy,
        "production_learning_snapshot_before_this_delivery": production_learning,
        "resident_intraday_20261029": intraday,
        "resident_intraday_performance_before_this_delivery": performance,
        "github_issues_observed": [
            {"number": 17, "state": "open", "scope": "provider quality and safe failover"},
            {"number": 18, "state": "open", "scope": "immutable daily research recovery"},
            {"number": 19, "state": "open", "scope": "executable T+1 shadow laboratory"},
            {"number": 20, "state": "open", "scope": "staged Android alert delivery"},
            {"number": 23, "state": "closed", "scope": "Railway BuildKit release blocker"},
        ],
        "learning_snapshot": snapshot,
        "deduplicated_strategy_summary": strategy,
        "learning_provider_error_counts": errors,
        "provider_unavailable_unique_codes": unavailable_codes,
        "limitations": [
            "The new low-chase v2 and momentum control have one independent signal date and no mature T+1 result at collection time.",
            "Control rows use shallower Level-1 screening and cannot establish causal superiority or inferiority.",
            "Intraday coverage is partial; early and late records cannot be described as full-market research.",
            "Production provider telemetry is process-bounded and does not persist across deployments.",
            "Price changes use unadjusted close proxies; they are not verified fills, executable net returns or real trades.",
            "No rule, threshold, weight, live order or automatic strategy promotion is changed.",
        ],
    }
    dump(EVIDENCE, evidence)

    h = strategy["horizons"]
    low = snapshot["low_position_summary"]
    early = intraday["early_pair"]
    late = intraday["late_pair"]
    body = f"""研究交易日T={T}；实际复核时间{now}。本轮先核对最新main、Railway、生产API和真实回执，复用market_review、volume_price、low_position、dragon_tiger四份同T完整研究，以及combined_pair和limitup_single两份完整裁决。生产交付核验6/6完成；这只证明交付齐全，不证明策略盈利。

一、学习快照、成熟度与极端风险
新增{SNAPSHOT_ID}，记录时间{snapshot['recorded_at']}。31条历史行中17条可观察、5条行情不可用、9条回溯来源排除；不可用代码为{unavailable_codes}，错误计数为{errors}。没有把缺失填成0，也没有用10月29日盘后信息回填盘中信号。

按同一证券+信号日去重后为{strategy['distinct_signal_date_symbols']}个证券日，剔除{strategy['overlap_rows_excluded']}条跨轨重叠；独立信号日最多7日：

|周期|去重N|独立日|均值%|中位数%|正变化率%|MAE≤-5%占比|
|---|---:|---:|---:|---:|---:|---:|
|T+1|{h['1']['sample_count']}|{h['1']['unique_signal_dates']}|{h['1']['average_price_change_pct']}|{h['1']['median_price_change_pct']}|{h['1']['positive_pct']}|{h['1']['adverse_below_minus_5_pct']}|
|T+2|{h['2']['sample_count']}|{h['2']['unique_signal_dates']}|{h['2']['average_price_change_pct']}|{h['2']['median_price_change_pct']}|{h['2']['positive_pct']}|{h['2']['adverse_below_minus_5_pct']}|
|T+5|{h['5']['sample_count']}|{h['5']['unique_signal_dates']}|{h['5']['average_price_change_pct']}|{h['5']['median_price_change_pct']}|{h['5']['positive_pct']}|{h['5']['adverse_below_minus_5_pct']}|
|T+10|{h['10']['sample_count']}|{h['10']['unique_signal_dates']}|{h['10']['average_price_change_pct']}|{h['10']['median_price_change_pct']}|{h['10']['positive_pct']}|{h['10']['adverse_below_minus_5_pct']}|

T+1的正变化率不能掩盖路径风险：T+2平均仍为-0.636%，T+5平均-5.659%、90.91%的样本出现至少-5%的路径不利观察；T+10仅8条/4日，平均-7.931%、全部出现至少-5%的MAE。原始重复轨中601872的T+10收盘代理最低-26.146%、MAE最低-27.639%，属于需要保留的左尾反证，不是可成交亏损。统一闸门仍为36条且20个独立日期，并要求成交、成本和按日期隔离的留出验证；当前不能训练/留出比较，promotion_authorized=false。

低位组仍只有4条、1个信号日，其中3条可观察。T+1均值0.395%、T+2均值-1.620%、T+5均值-1.998%；单日三只且有1只行情缺失，不能概括低位策略表现。龙虎榜仍无独立统一前推收益组，不能把席位净买直接写成胜率。

二、9:50/14:40防追高v2首日
10月29日09:50记录扫描{early['scanned']}只、有效报价{early['fresh_quotes']}只、日线复核{early['daily_checked']}只：新组002421/600853，MA20乖离6.143%/3.873%，近10日累计0.929%/1.719%；旧动量对照002164/300006。14:40记录仅扫描{late['scanned']}只、有效报价{late['fresh_quotes']}只、日线复核{late['daily_checked']}只：新组600853/000888，MA20乖离4.744%/6.546%，近10日累计1.719%/4.615%；对照001270/002487。两档均是局部股票池，早盘有daily_validation:ValueError，尾盘有2次eastmoney_rank:HTTPError。

v2与控制组都只有一个独立交易日，收集时10月30日尚未收盘，T+1/T+2/T+5/T+10均未成熟，因此性能接口尚无v2或control分组，只有旧版未标记历史。旧版价格观察：早盘T+1为19条/10日、均值-2.604%、极端低于-5%占47.37%；尾盘T+1为19条/10日、均值-0.128%、极端低于-5%占10.53%。旧版筛选深度与v2/对照不同，不能拿这组历史暗示因果胜率。盘中报价到未来收盘也不是买卖净利。

三、发布恢复、失败归因与下一轮假设
Railway BuildKit专项已闭环：原目标{TARGET[:12]}是当前生产{HEAD[:12]}的祖先，生产部署{DEPLOYMENT}为SUCCESS，/health精准返回当前SHA；两档live和performance接口均200，持久历史未覆写，scheduler/store/volume状态正常，所有新旧组仍shadow_only且零验证成交。GitHub #23已在真实读回后关闭。旧失败部署68c47427仍保留buildkitd.sock中断证据；官方US West构建事故于10月28日10:40 UTC标记resolved。代码/CI/部署成功均不代表研究成熟或盈利。

生产providers当前进程只有分钟16次尝试：13次ok、3次degraded；ConnectionError与HTTPError各3次。daily和quote_batch均为no_observations，不能解释为健康。本轮独立日线学习仍出现大量ReadTimeout/HTTPError，说明服务可访问与数据完整必须分开。

可证伪下一步仅保持影子：
1. 预注册比较v2与control的T+1/T+2终点、MAE和缺失率；同股同日去重，至少20个独立交易日、36条后才讨论方向。
2. 对新组按MA20乖离≤7%、近10日涨幅≤5%预先分层；若留出日期的左尾和缺失率不改善，否定“低乖离更抗回撤”。
3. 旧控制组缺少同深度日线筛选，先补齐可比字段或保持不可比；不允许用事后赢家补齐。
4. #17—#20继续open：提供方持久质量、完整研究幂等恢复、真实T+1成交实验和设备推送仍未满足关闭标准。

以上不修改现行选股规则、阈值或权重。APP没有内置大模型，不自动调权、不下实盘单，也不保证获利。"""

    report = {
        "id": REPORT_ID, "date": T, "market_date": T,
        "task_id": "learning_review", "track": "market_review", "run_id": RUN_ID,
        "title": "每日学习复核｜10月29日v2首日、左尾风险与发布恢复闭环",
        "summary": "六项研究6/6齐备；31条学习行去重为11个证券日/最多7个日期，T+5均值-5.659%、T+10均值-7.931%；防追高v2仅首日且无成熟T+1，#23在生产实证后关闭。",
        "body": body,
        "sources": [
            BASE + "/api/operations/delivery", BASE + "/api/operations/providers",
            BASE + "/api/strategy-lab", BASE + "/api/learning",
            BASE + "/api/intraday-live?slot=early_pair",
            BASE + "/api/intraday-live?slot=late_pair",
            BASE + "/api/intraday-performance?slot=early_pair",
            BASE + "/api/intraday-performance?slot=late_pair", EVIDENCE,
            "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/23",
            "https://status.railway.com/incident/ILLVW9WG",
        ],
        "report_type": "full_daily_research",
        "eligible_for_integrated_research": False,
        "analysis_completed": True, "status": "completed_with_data_gaps",
        "published_at": now, "recorded_at": now,
        "data_cutoff_at": T + "T15:00:00+08:00",
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
