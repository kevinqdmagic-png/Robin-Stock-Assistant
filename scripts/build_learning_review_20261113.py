#!/usr/bin/env python3
"""Build the linked 2026-11-13 learning review and one historical recovery.

The reports only summarize immutable snapshots and production outcome archives;
they never create recommendations or infer fills.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_backfills/linked-learning-recovery-20261113-20261114-v1.json"
PUBLISHED = datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0)
PUBLISHED_ISO = PUBLISHED.isoformat()
PUBLISHED_MINUTE = PUBLISHED.strftime("%Y-%m-%d %H:%M")


def receipt(report: dict, *, trigger: str, eligible: bool) -> dict:
    return {
        "id": report["id"] + "-receipt",
        "run_id": report["id"],
        "task_id": "learning_review",
        "date": report["date"],
        "trigger": trigger,
        "started_at": PUBLISHED_ISO,
        "completed_at": PUBLISHED_ISO,
        "recorded_at": PUBLISHED_ISO,
        "status": "completed",
        "analysis_completed": True,
        "eligible_for_integrated_research": eligible,
        "summary": report["summary"],
        "report_ids": [report["id"]],
        "recommendation_ids": [],
    }


current_id = "learning-review-20261113-full-v1"
current_body = f"""研究交易日：2026-11-13｜发布时间：北京时间 {PUBLISHED_MINUTE}（UTC+8）

本轮完成最新已收盘沪深交易日T=2026-11-13的学习复核，观察日D=2026-11-16。范围仅沪深、排除北交所。报告不产生新股票推荐：正式买点0只，原因是学习模块只有价格代理与影子观察、没有真实订单成交；最终综合双标尚未完成，本报告只向下游提供同T成熟样本、失败反例和可证伪提案。

### 数据、去重与成熟度

- 原冻结快照`forward-learning-2026-11-13`记录31条：22条可观察、9条回顾性不合格；23个提供方记录。按证券+实际价格基准日去重后17个事件、8个独立基准日，5条跨任务重叠不重复计数。
- 验证门槛仍为至少36个成熟证券—基准日、20个独立日期；当前成熟T+2特征样本22条、7个信号日，未达标，`promotion_authorized=false`、现行规则未改变。
- 2026-11-13全市场日线档案仅沪深：检查5225只、OHLCV及日期验证5216只，缺失9只，覆盖率99.8278%。主档为BaoStock归档；本轮复用已验证档案，没有并发登录。
- 2026-11-13两时段共4只新冻结影子观察尚未到T+1（最早2026-11-16收盘成熟），不拿周末或事后价格填充。

### 全样本双目标结果

|周期|证券—基准日N|独立基准日|正价格比例%|均值%|中位%|路径MAE≤-5%比例%|
|---|---:|---:|---:|---:|---:|---:|
|T+1|17|8|47.06|-0.804|-1.362|41.18|
|T+2|17|8|52.94|-1.633|0.627|58.82|
|T+5|17|8|29.41|-7.055|-8.545|88.24|
|T+10|17|8|17.65|-10.286|-7.219|94.12|

上涨比例和收益幅度必须分开：T+2正价格比例52.94%，但均值-1.633%，说明少数较大亏损压过上涨频率；T+5/T+10的均值、正比例和路径不利波动同步恶化。以上均为未复权信号日收盘代理，不是可成交买入，也不是实际胜率或净收益。

### 本轮新增：2026-11-12原时点冻结的T+1

生产早尾盘冻结在2026-11-13收盘后新增8个T+1价格结果。相同证券+信号日去重后，按时段和版本分组如下；基准均为原时点Level-1报价到次日未复权收盘，日线结果来自新浪免费备用，成交、费用、限价可成交与净收益均为空。

|时段/策略版本|N/独立信号日|正价格比例%|均值%|最差单笔%|实际成交胜率/净收益|
|---|---:|---:|---:|---:|---|
|09:50 relative `intraday_low_chase_v2`|2/1|0.0|-8.050|-10.502|N/A / N/A|
|09:50 control `momentum_control_v1`|2/1|0.0|-6.922|-7.331|N/A / N/A|
|14:40 relative `intraday_low_chase_v2`|2/1|50.0|-0.641|-2.568|N/A / N/A|
|14:40 control `momentum_control_v1`|2/1|50.0|-2.134|-7.656|N/A / N/A|

累计T+1描述统计：09:50 relative为10个样本/5日，正比例40.0%、均值-2.157%、中位-1.609%、平均盈利+2.215%、平均亏损-5.072%、最差-10.502%；09:50 control为14个/7日，正比例35.714%、均值-2.412%、中位-2.259%、平均盈利+3.175%、平均亏损-5.516%、最差-12.365%。14:40 relative为10个/5日，正比例40.0%、均值+0.520%、中位-0.756%、平均盈利+4.065%、平均亏损-1.843%、最差-3.235%；14:40 control为13个/7日，正比例46.154%、均值+0.264%、中位-1.408%、平均盈利+5.908%、平均亏损-4.574%、最差-7.656%。两组原始候选深度不同，当前又没有共同基准配对统计，不能把差异解释为因果优势。分钟路径未归档，以上时段样本的可证实MAE保持空值。

### 低位、版本与失败归因

低位冻结仅4个证券、1个独立日期：T+1正比例25%、均值-0.413%、最差路径MAE-7.049%；T+2正比例25%、均值-1.451%；T+5正比例75%但均值-0.958%，因为唯一负样本-8.040%压过3个小幅上涨；T+10正比例25%、均值-1.623%、最差路径MAE-10.804%。这再次说明不能用单一“上涨比例”排序，更不能把4只/1日说成已验证策略。

失败归因：早盘2026-11-12 relative两只次日分别出现大幅负价格变化，且相对组比动量对照更差，反驳“低追高筛选在每个交易日都能削弱T+1尾部”的强表述；尾盘组虽均值相对较高，但只有1个新增日期且仍有负样本，不能晋级。全样本T+5/T+10的负均值和高MAE比例说明中期尾部风险未解决。市况标签缺乏同日冻结的统一定义，当前保持`unknown`，不事后贴强弱市标签。

### 可证伪提案与样本外安排

1. 预注册“同一交易日、同一时段、relative与control各2只”的配对比较；至少20个独立日期、每组36个成熟事件后，分别检验正价格比例、均值/中位、平均盈亏与最差尾部，旧版本保留为对照。
2. 把早盘T+1最差跌幅是否持续小于对照作为反证指标；若连续前推样本不支持，停止“防追高降低尾部”的强假设，而不是回看后调参。
3. 市况分层只使用当日15:00前已归档的全市场广度字段；字段缺失即`unknown`，不从未来收益反推市况。
4. 真实晋级仍需订单/成交、手续费、滑点、涨跌停/停牌与T+1可退出证据。当前真实胜率、净收益均为N/A；保持`shadow_only`，不自动调权、不下单。

规则版本`forward_learning_v1 + dual_objective_intraday_v2`。本学习材料可供最终综合读取，但不替代市场、量价、低位、龙虎榜及独立打板的同T完整研究。
"""

current = {
    "id": current_id,
    "date": "2026-11-13",
    "market_date": "2026-11-13",
    "task_id": "learning_review",
    "track": "market_review",
    "run_id": current_id,
    "title": "2026-11-13学习复核｜全样本成熟周期、早尾盘T+1反例与前推提案",
    "summary": "17个去重价格代理事件/8个基准日的T+1至T+10已更新；新增11月12日早尾盘8个T+1结果，早盘relative均值-8.050%、尾盘relative均值-0.641%，均无成交证据。",
    "body": current_body,
    "sources": [
        "backend/data/learning.json#forward-learning-2026-11-13",
        "backend/data/baostock/2026-11-13.json",
        "https://robin-stock-api-production.up.railway.app/api/strategy-lab",
        "https://robin-stock-api-production.up.railway.app/api/intraday-performance?slot=early_pair",
        "https://robin-stock-api-production.up.railway.app/api/intraday-performance?slot=late_pair",
        "https://robin-stock-api-production.up.railway.app/api/daily-results?date=2026-11-13",
    ],
    "status": "completed",
    "analysis_completed": True,
    "eligible_for_integrated_research": True,
    "report_type": "full_daily_research",
    "provenance": "manual_daily_learning_review_from_immutable_snapshots_and_production_outcomes",
    "research_rule_version": "forward_learning_v1+dual_objective_intraday_v2",
    "published_at": PUBLISHED_ISO,
    "recorded_at": PUBLISHED_ISO,
    "market_data_cutoff_at": "2026-11-13T15:00:00+08:00",
    "planned_observation_date": "2026-11-16",
    "recommendation_ids": [],
    "formal_candidate_count": 0,
    "verified_fill_count": 0,
    "sample_count": 31,
    "observed_sample_count": 22,
    "unique_anchor_date_symbols": 17,
    "unique_anchor_dates": 8,
    "full_market_checked_count": 5225,
    "full_market_verified_count": 5216,
    "full_market_missing_count": 9,
    "full_market_coverage_pct": 99.8278,
    "actual_trade_win_rate_pct": None,
    "actual_net_return_pct": None,
    "model_weights_updated": False,
    "buy_order_allowed": False,
}

historical_id = "learning-delivery-recovery-20261016-20261114-v1"
historical_body = f"""研究交易日：2026-10-16｜发布时间：北京时间 {PUBLISHED_MINUTE}（UTC+8）

本次实际补做2026-10-16缺失的学习正文与回执，使用不可变原冻结快照`forward-learning-2026-10-16`（原记录时间2026-10-16 20:08，北京时间）。只复述原时点已成熟结果，不用后来走势补改历史结论、不重建盘中名单；本报告`eligible_for_integrated_research=false`，不替代最新T。

原记录24条：16条可观察、4条待成熟、4条回顾性不合格；按证券+实际价格基准日去重为11个事件、4个实际基准日，5条重叠记录排除。数据是未复权信号日收盘代理，不是实际买入。

|周期|证券—基准日N|独立基准日|正价格比例%|均值%|中位%|MAE≤-5%比例%|
|---|---:|---:|---:|---:|---:|---:|
|T+1|11|4|45.45|-1.367|-1.479|54.55|
|T+2|11|4|36.36|-3.726|-4.987|72.73|
|T+5|5|2|0.00|-13.417|-13.940|100.00|
|T+10|0|0|—|—|—|—|

分策略描述：`market_review_conditional/legacy_not_frozen`的T+1为6个/3日，正比例66.667%但均值-0.644%，平均盈利+3.880%、平均亏损-9.691%、最差收盘-10.002%；T+2正比例50%、均值-2.564%、最差路径MAE-17.528%。`combined_limitup_watch/legacy_not_frozen`的T+1为5个/3日，正比例40%、均值-2.626%、最差路径MAE-9.923%；T+2正比例20%、均值-3.751%、最差MAE-12.380%。T+5只有5个成熟事件且全部负变化，不能外推。`limitup_single_v1`仅1个事件：T+1 -1.479%、T+2 -6.624%、T+5 -14.662%，不是策略胜率。

失败归因：上涨频率较高的市场复盘组仍因大亏样本导致负均值；版本标签未冻结、市况未知、日期相关性高，名义N夸大独立性。原时点T+10没有成熟样本，保持空值；真实成交胜率和净收益均为空。低位冻结样本为0，不补造。

历史规则提案仅登记：把正比例与均值/中位、平均盈亏、最差收盘和路径MAE分开报告；冻结版本与实际基准日；按日期隔离前推验证。首轮仍要求至少36个成熟事件和20个独立日期，且需成交、成本与可退出证据。该补档不修改现行规则、不授权下单。
"""

historical = {
    "id": historical_id,
    "date": "2026-10-16",
    "task_id": "learning_review",
    "track": "market_review",
    "title": "2026-10-16学习补做｜原冻结双目标、成熟周期与尾部反例",
    "summary": "补齐10月16日原冻结学习正文与回执：11个去重事件/4个基准日，T+1均值-1.367%、T+2 -3.726%、当时T+5仅5个且全部为负，T+10未成熟。",
    "body": historical_body,
    "published_at": PUBLISHED_ISO,
    "recorded_at": PUBLISHED_ISO,
    "sources": [
        "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/blob/main/backend/data/learning.json#forward-learning-2026-10-16"
    ],
    "status": "completed",
    "analysis_completed": True,
    "eligible_for_integrated_research": False,
    "report_type": "full_daily_research",
    "provenance": "manual_historical_learning_backfill_from_immutable_snapshot",
    "research_rule_version": "forward_learning_v1_historical_snapshot_only",
    "market_data_cutoff_at": "2026-10-16T15:00:00+08:00",
    "recommendation_ids": [],
    "formal_candidate_count": 0,
    "verified_fill_count": 0,
    "sample_count": 24,
    "unique_anchor_date_symbols": 11,
    "unique_anchor_dates": 4,
    "actual_trade_win_rate_pct": None,
    "actual_net_return_pct": None,
}

bundle = {
    "research": [current, historical],
    "task_runs": [
        receipt(current, trigger="scheduled", eligible=True),
        receipt(historical, trigger="manual_backfill", eligible=False),
    ],
}
OUT.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUT)
