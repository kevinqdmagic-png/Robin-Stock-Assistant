#!/usr/bin/env python3
"""Append the complete 2026-10-19 market-review report, samples and receipt."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backend" / "data"
EVIDENCE_PATH = ROOT / "docs" / "research" / "market-review-2026-10-19-evidence.json"
REPORT_ID = "market-review-20261019-close-v1"
RUN_ID = "market-review-20261019-scheduled-close-v1"

SECTOR = {
    "002343": "传媒/短剧", "002889": "物流/供应链", "000576": "军工电子",
    "002626": "保健品", "002103": "文化消费", "600329": "中药", "002134": "PCB",
    "603188": "染料化工", "600825": "传媒", "002683": "民爆/军工", "300031": "游戏/机器人",
    "002085": "低空经济/汽车", "001216": "消费陶瓷", "002903": "机器人/数控",
    "605189": "纺织", "603278": "轮胎材料", "603348": "汽车零部件", "600435": "军工导航",
    "000530": "冷链设备", "605058": "PCB", "002777": "数字政务", "601778": "光伏电站",
    "001211": "家居消费", "002748": "化工", "001233": "轮胎", "000860": "白酒/养殖",
    "002164": "传动设备", "600487": "通信/电网",
}


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pct(value):
    return "N/A" if value is None else f"{value:+.2f}%"


def main():
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    now_utc = dt.datetime.now(dt.timezone.utc)
    now_cn = now_utc.astimezone(dt.timezone(dt.timedelta(hours=8)))
    completed_at = now_cn.isoformat(timespec="seconds")
    recorded_at = now_utc.isoformat(timespec="seconds")
    source_urls = [
        "https://lianban.net/days/2026-10-19.html",
        "https://stock.eastmoney.com/a/cdpfx.html",
        "https://news.caijingmobile.com/flash/list",
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData",
        "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688",
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        "https://web.ifzq.gtimg.cn/appstock/app/minute/query",
        "https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllBulletin/stockid/002683.phtml",
        "https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllBulletin/stockid/002903.phtml",
        "docs/research/market-review-2026-10-19-evidence.json",
    ]

    lines = []
    for row in evidence["deep_pool"]:
        structure = "放量推进/分歧承接"
        if float(row["changepercent"]) >= 9.5:
            structure = "封板或近封板/次日可买性待验"
        if row["code"].startswith(("300", "301", "688")):
            structure = "20%制度/高波动承接"
        lines.append(
            f"|{row['code']} {row['name']}|{SECTOR[row['code']]}|{float(row['trade']):.2f}/{float(row['changepercent']):+.2f}%|"
            f"{float(row['turnoverratio']):.1f}%|{row.get('rvol5',0):.2f}/{row.get('rvol10',0):.2f}/{row.get('rvol20',0):.2f}|"
            f"{row.get('clv',0):.3f}|{row.get('dist_ma20',0):+.1f}%|{pct(row.get('tail_1400_close_pct'))}/"
            f"{row.get('tail_volume_share',0)*100:.1f}%|{structure}|"
        )
    table = "\n".join(lines)

    vals = evidence["previous_pool_validation"]
    closes = sorted(x["close_pct"] for x in vals)
    median = (closes[13] + closes[14]) / 2

    body = f"""交易日T=2026-10-19，行情事实截止当日16:15:00+08:00；报告实际完成时间为{completed_at}。本报告仅完成market_review，不能替代volume_price、low_position、dragon_tiger三份独立完整研究，也不是盘后综合双标。quant_research已取消。APP只展示归档与验证，不内置大模型或自动训练权重。

一、市场复盘（事实）

上证3730.92（+0.39%）、深成指11817.42（+0.13%）、创业板2746.29（-0.94%）、科创50 1329.19（-2.17%）。沪深指数口径成交约1.438万亿元，较10月16日约1.555万亿元缩量约1170亿元；Sina全A入口汇总为1.448万亿元，两个口径分开保留。

全A原始覆盖5574只，其中5568只有有效收盘与昨收：2274涨、3129跌、165平。外部16:30暂定口径为46只涨停、21只炸板、11只连板、最高3板，情绪标记退潮；本地可复算的非ST普通主板口径为40只收于涨停、76只触板、36只未封、25只跌停。差异来自ST、20%/30%制度、上市初期及价格边界，均不混算。

银行托住上证，但创业板和科创50明显弱于主板；机器人、通信、军工、化工、低空经济仍有局部强度，农业偏弱，成长内部继续分化。10月16日的普涨修复没有延续为全面反转，今日属于“权重护盘、题材局部活跃、宽度偏弱的退潮分化”。

10月20日重点观察：①上证能否突破并站稳今日高点3743.80，同时创业板/科创50止跌；②机器人、军工和通信的非一字换手核心能否回踩后再放量，而非仅靠封板股维持表面强度；③今日暂定46只涨停、21只炸板与17%的1进2能否改善，若跌停继续约25只则隔夜退出风险仍高。

二、独立扫描、重复率与28只深筛

全A有效覆盖5568只；建立120只广泛池并深筛28只，覆盖传媒、物流、军工、机器人、通信、PCB、医药、消费、汽车、光伏、化工等至少11类方向，未将持仓、自选或用户询问股票自动纳入。

相对10月14、15、16三个可复算完整池，本池有6只去重后重复：宝通科技300031、冰山冷热000530、广博股份002103、世龙实业002748、富春染织605189、慈文传媒002343，6/28=21.4%。因10月13日没有同口径完整池，严格5/10交易日重复率仍标记样本不足，不以三日结果冒充5/10日统计。

|代码/名称|板块|收盘/涨跌|换手|RVOL5/10/20|CLV|距MA20|14点后涨跌/量占比|结构|
|---|---|---:|---:|---|---:|---:|---|---|
{table}

量价支持：广东宏大002683收30.11、涨7.92%、换手5.30%，RVOL20=4.94、CLV=0.940、距MA20仅+9.0%，14点后+0.87%；宇环数控002903收24.96、涨8.85%、换手19.13%，RVOL20=2.31、CLV=0.914、仍低于MA20约8.9%，14点后+2.09%。两者都必须用10月20日回踩承接和再转强确认，不能据形态断言资金身份。

量价反例：慈文传媒距MA20+63.1%、换手46.5%，新华传媒距MA20+101.5%、RVOL20超过20，均属高位高波动；天津普林振幅超过20%、换手22.0%且尾盘回落；久远银海盘中冲高13.85后收13.42，未能保持最高价附近；顺鑫农业冲高11.29后收10.97且尾盘转弱。封板股次日可买性不能由收盘涨停倒推。

三、上一完整池与冻结条件验证

10月16日深筛28只已全部取得10月19日日线观察：9只收涨，收盘收益均值-1.943%、中位数{median:.3f}%；MFE均值+2.477%、MAE均值-5.373%，16/28只MAE不高于-5%。这些是相对10月16日收盘的价格观察，不是逐只可执行策略收益。

安达维尔300719：开/高/低/收12.20/12.36/11.88/12.22。09:38进入11.75—12.05回踩区，但随后最高分钟价12.34，未重新站上冻结条件12.45；记未触发、无成交。

龙建股份600853：开/高/低/收3.62/3.76/3.52/3.54。早盘高点出现在回落之前；最低分钟价3.53，未进入冻结的3.43—3.52分钟确认区，更没有形成“回踩后重新站3.60”的顺序；记未触发、无成交。日线最高最低不能替代触发顺序。

前一版H2两只样本均未激活，可执行样本仍为0，不能宣布胜率或最佳卖出时段。两只未触发以及上一池整体负收益，支持继续坚持条件确认而非收盘后机械追涨。

四、本研究组10月20日两只条件观察（非综合双标）

1. 广东宏大002683——军工/低空板块共振后的首次分歧确认。参考价30.11，压力30.25/31.00。10月20日仅在开盘29.45—30.60、回踩29.30—29.75缩量守住后重新站30.15，且军工或低空方向至少两只非一字核心同向时进入模拟样本。高开31.10以上不追；跌破28.70、30.25—31.00放量不进或板块高标跌停均放弃。若触发，受T+1约束最早10月21日退出。

2. 宇环数控002903——机器人方向低位高波动反转后的承接验证。参考价24.96，压力25.22/26.00。10月20日仅在开盘24.30—25.45、回踩23.95—24.45缩量守住后重新站25.05，且机器人板块换手核心未批量转弱时观察。高开25.80以上不追；跌破23.55、25.22—26.00放量不进或板块孤立均放弃。若触发，最早10月21日退出。风险是当日换手19.13%、振幅13.60%，隔夜波动显著高于广东宏大。

主要替代：久远银海因冲高回落且未保住强势区被替代；天津普林因超大振幅、高换手和尾盘回落被替代；顺鑫农业因冲高回落、板块同步性不足被替代；北方导航虽属军工强势，但距MA20约+13.8%，低位优势弱于广东宏大。收盘封板的万丰奥威、文灿股份、亨通光电等无法证明次日普通买入可执行性，未升级。

五、10月20日指数三情景冻结（无概率）

上行：上证突破3743.80并维持30分钟，红盘家数>3200，沪深成交节奏不低于10月19日，炸板率与跌停数同步收敛；失效为跌回3716且红盘不足2200。

震荡：上证主要运行于3692.29—3743.80，红盘约1800—3200，成交继续温和缩量，题材轮动但无持续扩散；任一边界有效突破30分钟则震荡情景失效。

下行：跌破3692.29后30分钟不能收回，下跌家数>3800且成交同比放大，跌停数高于25；失效为重新站回3730且红盘超过2800、炸板和跌停同步收敛。

六、发现与下一项可证伪假设

冻结H3：在指数分化、市场宽度偏弱阶段，距MA20不高于约10%、CLV>0.88、尾盘不弱且有板块共振的未封板样本，只有次日完成“缩量回踩—关键位不破—再放量收复”才可能改善T+1退出质量。广东宏大与宇环数控作为前推样本，慈文传媒/新华传媒作为高乖离对照，天津普林作为高振幅反例。后续只追加触发、失效、MFE/MAE和最早合法退出，不修改今天条件。

术语：CLV=(收盘-最低)/(最高-最低)，越接近1表示收盘越靠近全天高位；RVOL20为当日成交量相对之前20个完成交易日平均量；MFE/MAE分别为相对冻结参考的最大有利/不利价格波动。事实、推断和假设已分开，本研究不保证收益。"""

    report = {
        "id": REPORT_ID, "date": "2026-10-19", "task_id": "market_review", "track": "market_review",
        "run_id": RUN_ID, "report_type": "full_daily_research", "eligible_for_integrated_research": True,
        "published_at": completed_at, "recorded_at": completed_at, "data_cutoff_at": "2026-10-19T16:15:00+08:00",
        "title": "2026-10-19 A股收盘复盘、全池验证与10月20日条件观察",
        "summary": "全A有效扫描5568只、广泛池120只、深筛28只；权重护盘但成长及宽度偏弱，上一池28只平均收盘-1.94%。本研究组冻结广东宏大、宇环数控两只10月20日条件观察。",
        "body": body, "sources": source_urls, "research_version": "market_review_close_v6",
        "volume_price_version": "volume_price_close_v3", "market_date": "2026-10-19",
        "broad_pool_count": 120, "deep_pool_count": 28,
        "previous_pool_status": "2026-10-16 full pool verified on 2026-10-19",
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
        "market-review-20261016-300719-close-v1": {
            "id": "market-review-20261016-300719-close-v1-trigger-result-20261019",
            "as_of": "2026-10-19T15:00:00+08:00", "recorded_at": completed_at,
            "market_date": "2026-10-19", "horizon": "planned entry day trigger verification",
            "status": "not_triggered", "trigger_status": "pullback_reached_but_reclaim_absent",
            "entry_fill_status": "no_fill", "executed_trade": False, "strategy_sample_activated": False,
            "observed_open": 12.20, "observed_high": 12.36, "observed_low": 11.88, "observed_close": 12.22,
            "executable_net_return_pct": None,
            "source": "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=sz300719",
            "report_id": REPORT_ID,
            "note": "09:38进入回踩区，但随后未站上冻结的12.45；保留未触发样本。",
        },
        "market-review-20261016-600853-close-v1": {
            "id": "market-review-20261016-600853-close-v1-trigger-result-20261019",
            "as_of": "2026-10-19T15:00:00+08:00", "recorded_at": completed_at,
            "market_date": "2026-10-19", "horizon": "planned entry day trigger verification",
            "status": "not_triggered", "trigger_status": "required_pullback_reclaim_sequence_absent",
            "entry_fill_status": "no_fill", "executed_trade": False, "strategy_sample_activated": False,
            "observed_open": 3.62, "observed_high": 3.76, "observed_low": 3.52, "observed_close": 3.54,
            "executable_net_return_pct": None,
            "source": "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=sh600853",
            "report_id": REPORT_ID,
            "note": "早盘高点先出现，最低分钟价3.53，未形成冻结的回踩区后重新站3.60顺序；不倒推成交。",
        },
    }
    for rec_id, result in prior_results.items():
        if rec_id in by_id and not any(x.get("id") == result["id"] for x in by_id[rec_id].setdefault("results", [])):
            by_id[rec_id]["results"].append(result)

    new_recs = [
        {
            "id": "market-review-20261019-002683-close-v1", "date": "2026-10-19", "published_at": completed_at,
            "group": "close", "strategy": "market_review_conditional", "task_id": "market_review",
            "provenance": "contemporaneous_close_research", "data_cutoff_at": "2026-10-19T16:15:00+08:00",
            "planned_entry_date": "2026-10-20", "earliest_legal_exit_date_if_bought": "2026-10-21",
            "current_stage": "frozen_conditional_observation", "report_ids": [REPORT_ID], "sources": source_urls,
            "roundtrip_cost_assumption_bps": 20, "results": [], "code": "002683", "name": "广东宏大",
            "model": "sector_resonance_first_divergence_v6",
            "reason": "收30.11，换手5.30%，RVOL20 4.94，CLV0.940，距MA20 +9.0%，14点后+0.87%；军工/低空共振但须次日回踩再转强确认。",
            "reference_price": 30.11, "reference_price_time": "2026-10-19T15:00:00+08:00",
            "reference_price_market_date": "2026-10-19", "reference_price_source": "https://qt.gtimg.cn/q=sz002683",
            "reference_entry_range": [29.30, 30.15], "operational_invalid_price": 28.70,
            "trigger": "10月20日开盘29.45—30.60；回踩29.30—29.75缩量守住后重新站30.15，且军工或低空至少两只非一字核心同向。",
            "invalid": "高开31.10以上不追；跌破28.70、30.25—31.00放量不进或板块高标跌停均放弃。",
            "exit_plan": "若10月20日真实触发，最早10月21日卖；弱开失守28.70优先退出，强势观察30.25、31.00。",
        },
        {
            "id": "market-review-20261019-002903-close-v1", "date": "2026-10-19", "published_at": completed_at,
            "group": "close", "strategy": "market_review_conditional", "task_id": "market_review",
            "provenance": "contemporaneous_close_research", "data_cutoff_at": "2026-10-19T16:15:00+08:00",
            "planned_entry_date": "2026-10-20", "earliest_legal_exit_date_if_bought": "2026-10-21",
            "current_stage": "frozen_conditional_observation", "report_ids": [REPORT_ID], "sources": source_urls,
            "roundtrip_cost_assumption_bps": 20, "results": [], "code": "002903", "name": "宇环数控",
            "model": "low_position_reversal_robot_resonance_v6",
            "reason": "收24.96，换手19.13%，RVOL20 2.31，CLV0.914，低于MA20约8.9%，14点后+2.09%；机器人方向低位反转但振幅与换手较高。",
            "reference_price": 24.96, "reference_price_time": "2026-10-19T15:00:00+08:00",
            "reference_price_market_date": "2026-10-19", "reference_price_source": "https://qt.gtimg.cn/q=sz002903",
            "reference_entry_range": [23.95, 25.05], "operational_invalid_price": 23.55,
            "trigger": "10月20日开盘24.30—25.45；回踩23.95—24.45缩量守住后重新站25.05，且机器人换手核心未批量转弱。",
            "invalid": "高开25.80以上不追；跌破23.55、25.22—26.00放量不进或板块孤立均放弃。",
            "exit_plan": "若10月20日真实触发，最早10月21日卖；弱开失守23.55优先退出，强势观察25.22、26.00。",
        },
    ]
    existing = {x["id"] for x in recommendations["items"]}
    recommendations["items"].extend(x for x in new_recs if x["id"] not in existing)

    task_runs = load("task_runs.json")
    receipt_id = RUN_ID + "-completed"
    receipt = {
        "id": receipt_id, "run_id": RUN_ID, "task_id": "market_review", "date": "2026-10-19",
        "trigger": "scheduled", "started_at": "2026-10-19T08:42:52+00:00",
        "recorded_at": recorded_at, "completed_at": recorded_at, "status": "completed",
        "summary": "完成10月19日全A有效5568只扫描、120只广泛池、28只深筛、上一池28只验证、两只条件观察与10月20日指数三情景冻结。",
        "report_ids": [REPORT_ID], "recommendation_ids": [x["id"] for x in new_recs],
        "research_rule_version": "market_review_close_v6", "analysis_completed": True,
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
