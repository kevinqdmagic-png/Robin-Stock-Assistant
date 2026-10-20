#!/usr/bin/env python3
"""Append the complete 2026-10-20 market-review report, samples and receipt."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backend" / "data"
EVIDENCE_PATH = ROOT / "docs" / "research" / "market-review-2026-10-20-evidence.json"
REPORT_ID = "market-review-20261020-close-v1"
RUN_ID = "market-review-20261020-scheduled-close-v1"

SECTOR = {
    "600148": "汽车零部件/军工", "003029": "网络安全/量子科技", "002076": "LED/信息安全",
    "002929": "通信/边缘AI", "600860": "机器人/氢能", "002696": "饲料/水产",
    "000530": "冷链设备", "603341": "消费电子/边缘AI", "600241": "新能源/机器人",
    "002242": "消费/机器人", "603273": "专用设备/机器人", "002917": "民爆/军工",
    "002376": "金融设备/AI", "002088": "耐火材料", "688836": "人形机器人",
    "603366": "能源设备/消费", "001323": "家居消费", "603636": "软件/数字政务",
    "300458": "边缘AI/芯片", "300709": "消费电子/机器人", "002596": "海南基建",
    "300031": "游戏/机器人", "002164": "传动设备/机器人", "300825": "汽车设计/机器人",
    "001388": "通信设备", "301378": "数字政务/软件", "688795": "GPU/半导体",
    "603466": "数字内容/AI",
}


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def save(name: str, value):
    (DATA / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pct(value):
    return "N/A" if value is None else f"{value:+.2f}%"


def main():
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    now_utc = dt.datetime.now(dt.timezone.utc)
    now_cn = now_utc.astimezone(dt.timezone(dt.timedelta(hours=8)))
    completed_at = now_cn.isoformat(timespec="seconds")
    recorded_at = now_utc.isoformat(timespec="seconds")
    source_urls = [
        "https://www.cls.cn/detail/2509693",
        "https://finance.eastmoney.com/a/202610203901282391.html",
        "https://stock.stcn.com/article/detail/3468762.html",
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData",
        "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688",
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        "https://web.ifzq.gtimg.cn/appstock/app/minute/query",
        "https://www.cninfo.com.cn/new/disclosure/stock?stockCode=300458",
        "https://www.cninfo.com.cn/new/disclosure/stock?stockCode=300825",
        "docs/research/market-review-2026-10-20-evidence.json",
    ]

    rows = []
    for row in evidence["deep_pool"]:
        change = float(row["changepercent"])
        structure = "放量推进/分歧承接"
        if change >= 9.5:
            structure = "封板或近封板/次日可买性待验"
        if row["code"].startswith(("300", "301", "688")):
            structure = "20%制度/高波动承接"
        rows.append(
            f"|{row['code']} {row['name']}|{SECTOR[row['code']]}|{float(row['trade']):.2f}/{change:+.2f}%|"
            f"{float(row['turnoverratio']):.1f}%|{row.get('rvol5', 0):.2f}/{row.get('rvol10', 0):.2f}/{row.get('rvol20', 0):.2f}|"
            f"{row.get('clv', 0):.3f}|{row.get('dist_ma20', 0):+.1f}%|{pct(row.get('tail_1400_close_pct'))}/"
            f"{row.get('tail_volume_share', 0) * 100:.1f}%|{structure}|"
        )
    pool_table = "\n".join(rows)

    vals = evidence["previous_pool_validation"]
    close_values = sorted(float(x["close_pct"]) for x in vals)
    median_close = (close_values[13] + close_values[14]) / 2
    avg_close = sum(close_values) / len(close_values)
    avg_mfe = sum(float(x["mfe_pct"]) for x in vals) / len(vals)
    avg_mae = sum(float(x["mae_pct"]) for x in vals) / len(vals)
    positive = sum(float(x["close_pct"]) > 0 for x in vals)
    tail_loss = sum(float(x["mae_pct"]) <= -5 for x in vals)

    body = f"""交易日T=2026-10-20，行情事实截止当日16:15:00+08:00；报告实际完成时间为{completed_at}。本报告只完成market_review，不能替代volume_price、low_position、dragon_tiger三份独立完整研究，也不是盘后综合双标。quant_research已取消。APP只展示归档与统计，不内置大模型或自动训练权重。

一、市场复盘（事实）

上证3735.37（+0.12%）、深成指11801.29（-0.14%）、创业板2739.20（-0.26%）、科创50 1342.42（+1.00%）。沪深指数口径成交1.456万亿元，较10月19日放量约186亿元；Sina全A有效股票汇总为1.471万亿元，两个口径分开保留。

全A原始覆盖5574只，其中5568只有有效收盘与昨收：3777涨、1668跌、123平。公开收盘综述确认超过3700股上涨；本地可复算的非ST普通主板代理口径为46只封板、79只触板、33只触板未封、6只跌停，代理炸板率33/79=41.8%。该口径不含ST、20%/30%制度和上市初期无涨跌幅限制，不能冒充交易所全市场涨跌停总数。公开资料只列出大业股份3板及福莱新材、宁波东力、浙江荣泰2板，完整逐层晋级分母未取得，因此最高可见高度为3板，晋级率记数据不足而不臆造。

人形机器人最强，公开综述称板块逾10股涨停；边缘AI、软件、半导体、教育和能源设备同步偏强。煤炭、贵金属、保险、券商、航运等偏弱。与10月19日相比，跌停代理数从25降至6、上涨家数明显修复且量能略增，情绪从退潮分化转为“低位修复、科技扩散”；但深成指和创业板仍收绿，尚不足以定义全面上行周期。

10月21日重点观察：①机器人和边缘AI能否由封板扩散转为非一字换手核心继续承接；②上证能否突破3740.07、创业板能否收复2790.12，否则宽度修复可能只是一日轮动；③代理炸板率41.8%能否下降且跌停不重新扩大，作为T+1退出环境验证。

二、独立扫描、重复率与28只深筛

全A有效覆盖5568只；建立120只广泛池并深筛28只，覆盖机器人、半导体、通信、软件、汽车、军工、消费、能源设备、基建、传媒和材料等至少11类方向，未把持仓、自选或用户询问股票自动纳入。

相对10月14、15、16、19四个可复算完整池，本池有7只去重后重复：吉大正元、星光股份、京城股份、冰山冷热、金奥博、宝通科技、宁波东力，7/28=25.0%。10月13日缺同口径完整池，严格过去5/10交易日重复率仍标记样本不足，不用四次结果冒充5/10日统计。冰山冷热连续出现是因机器人/冷链方向持续高成交，但距MA20+45.6%、换手44.4%，本轮只留作高位反例，不升级为两只观察。

|代码/名称|板块|收盘/涨跌|换手|RVOL5/10/20|CLV|距MA20|14点后涨跌/量占比|结构|
|---|---|---:|---:|---|---:|---:|---|---|
{pool_table}

量价支持：全志科技300458收28.64、涨11.27%、换手7.86%，RVOL20=1.82、CLV=1.000、距MA20仍-5.1%，14点后+2.18%；阿尔特300825收11.52、涨9.40%、换手12.29%，RVOL20=2.84、CLV=0.737、距MA20约-0.2%，14点后+0.70%。二者均处于低位反转而非远离均线的加速段，但只能由10月21日回踩承接和板块同步确认。

量价反例：冰山冷热距MA20+45.6%、换手44.4%，百洋股份距MA20+27.7%、换手28.7%，时代万恒距MA20+40.3%、换手32.9%，均存在高换手/高乖离；天元智能、精研科技、新北洋冲高后未收在最高附近；摩尔线程虽涨11.16%，但RVOL20仅1.30且绝对价格、波动较高。封板股收盘强不等于次日能以合理价格成交。

三、上一完整池及冻结条件验证

10月19日深筛28只已全部取得10月20日日线观察：{positive}只收涨，收盘收益均值{avg_close:+.3f}%、中位数{median_close:+.3f}%；MFE均值{avg_mfe:+.3f}%、MAE均值{avg_mae:+.3f}%，{tail_loss}/28只MAE不高于-5%。这些是相对10月19日收盘的价格观察，不是逐只可执行策略收益。

广东宏大002683：开/高/低/收30.10/30.55/29.11/30.17。开盘满足冻结区间，09:31进入29.30—29.75回踩区，10:51后重新站上30.15，且未跌破28.70；但“军工或低空至少两只非一字核心同向”未取得可独立核验的冻结时点板块证据，故整体条件仍记未验证、无成交，不把价格序列倒推成完整触发。

宇环数控002903：开/高/低/收25.04/25.40/24.39/24.90。13:41进入23.95—24.45回踩区，但之后未重新站上25.05，记未触发、无成交。前一版H3仍无可执行样本，不公布胜率、盈亏比或最佳卖出时段。

10月19日冻结的指数三情景也未完整命中：上证最高3740.07，未突破3743.80；宽度3777家上涨又超出震荡情景的1800—3200区间；下行阈值未触发。该失败暴露了“指数未突破但宽度显著修复”的遗漏，今日按事前规则记为未覆盖情形，不事后修改旧条件。

四、本研究组10月21日两只条件观察（非综合双标）

1. 全志科技300458——边缘AI/芯片低位放量反转。参考价28.64，压力30.18（MA20）/30.50，20日高点34.47。10月21日仅在开盘27.80—29.30、回踩27.45—28.05缩量守住后重新站28.70，且边缘AI/半导体至少两只非一字核心未批量转弱时进入模拟样本。高开29.60以上不追；跌破26.90、30.10—30.50放量滞涨或板块反转均放弃。若触发，受T+1约束最早10月22日退出。

2. 阿尔特300825——机器人/汽车设计低位反转。参考价11.52，压力12.06/12.40，20日高点13.45。10月21日仅在开盘11.10—11.85、回踩10.95—11.30守住后重新站11.60，且机器人换手核心延续、汽车方向不形成孤立拖累时观察。高开12.10以上不追；跌破10.75、12.00—12.20放量滞涨或机器人板块转弱均放弃。若触发，最早10月22日退出。其当日10.01—12.06振幅超过20%、CLV仅0.737，隔夜风险高于全志科技。

主要替代：金奥博距MA20+19.0%且换手18.7%，低位优势不足；天元智能冲高15.05后收14.53，价格推进未保持；摩尔线程RVOL20仅1.30、绝对价格和波动过高；冰山冷热高乖离高换手。长春一东、润建股份、龙旗科技等封板对象无法证明10月21日普通买入可执行性，也未升级。

五、10月21日指数三情景冻结（无概率）

上行/宽度延续：上证站上3740.07或创业板站上2790.12并维持30分钟，且上涨家数>3000、成交节奏不低于1.456万亿元；即使指数暂未越界，若上涨家数>3600、跌停继续不高于6且科技主线扩散，也归入“宽度主导上行”。失效为上证回落至3720下方、上涨不足2200且科技主线转弱。

震荡：主要指数运行在10月20日区间内（上证3702.44—3740.07、创业板2706.41—2790.12），成交相对今日约±8%，边界均未维持突破30分钟；宽度仅作内部强弱描述，不再设置会留下空档的硬区间。任一指数有效突破边界并满足对应宽度条件则震荡失效。

下行：上证跌破3702.44或创业板跌破2706.41后30分钟不能收回，同时上涨家数<1800、下跌家数>3500，成交放大且代理跌停明显高于6。失效为上证重新站回3735、上涨超过2800且跌停/炸板同步收敛。

六、发现与下一项可证伪假设

冻结H4：宽度主导的科技修复日，距MA20不高于0%、RVOL20>1.5且尾盘不弱的未封板样本，只有次日完成“缩量回踩—关键位守住—再放量收复”，其T+1退出质量才可能优于封板难买、高乖离和低相对量对照。全志科技、阿尔特作为前推样本；冰山冷热、金奥博和摩尔线程作为反例/对照。后续只追加触发、失效、MFE/MAE和最早合法退出，不修改今日条件。

术语：CLV=(收盘-最低)/(最高-最低)，越接近1表示收盘越靠近全天高位；RVOL20为当日成交量相对之前20个完成交易日平均量；MFE/MAE分别为相对冻结参考的最大有利/不利价格波动。事实、推断与假设已分开，本研究不保证收益。"""

    report = {
        "id": REPORT_ID, "date": "2026-10-20", "task_id": "market_review", "track": "market_review",
        "run_id": RUN_ID, "report_type": "full_daily_research", "eligible_for_integrated_research": True,
        "published_at": completed_at, "recorded_at": completed_at,
        "data_cutoff_at": "2026-10-20T16:15:00+08:00",
        "title": "2026-10-20 A股收盘复盘、全池验证与10月21日条件观察",
        "summary": "全A有效扫描5568只、广泛池120只、深筛28只；上涨3777家、机器人和边缘AI领涨，上一池28只平均收盘-0.27%。本组冻结全志科技、阿尔特两只10月21日条件观察。",
        "body": body, "sources": source_urls, "research_version": "market_review_close_v7",
        "volume_price_version": "volume_price_close_v3", "market_date": "2026-10-20",
        "broad_pool_count": 120, "deep_pool_count": 28,
        "previous_pool_status": "2026-10-19 full pool verified on 2026-10-20",
        "previous_pool_verified_count": 28, "facts_hypotheses_separated": True,
        "codes": [x["code"] for x in evidence["deep_pool"]],
        "provenance": "contemporaneous_close_research",
        "integrated_prerequisite_policy": "market_review+volume_price+low_position+dragon_tiger; quant_research cancelled",
    }
    research = load("research.json")
    if not any(x["id"] == REPORT_ID for x in research["items"]):
        research["items"].append(report)

    recommendations = load("recommendations.json")
    by_id = {x["id"]: x for x in recommendations["items"]}
    prior_results = {
        "market-review-20261019-002683-close-v1": {
            "id": "market-review-20261019-002683-close-v1-trigger-result-20261020",
            "as_of": "2026-10-20T15:00:00+08:00", "recorded_at": completed_at,
            "market_date": "2026-10-20", "horizon": "planned entry day trigger verification",
            "status": "not_verified", "trigger_status": "price_sequence_met_but_sector_confirmation_unverified",
            "entry_fill_status": "no_fill", "executed_trade": False, "strategy_sample_activated": False,
            "observed_open": 30.10, "observed_high": 30.55, "observed_low": 29.11, "observed_close": 30.17,
            "executable_net_return_pct": None,
            "source": "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=sz002683",
            "report_id": REPORT_ID,
            "note": "价格顺序满足开盘、回踩与再站条件，但冻结时点的两只板块同伴证据无法独立核验；保守记未验证、无成交。",
        },
        "market-review-20261019-002903-close-v1": {
            "id": "market-review-20261019-002903-close-v1-trigger-result-20261020",
            "as_of": "2026-10-20T15:00:00+08:00", "recorded_at": completed_at,
            "market_date": "2026-10-20", "horizon": "planned entry day trigger verification",
            "status": "not_triggered", "trigger_status": "pullback_reached_but_reclaim_absent",
            "entry_fill_status": "no_fill", "executed_trade": False, "strategy_sample_activated": False,
            "observed_open": 25.04, "observed_high": 25.40, "observed_low": 24.39, "observed_close": 24.90,
            "executable_net_return_pct": None,
            "source": "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=sz002903",
            "report_id": REPORT_ID,
            "note": "13:41进入冻结回踩区，之后未重新站上25.05；保留未触发样本。",
        },
    }
    for rec_id, result in prior_results.items():
        if rec_id in by_id and not any(x.get("id") == result["id"] for x in by_id[rec_id].setdefault("results", [])):
            by_id[rec_id]["results"].append(result)

    new_recs = [
        {
            "id": "market-review-20261020-300458-close-v1", "date": "2026-10-20", "published_at": completed_at,
            "group": "close", "strategy": "market_review_conditional", "task_id": "market_review",
            "provenance": "contemporaneous_close_research", "data_cutoff_at": "2026-10-20T16:15:00+08:00",
            "planned_entry_date": "2026-10-21", "earliest_legal_exit_date_if_bought": "2026-10-22",
            "current_stage": "frozen_conditional_observation", "report_ids": [REPORT_ID], "sources": source_urls,
            "roundtrip_cost_assumption_bps": 20, "results": [], "code": "300458", "name": "全志科技",
            "model": "low_position_edge_ai_reversal_v7",
            "reason": "收28.64，涨11.27%，换手7.86%，RVOL20 1.82，CLV1.000，距MA20 -5.1%，14点后+2.18%；边缘AI/芯片低位放量反转。",
            "reference_price": 28.64, "reference_price_time": "2026-10-20T15:00:00+08:00",
            "reference_price_market_date": "2026-10-20", "reference_price_source": "https://qt.gtimg.cn/q=sz300458",
            "reference_entry_range": [27.45, 28.70], "operational_invalid_price": 26.90,
            "trigger": "10月21日开盘27.80—29.30；回踩27.45—28.05缩量守住后重新站28.70，且边缘AI/半导体至少两只非一字核心未批量转弱。",
            "invalid": "高开29.60以上不追；跌破26.90、30.10—30.50放量滞涨或板块反转均放弃。",
            "exit_plan": "若10月21日真实触发，最早10月22日卖；弱开失守26.90优先退出，强势观察30.18、30.50。",
        },
        {
            "id": "market-review-20261020-300825-close-v1", "date": "2026-10-20", "published_at": completed_at,
            "group": "close", "strategy": "market_review_conditional", "task_id": "market_review",
            "provenance": "contemporaneous_close_research", "data_cutoff_at": "2026-10-20T16:15:00+08:00",
            "planned_entry_date": "2026-10-21", "earliest_legal_exit_date_if_bought": "2026-10-22",
            "current_stage": "frozen_conditional_observation", "report_ids": [REPORT_ID], "sources": source_urls,
            "roundtrip_cost_assumption_bps": 20, "results": [], "code": "300825", "name": "阿尔特",
            "model": "low_position_robot_auto_reversal_v7",
            "reason": "收11.52，涨9.40%，换手12.29%，RVOL20 2.84，CLV0.737，距MA20 -0.2%，14点后+0.70%；机器人/汽车设计低位反转，但日内振幅超过20%。",
            "reference_price": 11.52, "reference_price_time": "2026-10-20T15:00:00+08:00",
            "reference_price_market_date": "2026-10-20", "reference_price_source": "https://qt.gtimg.cn/q=sz300825",
            "reference_entry_range": [10.95, 11.60], "operational_invalid_price": 10.75,
            "trigger": "10月21日开盘11.10—11.85；回踩10.95—11.30守住后重新站11.60，且机器人换手核心延续、汽车方向不形成孤立拖累。",
            "invalid": "高开12.10以上不追；跌破10.75、12.00—12.20放量滞涨或机器人板块转弱均放弃。",
            "exit_plan": "若10月21日真实触发，最早10月22日卖；弱开失守10.75优先退出，强势观察12.06、12.40。",
        },
    ]
    existing = {x["id"] for x in recommendations["items"]}
    recommendations["items"].extend(x for x in new_recs if x["id"] not in existing)

    task_runs = load("task_runs.json")
    receipt_id = RUN_ID + "-completed"
    receipt = {
        "id": receipt_id, "run_id": RUN_ID, "task_id": "market_review", "date": "2026-10-20",
        "trigger": "scheduled", "started_at": "2026-10-20T08:45:13+00:00",
        "recorded_at": recorded_at, "completed_at": recorded_at, "status": "completed",
        "summary": "完成10月20日全A有效5568只扫描、120只广泛池、28只深筛、上一池28只验证、两只条件观察及10月21日指数情景冻结。",
        "report_ids": [REPORT_ID], "recommendation_ids": [x["id"] for x in new_recs],
        "research_rule_version": "market_review_close_v7", "analysis_completed": True,
        "delivery_status": "repository_pending", "sources": source_urls,
    }
    if not any(x["id"] == receipt_id for x in task_runs["items"]):
        task_runs["items"].append(receipt)

    save("research.json", research)
    save("recommendations.json", recommendations)
    save("task_runs.json", task_runs)
    print(json.dumps({"report": REPORT_ID, "recommendations": [x["id"] for x in new_recs],
                      "receipt": receipt_id, "completed_at": completed_at}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
