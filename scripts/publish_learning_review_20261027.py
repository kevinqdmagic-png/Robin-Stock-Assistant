#!/usr/bin/env python3
"""Publish the independent 2026-10-27 learning and operations review."""
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CN = ZoneInfo("Asia/Shanghai")
T = "2026-10-27"
SNAPSHOT_ID = "forward-learning-2026-10-27"
REPORT_ID = "learning-review-20261027-forward-v1"
RUN_ID = "learning-review-20261027-scheduled-forward-v1"
EVIDENCE = "docs/research/learning-review-20261027-evidence.json"
BASE = "https://robin-stock-api-production.up.railway.app"
REQUIRED = {
    "market_review": "market-review-20261027-close-v1",
    "volume_price": "volume-price-20261027-close-v1",
    "low_position": "low-position-20261027-close-v1",
    "dragon_tiger": "dragon-tiger-20261027-close-v1",
    "combined_pair": "combined-pair-20261027-close-v1",
    "limitup_single": "limitup-single-20261027-close-v2",
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
    strategy = summarize_snapshot(snapshot)
    health = get("/health")
    delivery = get("/api/operations/delivery")
    providers = get("/api/operations/providers")
    production_strategy = get("/api/strategy-lab")
    early = get("/api/intraday-live?slot=early_pair&limit=20")
    late = get("/api/intraday-live?slot=late_pair&limit=20")
    errors = dict(Counter(
        error for group in ("evaluations", "low_position_evaluations")
        for row in snapshot[group] for error in row.get("provider_errors", [])))
    unavailable_codes = sorted({
        row["code"] for group in ("evaluations", "low_position_evaluations")
        for row in snapshot[group] if row.get("status") == "provider_unavailable"})
    intraday = {}
    for slot, payload in (("early_pair", early), ("late_pair", late)):
        row = next((item for item in payload.get("items", []) if item.get("date") == T), None)
        if not row:
            raise ValueError("missing_resident_intraday:" + slot)
        intraday[slot] = row

    issues = [
        {"number": 17, "state": "open", "title": "provider-quality telemetry and safe quote failover"},
        {"number": 18, "state": "open", "title": "recover missing complete daily research with immutable audit trail"},
        {"number": 19, "state": "open", "title": "executable T+1 shadow trading laboratory"},
        {"number": 20, "state": "open", "title": "reliable staged Android stock-alert delivery"},
    ]
    evidence = {
        "schema_version": 1,
        "id": "learning-review-20261027-evidence-v1",
        "market_date": T,
        "collected_at": now,
        "data_cutoff_at": T + "T15:00:00+08:00",
        "repository_head_observed": "6d3e2a91fe56dc3c6178cb79e1c54bb78dd6a86c",
        "production_health_before_this_delivery": health,
        "six_complete_research_items": delivery_rows,
        "production_delivery_snapshot": delivery,
        "production_provider_snapshot": providers,
        "production_strategy_snapshot_before_this_delivery": production_strategy,
        "resident_intraday_20261027": intraday,
        "github_issues_observed": issues,
        "learning_snapshot": snapshot,
        "deduplicated_strategy_summary": strategy,
        "learning_provider_error_counts": errors,
        "provider_unavailable_unique_codes": unavailable_codes,
        "limitations": [
            "Production provider telemetry is process-bounded and is not persistent across deployments.",
            "The 09:50 and 14:40 records are partial Level-1 observations, not full-market studies or buy orders.",
            "Price changes use signal-day unadjusted close; they are not verified fills or executable net returns.",
            "The weak-market research-shadow instruction was committed after the T27 close reports and is not backfilled here.",
            "No rule, threshold, model weight, real-money order or automatic promotion is changed.",
        ],
    }
    dump(EVIDENCE, evidence)

    h = strategy["horizons"]
    low = snapshot["low_position_summary"]
    body = f"""研究交易日T={T}；实际复核时间{now}。本轮读取最新main与生产接口，并复用10月27日market_review、volume_price、low_position、dragon_tiger四份同T完整研究及combined_pair、limitup_single两份完整裁决和各自completed回执。生产delivery接口核验6/6完整；这只证明交付齐全，不证明策略盈利。

一、学习快照与数据缺口
新增{SNAPSHOT_ID}，实际记录时间{snapshot['recorded_at']}。31条正式历史记录中仅5条可观察、17条行情不可用、9条回溯来源排除；23个唯一代码中，正式与低位组共有{len(unavailable_codes)}个代码因本轮提供方失败而不可用。错误原样保留为{errors}，没有填零、沿用旧快照或用盘后信息补造成交。

策略实验室按同一证券+信号日去重后，只剩3个独立证券日，剔除2条重叠行：

|周期|成熟N|独立日期|均值%|中位数%|正变化率%|MAE≤-5%占比|
|---|---:|---:|---:|---:|---:|---:|
|T+1|{h['1']['sample_count']}|{h['1']['unique_signal_dates']}|{h['1']['average_price_change_pct']}|{h['1']['median_price_change_pct']}|{h['1']['positive_pct']}|{h['1']['adverse_below_minus_5_pct']}|
|T+2|{h['2']['sample_count']}|{h['2']['unique_signal_dates']}|{h['2']['average_price_change_pct']}|{h['2']['median_price_change_pct']}|{h['2']['positive_pct']}|{h['2']['adverse_below_minus_5_pct']}|
|T+5|{h['5']['sample_count']}|{h['5']['unique_signal_dates']}|{h['5']['average_price_change_pct']}|{h['5']['median_price_change_pct']}|{h['5']['positive_pct']}|{h['5']['adverse_below_minus_5_pct']}|
|T+10|{h['10']['sample_count']}|{h['10']['unique_signal_dates']}|{h['10']['average_price_change_pct']}|{h['10']['median_price_change_pct']}|{h['10']['positive_pct']}|{h['10']['adverse_below_minus_5_pct']}|

T+2虽有2/3为正，但均值仍为-0.770%，因为002074为-6.840%；3条中2条路径MAE不优于-5%。T+10只有002074一条，收盘代理-14.370%、路径MAE-19.270%，只能作为极端左尾个案，不能写成策略长期胜率。统一学习门槛仍为36条且20个独立日期；当前去重后仅3条/3日，训练/留出比较不成立，promotion_authorized=false。

低位组4条仍只有1条可观察，本轮可得的是600900：T+1 -1.241%、T+2 +0.134%、路径MAE -1.643%；另3条行情缺失。与上一快照可得代码不同，不能把两个单样本的变化解释成策略进步。龙虎榜仍未形成独立统一前推收益组。

二、交付、盘中存档与提供方
生产六项完整研究为completed，四项综合前置真实齐备；综合组与D28打板组均为正式0只。10月27日Railway 09:50和14:40两档均实际写入持久卷：各扫描137只、各保留2只局部Level-1观察，数据源错误为空。但两档均明确partial_level1_watch_not_backtested、full_market_coverage=false、strategy_validated=false、recommendation_executable=false，不能替代完整全市场研究或当作买入。

生产providers接口当前进程只记录19次分钟尝试：13次ok、6次degraded、0次unavailable；最近源为腾讯分钟，ConnectionError与HTTPError各6次。daily和quote_batch为no_observations，按接口契约不等于健康。学习补做的独立日线请求则发生大面积双源超时，说明“服务在线/HTTP 200”与“本轮样本完整”必须分开报告。

三、问题与下一轮可证伪假设
GitHub #17、#18、#19、#20均仍open。#17提供方质量、#18完整研究恢复已出现可读诊断与交付核验，但未达到关闭标准；#19真实可执行T+1、#20可靠安卓推送仍缺成交/设备授权等大项，未擅自实施。

1. 数据完整性门：若去重后可观察证券日较上一完整快照大幅下降，跨日均值只作缺失审计，不进入参数比较；待同一批代码双源补齐后验证结论是否稳定。
2. 重叠事件权重：同股同信号日跨研究轨只计一个市场事件；未来比较“等证券日权重”与“原始报告行权重”，若结论方向改变则拒绝晋级。
3. 弱市左尾假设：首次分歧承接、低位启动和首/二板影子组应优先比较MAE与未成交率，而非只看正收益率；至少20个独立交易日后再按日期隔离训练/留出。
4. 低位持续承接：600900单例从T+1负到T+2微正不能证明反转；冻结板块强弱、次日承接和量价回踩后，至少5个独立日期再比较。

弱市双轨指令是在T27收盘研究之后进入main，本任务不回填事后赢家，也不重复生成综合/打板报告；第一批research_shadow样本应从下一次真实交易日原时点冻结。以上均为shadow_only：价格代理不是纸面成交，纸面成交也不是真实成交；APP不自动调权、不下实盘单、不保证获利。"""
    report = {
        "id": REPORT_ID, "date": T, "market_date": T,
        "task_id": "learning_review", "track": "market_review", "run_id": RUN_ID,
        "title": "每日学习复核｜10月27日双源缺口、去重左尾与六项交付核验",
        "summary": "31条正式记录仅5条可观察、17条行情缺失、9条回溯排除；去重后T+2仅3只/3日、均值-0.770%，六项研究与两档盘中存档齐，规则不变。",
        "body": body,
        "sources": [
            BASE + "/api/operations/delivery", BASE + "/api/operations/providers",
            BASE + "/api/strategy-lab", BASE + "/api/learning", EVIDENCE,
            "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/17",
            "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/18",
            "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/19",
            "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/20",
        ],
        "report_type": "full_daily_research",
        "eligible_for_integrated_research": False,
        "analysis_completed": True,
        "status": "completed_with_data_gaps",
        "published_at": now, "recorded_at": now,
        "data_cutoff_at": T + "T15:00:00+08:00",
        "provenance": "forward_snapshot_and_operations_review_with_provider_gaps",
        "research_rule_version": "forward_learning_v1_strategy_lab_v1",
        "learning_snapshot_id": SNAPSHOT_ID,
        "sample_count": snapshot["sample_count"],
        "deduplicated_mature_t2": h["2"]["sample_count"],
        "unique_cohort_dates": h["2"]["unique_signal_dates"],
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
