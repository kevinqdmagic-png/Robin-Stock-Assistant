#!/usr/bin/env python3
"""Build the first weekly research review and one immutable learning recovery."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_backfills/linked-weekly-review-20261109-20261113-v1.json"
NOW = datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0)
NOW_ISO = NOW.isoformat()
NOW_MINUTE = NOW.strftime("%Y-%m-%d %H:%M")


def make_receipt(report: dict, trigger: str) -> dict:
    return {
        "id": report["id"] + "-receipt",
        "run_id": report["id"],
        "task_id": report["task_id"],
        "date": report["date"],
        "trigger": trigger,
        "started_at": NOW_ISO,
        "completed_at": NOW_ISO,
        "recorded_at": NOW_ISO,
        "status": "completed",
        "analysis_completed": True,
        "eligible_for_integrated_research": False,
        "summary": report["summary"],
        "report_ids": [report["id"]],
        "recommendation_ids": [],
    }


weekly_id = "weekly-review-20261109-20261113-v1"
weekly_body = f"""研究交易日：2026-11-13｜发布时间：北京时间 {NOW_MINUTE}（UTC+8）

统计区间：2026-11-09至2026-11-13。本报告为周日`weekly_review`独立周总结，不产生休市日推荐、盘中信号或最终双标，不替代任何每日完整研究。范围仅沪深、排除北交所；所有收益字段均为原冻结报价或未复权收盘代理，没有真实成交时，真实胜率与净收益保持N/A。

### 本周数据与交付质量

- 最新T=2026-11-13的BaoStock沪深日线档案检查5225只、日期与OHLCV验证5216只、缺失9只，覆盖率99.8278%；生产同T缓存仅100只新浪局部样本且标为`partial`，不拿局部缓存冒充全市场。
- 六模块完整交付门禁：11月9日0/6、10日0/6、11日0/6、12日2/6、13日2/6。11月13日仅`market_review`与`volume_price`完整；`low_position`、`dragon_tiger`、`combined_pair`、`limitup_single`仍为partial。跨日欠项56条继续保留，周报不解除它们。
- 11月13日全市场证据显示上证-0.59%、创业板-3.32%，传媒/养殖相对强；盘中策略档案的`market_regime`仍为`unknown`，所以本周不能事后按强弱市分组来解释输赢。
- 11月13日09:50/14:40各2只影子观察已按原时点冻结，但周末尚未成熟T+1；本周统计截至11月12日信号、11月13日收盘结果，不补造11月13日未来收益。

### 本周双目标：上涨比例与变化幅度分开

|时段/版本|周期|N/独立日|正价格比例|均值|中位|平均正/负幅度|最差|
|---|---:|---:|---:|---:|---:|---|---:|
|09:50 relative v2|T+1|8/4|37.5%|-1.799%|-1.609%|+2.295% / -4.255%|-10.502%|
|09:50 control v1|T+1|8/4|50.0%|-0.811%|-0.054%|+3.029% / -4.650%|-7.331%|
|09:50 relative v2|T+2|6/3|33.3%|-1.577%|-2.688%|+2.693% / -3.712%|-5.285%|
|09:50 control v1|T+2|6/3|16.7%|-2.887%|-3.778%|+4.250% / -4.314%|-7.490%|
|14:40 relative v2|T+1|8/4|50.0%|+0.964%|+0.253%|+4.065% / -2.136%|-3.235%|
|14:40 control v1|T+1|8/4|62.5%|+1.905%|+3.293%|+6.034% / -4.978%|-7.656%|
|14:40 relative v2|T+2|6/3|50.0%|+0.529%|+0.217%|+4.575% / -3.516%|-4.905%|
|14:40 control v1|T+2|6/3|50.0%|-1.267%|-4.454%|+8.189% / -10.723%|-12.774%|

本周结论：09:50 relative在T+1的上涨比例、均值和最差值均未胜过对照，直接反驳“低追高筛选每周都能降低早盘尾部”的强假设；T+2虽比对照均值高，但两组都为负且只有3个日期。14:40 relative的T+1均值为正、负样本幅度较小，但上涨比例和均值仍低于对照；T+2相对更稳只是6只/3日的探索结果。两组都没有路径分钟数据，MAE样本为0；订单成交、费用、滑点、限价可成交、不可退出数量均无证据。

### 累计样本与长期反例

|时段/版本|周期|N/独立日|正价格比例|均值|中位|最差|
|---|---:|---:|---:|---:|---:|---:|
|09:50 relative v2|T+1|10/5|40.0%|-2.157%|-1.609%|-10.502%|
|09:50 control v1|T+1|14/7|35.7%|-2.412%|-2.259%|-12.365%|
|09:50 relative v2|T+2|8/4|37.5%|-1.648%|-2.688%|-9.270%|
|09:50 control v1|T+2|12/6|8.3%|-3.812%|-4.095%|-12.288%|
|14:40 relative v2|T+1|10/5|40.0%|+0.520%|-0.756%|-3.235%|
|14:40 control v1|T+1|13/7|46.2%|+0.264%|-1.408%|-7.656%|
|14:40 relative v2|T+2|8/4|50.0%|+0.434%|+0.146%|-4.905%|
|14:40 control v1|T+2|11/6|36.4%|-1.678%|-1.386%|-12.774%|

T+5仍极不成熟：09:50 relative仅2只/1日、正比例0%、均值-8.066%；14:40 relative仅2只/1日、正比例0%、均值-1.427%。T+10没有可比的relative v2成熟组；对照也只有早盘4只/2日、尾盘3只/2日，不作排序。

跨模块全样本按证券+实际基准日去重为17个事件、8个日期：T+1正比例47.06%、均值-0.804%；T+2正比例52.94%但均值-1.633%；T+5正比例29.41%、均值-7.055%；T+10正比例17.65%、均值-10.286%，且路径MAE≤-5%的比例分别为41.18%、58.82%、88.24%、94.12%。上涨频率和平均结果明显不是同一个目标，T+2“过半上涨”仍不能掩盖负均值和尾部。

低位形态只有4只、1个日期：T+5正比例75%却均值-0.958%，唯一负样本-8.040%压过3个小涨；最差路径MAE-10.804%。这不足以说明低位策略有效，只能说明单看正比例容易低估尾部。

### 本周支持、推翻与停止

- **较可靠的是风险结论，不是盈利结论**：跨模块T+5/T+10继续恶化；上涨比例较高时均值仍可为负；没有成交和MAE路径时不能把报价观察改称真实胜率或净收益。
- **被本周反例削弱**：早盘relative能够稳定降低T+1尾部。本周relative最差-10.502%，比同周control最差-7.331%更差。
- **仍待验证**：尾盘relative可能降低负样本幅度。累计T+1平均负幅度-1.843%，小于control的-4.574%，但只有5个与7个日期，候选深度也不完全相同。
- **应停止的表述**：用单周正均值、单一上涨比例或少数极端盈利样本宣称“策略已胜出”；用报价到未来收盘变化冒充可成交净利；按未来结果补贴强弱市标签。

### 下周预注册的赚钱假设

1. 同一日期、同一时段各冻结2只relative与2只control，至少20个独立日期、每组36个成熟事件后再检验；主指标同时包含正比例、均值、中位、平均盈亏、最差5%尾部，不能只选有利指标。
2. 尾盘relative的可证伪目标是“在不明显降低正比例的前提下，把平均负幅度和最差跌幅压低”；若连续前推样本不满足，停止该风险优势假设。
3. 补齐原冻结后至收盘/次日的分钟路径，计算可证实MAE，并记录涨跌停、停牌、无成交和T+1不可退出；没有这些字段，真实交易胜率与成本后净收益继续为空。
4. 市况只用当日冻结的全市场广度与指数字段分层；缺失即`unknown`。弱市/强市对照必须先定义、后观察，不从收益反推标签。
5. 继续保留`shadow_only`与旧版本对照；不自动调权、不修改正式买点门槛、不下单。当前研究门槛36个事件/20个独立日期及按日期隔离的样本外验证尚未满足。

本周新增的是可复核反例和更明确的尾部风险假设，不是保证获利的策略结论。
"""

weekly = {
    "id": weekly_id,
    "date": "2026-11-13",
    "task_id": "weekly_review",
    "track": "market_review",
    "run_id": weekly_id,
    "title": "周总结｜11月9日至13日双目标、早尾盘反例与下周前推假设",
    "summary": "周内早盘relative T+1为8只/4日、均值-1.799%，尾盘relative为8只/4日、均值+0.964%；均未在T+1同时胜过对照。累计跨模块T+5/T+10均值继续恶化，保持shadow_only。",
    "body": weekly_body,
    "sources": [
        "backend/data/learning.json#forward-learning-2026-11-13",
        "backend/data/baostock/2026-11-13.json",
        "https://robin-stock-api-production.up.railway.app/api/strategy-lab",
        "https://robin-stock-api-production.up.railway.app/api/intraday-performance?slot=early_pair",
        "https://robin-stock-api-production.up.railway.app/api/intraday-performance?slot=late_pair",
        "https://robin-stock-api-production.up.railway.app/api/operations/delivery?date=2026-11-13",
        "https://robin-stock-api-production.up.railway.app/api/operations/recovery?since=2026-11-02",
    ],
    "status": "completed",
    "analysis_completed": True,
    "eligible_for_integrated_research": False,
    "report_type": "weekly_research",
    "provenance": "weekly_review_from_immutable_archives_and_production_forward_results",
    "research_rule_version": "weekly_dual_objective_review_v1",
    "published_at": NOW_ISO,
    "recorded_at": NOW_ISO,
    "market_data_cutoff_at": "2026-11-13T15:00:00+08:00",
    "statistics_period_start": "2026-11-09",
    "statistics_period_end": "2026-11-13",
    "recommendation_ids": [],
    "formal_candidate_count": 0,
    "verified_fill_count": 0,
    "actual_trade_win_rate_pct": None,
    "actual_net_return_pct": None,
    "model_weights_updated": False,
    "buy_order_allowed": False,
}

historical_id = "learning-delivery-recovery-20261019-20261115-v1"
historical_body = f"""研究交易日：2026-10-19｜发布时间：北京时间 {NOW_MINUTE}（UTC+8）

本次实际补做2026-10-19缺失的学习正文与回执，使用不可变原冻结快照`forward-learning-2026-10-19`（原记录时间2026-10-19 20:13，北京时间）。只复述原时点已成熟价格代理，不用后来行情改写、不重建盘中名单；本报告不进入当前综合。

原记录27条：18条可观察、6条回顾性不合格、3条待成熟；按证券+实际价格基准日去重为13个事件、5个基准日。数据为未复权信号日收盘代理，不是成交。

|周期|N/独立基准日|正价格比例|均值|中位|MAE≤-5%比例|
|---|---:|---:|---:|---:|---:|
|T+1|13/5|53.85%|-0.481%|+0.182%|46.15%|
|T+2|13/5|46.15%|-2.328%|-3.444%|61.54%|
|T+5|8/3|12.50%|-9.837%|-10.452%|100.00%|
|T+10|0/0|—|—|—|—|

`market_review_conditional/legacy_not_frozen`的T+1为8只/4日，正比例75%、均值+0.615%，但平均亏损-9.691%、最差-10.002%；T+2正比例62.5%、均值-0.582%、最差路径MAE-17.528%。`combined_limitup_watch`的T+1为5只/3日、正比例40%、均值-2.626%；T+2正比例20%、均值-3.751%。`limitup_single_v1`只有1个事件，T+1 -1.479%、T+2 -6.624%、T+5 -14.662%，不能推断总体。

失败归因：上涨频率较高的市场组仍受大幅负样本拖累；版本未冻结、市况未知、日期相关性高。T+5仅8个事件且全部路径MAE低于或等于-5%，T+10在原时点没有成熟样本，保持空值。真实胜率、净收益、不可成交数量为空。

历史提案只登记：同时报告正比例、均值/中位、平均盈亏与尾部；冻结版本和实际基准日；按日期隔离前推。最低36个成熟事件、20个独立日期及真实成交/成本证据未满足，不改规则、不调权、不下单。
"""

historical = {
    "id": historical_id,
    "date": "2026-10-19",
    "task_id": "learning_review",
    "track": "market_review",
    "title": "2026-10-19学习补做｜正比例、负均值与T+5尾部反例",
    "summary": "补齐10月19日原冻结学习正文与回执：13个去重事件/5个基准日，T+1正比例53.85%但均值-0.481%，T+5仅8个且均值-9.837%，原时点T+10未成熟。",
    "body": historical_body,
    "sources": [
        "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/blob/main/backend/data/learning.json#forward-learning-2026-10-19"
    ],
    "status": "completed",
    "analysis_completed": True,
    "eligible_for_integrated_research": False,
    "report_type": "full_daily_research",
    "provenance": "manual_historical_learning_backfill_from_immutable_snapshot",
    "research_rule_version": "forward_learning_v1_historical_snapshot_only",
    "published_at": NOW_ISO,
    "recorded_at": NOW_ISO,
    "market_data_cutoff_at": "2026-10-19T15:00:00+08:00",
    "recommendation_ids": [],
    "formal_candidate_count": 0,
    "verified_fill_count": 0,
    "sample_count": 27,
    "unique_anchor_date_symbols": 13,
    "unique_anchor_dates": 5,
    "actual_trade_win_rate_pct": None,
    "actual_net_return_pct": None,
}

bundle = {
    "research": [weekly, historical],
    "task_runs": [
        make_receipt(weekly, "scheduled"),
        make_receipt(historical, "manual_backfill"),
    ],
}
OUT.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUT)
