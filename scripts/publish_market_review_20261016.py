#!/usr/bin/env python3
"""Append the complete 2026-10-16 market-review report, samples and receipt."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backend" / "data"
EVIDENCE_PATH = ROOT / "docs" / "research" / "market-review-2026-10-16-evidence.json"
REPORT_ID = "market-review-20261016-close-v1"
RUN_ID = "market-review-20261016-scheduled-close-v1"


SECTOR = {
    "000530":"冷链设备", "300111":"光伏/医药", "600668":"医药建材", "003029":"网络安全",
    "002076":"照明/机器人", "300107":"航空材料", "300719":"航空装备", "002917":"民爆装备",
    "000099":"通用航空", "000995":"白酒", "603668":"水产养殖", "002343":"文化传媒",
    "301010":"冷链节能", "301696":"智能装备", "300699":"碳纤维/军工", "603193":"个护消费",
    "600501":"航天装备", "603168":"医药", "600853":"基建/冰雪经济", "002437":"创新药",
    "301555":"复合材料", "301357":"军工结构件", "600860":"氢能装备", "600127":"粮食消费",
    "600319":"化工", "688295":"碳纤维/低空", "000887":"汽车零部件", "603334":"生物基材料",
}


def load(name):
    return json.loads((DATA / name).read_text())


def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def pct(v):
    return "N/A" if v is None else f"{v:+.2f}%"


def main():
    evidence = json.loads(EVIDENCE_PATH.read_text())
    now_utc = dt.datetime.now(dt.timezone.utc)
    now_cn = now_utc.astimezone(dt.timezone(dt.timedelta(hours=8)))
    completed_at = now_cn.isoformat(timespec="seconds")
    source_urls = [
        "https://news.bjd.com.cn/2026/10/16/11997442.shtml",
        "https://lianban.net/days/2026-10-16.html",
        "https://www.dabanke.com/?_canonical_recover=20260920",
        "https://biz.finance.sina.com.cn/data_reveal/index.php",
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData",
        "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688",
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        "https://web.ifzq.gtimg.cn/appstock/app/minute/query",
        "https://www.sse.com.cn/assortment/stock/list/info/announcement/index.shtml?productId=603193",
        "https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllBulletin/stockid/300719.phtml",
        "https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllBulletin/stockid/600853.phtml",
        "docs/research/market-review-2026-10-16-evidence.json",
    ]

    vals = evidence["previous_pool_validation"]
    closes = sorted(x["close_pct"] for x in vals)
    median = (closes[13] + closes[14]) / 2
    lines = []
    for z in evidence["deep_pool"]:
        struct = "封板/买入可行性待验" if float(z["changepercent"]) >= 9.5 and z["symbol"][:2] in {"sh","sz"} and z["code"][0] not in {"3","6"} else "放量推进/分歧承接"
        if z["code"].startswith(("300", "301", "688")):
            struct = "20%制度/高波动承接"
        lines.append(
            f"|{z['code']} {z['name']}|{SECTOR[z['code']]}|{float(z['trade']):.2f}/{float(z['changepercent']):+.2f}%|"
            f"{float(z['turnoverratio']):.1f}%|{z.get('rvol5',0):.2f}/{z.get('rvol10',0):.2f}/{z.get('rvol20',0):.2f}|"
            f"{z.get('clv',0):.3f}|{z.get('dist_ma20',0):+.1f}%|{pct(z.get('tail_1400_close_pct'))}/{z.get('tail_volume_share',0)*100:.1f}%|{struct}|"
        )
    table = "\n".join(lines)

    body = f"""交易日T=2026-10-16，行情事实截止当日15:35:45+08:00；本报告实际完成时间为{completed_at}。本轮遵循四份完整研究前置：market_review、volume_price、low_position、dragon_tiger；quant_research已取消。这里仅完成market_review，不替代另三份独立报告，也不是盘后综合双标。APP只展示归档与验证，不内置大模型或自动权重训练。

一、市场复盘（事实）

上证3716.28（+0.24%）、深成指11802.46（-0.12%）、创业板2772.38（-0.39%）、科创50 1358.65（-0.06%）。沪深成交约1.555万亿元，较10月15日约1.633万亿元缩量约780亿元；本次Sina全A入口汇总含北交等口径为1.569万亿元，两个口径分开保留。

全市场原始覆盖5576只，其中5570只有有效收盘与昨收：3301涨、2127跌、142平。外部复盘口径为61只涨停、49只炸板、约12只跌停、7只连板、最高11板，封板率约54%；本地可复算的非ST普通主板口径为56只收于涨停、110只触板、54只未封、14只跌停。差异来自ST、20%/30%制度、上市首日及收盘价四舍五入边界，均不混算。

新华传媒11板打开高度，但昨日30只首板仅4只1进2（13.3%），昨日7只二板以上仅3只晋级（42.9%）；盘面从早盘约4800只红盘收窄到3301只。低空经济、汽车、贵金属、地产、石化和发电设备相对强，军工早盘爆发；半导体高开低走，PCB、医药/生物科技、传媒、海运、教育和互联网偏弱。情绪判定为“冰点后修复但冲高回落、强度分化”，不是全面反转。

10月19日重点观察：①上证能否有效站稳10月16日高点3750.77而不是再次午后回落；②军工/低空经济的非一字换手核心能否缩量回踩后再放量；③炸板49—54只是否明显下降、1进2是否高于13.3%，否则高位情绪与宽度修复相背离。

二、独立扫描、重复率与28只深筛

全A有效覆盖5570只；建立120只广泛池并深筛28只，覆盖冷链、军工航空、低空经济、基建、汽车零部件、医药、消费、化工、传媒、网络安全等至少10类方向。未把持仓、自选或用户提问股票自动纳入。

可取得完整池的10月14、15两日与本池重复6只：金奥博002917、建新股份300107、晶雪节能301010、冰山冷热000530、向日葵300111、尖峰集团600668，去重后6/28=21.4%。由于10月13日受阻且更早完整池不连续，严格5/10交易日重复率均标记“完整样本不足”；21.4%只表示现有两日对照，不冒充完整5日统计。

|代码/名称|板块|收盘/涨跌|换手|RVOL5/10/20|CLV|距MA20|14点后涨跌/量占比|结构|
|---|---|---:|---:|---|---:|---:|---|---|
{table}

量价支持：安达维尔300719收12.40、RVOL20=6.10、CLV=0.721、距MA20仅+4.2%，但14点后-0.96%；龙建股份600853收3.59、RVOL20=5.42、CLV=0.730、距MA20+8.0%，14点后-0.55%。两者均是放量后仍有上影/尾盘分歧，必须以10月19日回踩承接和再转强确认，不能将今日上涨当作“主力建仓完成”。

量价反例：冰山冷热距MA20约+42.2%、换手33.2%；慈文传媒距MA20+52.4%、换手48.2%；润本股份虽距MA20仅+2.5%，但10月19日有301,257,000股首发限售股上市流通，事件风险直接压过形态；誉衡药业换手28.6%且存在董事高管减持预披露；中复神鹰14点后-2.84%且存在定增稀释风险。

三、上一完整池与冻结样本验证

10月15日深筛28只已全部取得10月16日日线观察：8只收涨，收盘收益均值-1.835%、中位数{median:.3f}%；MFE均值+3.864%、MAE均值-5.477%，16/28只MAE不高于-5%。市场宽度修复并未改善该高活跃池的中位收益，说明“昨日强势股”仍有显著负反馈。这些是相对昨日收盘的价格观察，不是逐只策略收益。

佛塑科技000973：开/高/低/收11.99/12.05/11.79/11.96。09:45触及11.80回踩区，但全天最高12.05，未重新站上冻结条件12.20，记未触发、无成交。

恩捷股份002812：开/高/低/收48.99/49.35/45.71/46.26。09:31回踩47.88后未重新站上48.60，随后跌破46.35失效位，记未触发且失效、无成交；不能因开盘曾高于48.60倒推成交，因为冻结顺序要求先回踩再收复。

洪都航空600316是10月15日已激活的模拟条件样本：10月16日开/高/低/收35.12/38.61/35.12/37.66；09:41首个分钟价36.24达到第一观察位36.20，09:51分钟价37.50达到第二观察位。原规则没有冻结分批权重，因此只记录两个价位可观察到，不虚构单一可执行净收益；T+1退出质量判为良好。

四、本研究组10月19日两只条件观察（非综合双标）

1. 安达维尔300719——主升首次分歧/军工低空共振。参考价12.40，涨10.62%，成交2.39亿元，换手10.83%，RVOL5/10/20=4.99/6.26/6.10，CLV0.721，距MA20+4.2%，压力12.79/13.08。10月19日仅在开盘11.95—12.60、回踩11.75—12.05缩量守住后重新站12.45，且军工/低空经济非一字核心未批量转弱时进入模拟样本。高开12.90以上不追；跌破11.55、冲击12.79放量不进或板块高标跌停均放弃。若触发最早10月20日退出，弱开失守11.55优先退出，强势观察12.79、13.08。风险：创业板20%波动、2026年中报亏损及再融资稀释，不把题材标签当基本面确认。

2. 龙建股份600853——基建/冰雪经济放量试板后的承接。参考价3.59，涨7.16%，成交3.44亿元，换手9.42%，RVOL5/10/20=2.08/3.51/5.42，CLV0.730，距MA20+8.0%，压力3.69/3.78。10月19日仅在开盘3.48—3.66、回踩3.43—3.52缩量守住后重新站3.60，且地产/基建或冰雪方向有至少两只同向强势股时观察。高开3.75以上不追；跌破3.32、冲击3.69—3.78放量回落或板块孤立均放弃。若触发最早10月20日退出，弱开失守3.32优先退出，强势观察3.69、3.78。风险：10月16日曾触板后未封、可转债转股与题材持续性不足。

主要替代：润本股份因10月19日大额限售股上市流通排除；誉衡药业因高换手、长上影及减持风险排除；中复神鹰因20%制度、尾盘回落和定增稀释风险排除；航天晨光、中鼎股份等收盘封板样本无法证明10月19日普通可买，未升级。

五、10月19日指数情景冻结（无概率）

上行：上证站上3750.77并维持30分钟，红盘家数>3500，沪深同时点成交不显著低于10月16日，炸板率收敛；失效为跌回3720且红盘不足2000。

震荡：上证主要运行于3681.28—3750.77，红盘约2000—3500，成交温和缩量，板块轮动但无持续扩散；任一边界有效突破30分钟则震荡情景失效。

下行：跌破3681.28后30分钟不能收回，下跌家数>3500且成交同比放大；失效为重新站回3716并且红盘超过2800、跌停和炸板同步收敛。

六、发现与下一项可证伪假设

10月15日H1的两只前推样本均未触发，样本数仍为0，不能验证“低乖离+高CLV”优势；恩捷还提供了“先回踩后不收复”的失败反例。新冻结H2：在修复但冲高回落的市场中，RVOL20>4、距MA20<10%、CLV 0.65—0.80且未封板的样本，只有次日回踩后重新站回关键位才可能改善T+1退出；安达维尔与龙建股份作为前推样本，冰山冷热/慈文传媒为高乖离对照，润本股份为事件风险反例。后续只追加触发、失效、MFE/MAE及10月20日最早合法退出，不回改今天条件。

术语：CLV=(收盘-最低)/(最高-最低)，越接近1表示收盘越靠近全天高位；RVOL20为当日成交量相对之前20个完成交易日平均量；MFE/MAE分别是相对冻结参考的最大有利/不利价格波动。事实、推断和假设已分开，本研究不保证收益。"""

    report = {
        "id": REPORT_ID, "date": "2026-10-16", "task_id": "market_review", "track": "market_review",
        "run_id": RUN_ID, "report_type": "full_daily_research", "eligible_for_integrated_research": True,
        "published_at": completed_at, "recorded_at": completed_at, "data_cutoff_at": "2026-10-16T15:35:45+08:00",
        "title": "2026-10-16 A股收盘复盘、全池T+1验证与10月19日条件观察",
        "summary": "全A有效扫描5570只、广泛池120只、深筛28只；市场修复但冲高回落，上一池28只平均收盘-1.83%。本研究组冻结安达维尔、龙建股份两只10月19日条件观察。",
        "body": body, "sources": source_urls, "research_version": "market_review_close_v5",
        "volume_price_version": "volume_price_close_v3", "market_date": "2026-10-16",
        "broad_pool_count": 120, "deep_pool_count": 28,
        "previous_pool_status": "2026-10-15 full pool verified on 2026-10-16",
        "previous_pool_verified_count": 28, "facts_hypotheses_separated": True,
        "codes": [x["code"] for x in evidence["deep_pool"]],
        "provenance": "contemporaneous_close_research",
        "integrated_prerequisite_policy": "market_review+volume_price+low_position+dragon_tiger; quant_research cancelled",
    }
    research = load("research.json")
    if not any(x["id"] == REPORT_ID for x in research["items"]):
        research["items"].append(report)

    recommendations = load("recommendations.json")
    prior_by_id = {x["id"]: x for x in recommendations["items"]}
    prior_results = {
        "market-review-20261015-000973-close-v1": {
            "id":"market-review-20261015-000973-close-v1-trigger-result-20261016", "as_of":"2026-10-16T15:00:00+08:00",
            "recorded_at":completed_at, "market_date":"2026-10-16", "horizon":"planned entry day trigger verification",
            "status":"not_triggered", "trigger_status":"support_reached_but_reclaim_absent", "entry_fill_status":"no_fill",
            "executed_trade":False, "strategy_sample_activated":False, "observed_open":11.99, "observed_high":12.05,
            "observed_low":11.79, "observed_close":11.96, "executable_net_return_pct":None,
            "source":"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=sz000973", "report_id":REPORT_ID,
            "note":"09:45触及11.80，但全天未站上冻结的12.20，保留未触发样本。",
        },
        "market-review-20261015-002812-close-v1": {
            "id":"market-review-20261015-002812-close-v1-trigger-result-20261016", "as_of":"2026-10-16T15:00:00+08:00",
            "recorded_at":completed_at, "market_date":"2026-10-16", "horizon":"planned entry day trigger verification",
            "status":"not_triggered_invalidated", "trigger_status":"pullback_without_reclaim_then_invalidated", "entry_fill_status":"no_fill",
            "executed_trade":False, "strategy_sample_activated":False, "observed_open":48.99, "observed_high":49.35,
            "observed_low":45.71, "observed_close":46.26, "executable_net_return_pct":None,
            "source":"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=sz002812", "report_id":REPORT_ID,
            "note":"09:31回踩47.88后未收复48.60，随后跌破46.35；顺序不满足，不能用开盘价倒推成交。",
        },
        "market-review-20261014-600316-close-v1": {
            "id":"market-review-20261014-600316-close-v1-exit-observation-20261016", "as_of":"2026-10-16T15:00:00+08:00",
            "recorded_at":completed_at, "market_date":"2026-10-16", "horizon":"T+1 earliest legal exit observation",
            "status":"exit_levels_observed_split_weight_unfrozen", "executed_trade":False, "strategy_sample_activated":True,
            "observed_open":35.12, "observed_high":38.61, "observed_low":35.12, "observed_close":37.66,
            "simulated_reference_entry":35.85, "first_36_20_observed_at":"2026-10-16T09:41:00+08:00",
            "first_37_50_observed_at":"2026-10-16T09:51:00+08:00", "executable_net_return_pct":None,
            "source":"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=sh600316", "report_id":REPORT_ID,
            "note":"两个冻结观察位均出现，但原计划未冻结分批权重，故不事后制造单一净收益；退出质量良好。",
        },
    }
    for rid, result in prior_results.items():
        if rid in prior_by_id and not any(x.get("id") == result["id"] for x in prior_by_id[rid].setdefault("results", [])):
            prior_by_id[rid]["results"].append(result)

    new_recs = [
        {"id":"market-review-20261016-300719-close-v1", "date":"2026-10-16", "published_at":completed_at,
         "group":"close", "strategy":"market_review_conditional", "task_id":"market_review", "provenance":"contemporaneous_close_research",
         "data_cutoff_at":"2026-10-16T15:35:45+08:00", "planned_entry_date":"2026-10-19",
         "earliest_legal_exit_date_if_bought":"2026-10-20", "current_stage":"frozen_conditional_observation",
         "report_ids":[REPORT_ID], "sources":source_urls, "roundtrip_cost_assumption_bps":20, "results":[],
         "code":"300719", "name":"安达维尔", "model":"first_divergence_sector_resonance_v5",
         "reason":"收12.40，换手10.83%，RVOL20 6.10，CLV0.721，距MA20 +4.2%；军工/低空共振，但尾盘-0.96%、中报亏损且有再融资风险。",
         "reference_price":12.40, "reference_price_time":"2026-10-16T15:00:00+08:00",
         "reference_price_market_date":"2026-10-16", "reference_price_source":"https://qt.gtimg.cn/q=sz300719",
         "reference_entry_range":[11.75,12.45], "operational_invalid_price":11.55,
         "trigger":"10月19日开盘11.95—12.60；回踩11.75—12.05缩量守住后重新站12.45，且军工/低空经济非一字核心未批量转弱。",
         "invalid":"高开12.90以上不追；跌破11.55、12.79附近放量不进或板块高标跌停均放弃。",
         "exit_plan":"若10月19日真实触发，最早10月20日卖；弱开失守11.55优先退出，强势观察12.79、13.08。"},
        {"id":"market-review-20261016-600853-close-v1", "date":"2026-10-16", "published_at":completed_at,
         "group":"close", "strategy":"market_review_conditional", "task_id":"market_review", "provenance":"contemporaneous_close_research",
         "data_cutoff_at":"2026-10-16T15:35:45+08:00", "planned_entry_date":"2026-10-19",
         "earliest_legal_exit_date_if_bought":"2026-10-20", "current_stage":"frozen_conditional_observation",
         "report_ids":[REPORT_ID], "sources":source_urls, "roundtrip_cost_assumption_bps":20, "results":[],
         "code":"600853", "name":"龙建股份", "model":"failed_board_reclaim_infrastructure_v5",
         "reason":"收3.59，换手9.42%，RVOL20 5.42，CLV0.730，距MA20 +8.0%；曾触板未封，需次日回踩后重新站稳验证。",
         "reference_price":3.59, "reference_price_time":"2026-10-16T15:00:00+08:00",
         "reference_price_market_date":"2026-10-16", "reference_price_source":"https://qt.gtimg.cn/q=sh600853",
         "reference_entry_range":[3.43,3.60], "operational_invalid_price":3.32,
         "trigger":"10月19日开盘3.48—3.66；回踩3.43—3.52缩量守住后重新站3.60，且地产/基建或冰雪方向至少两只同向强势。",
         "invalid":"高开3.75以上不追；跌破3.32、3.69—3.78放量回落或板块孤立均放弃。",
         "exit_plan":"若10月19日真实触发，最早10月20日卖；弱开失守3.32优先退出，强势观察3.69、3.78。"},
    ]
    existing = {x["id"] for x in recommendations["items"]}
    recommendations["items"].extend(x for x in new_recs if x["id"] not in existing)

    task_runs = load("task_runs.json")
    receipt_id = RUN_ID + "-completed"
    receipt = {
        "id":receipt_id, "run_id":RUN_ID, "task_id":"market_review", "date":"2026-10-16", "trigger":"scheduled",
        "started_at":"2026-10-16T08:39:30+00:00", "recorded_at":now_utc.isoformat(timespec="seconds"),
        "completed_at":now_utc.isoformat(timespec="seconds"), "status":"completed",
        "summary":"完成10月16日全A有效5570只扫描、120只广泛池、28只深筛、上一池28只T+1价格验证、两只条件观察与10月19日指数三情景冻结。",
        "report_ids":[REPORT_ID], "recommendation_ids":[x["id"] for x in new_recs],
        "research_rule_version":"market_review_close_v5", "analysis_completed":True,
        "delivery_status":"repository_pending", "sources":source_urls,
    }
    if not any(x["id"] == receipt_id for x in task_runs["items"]):
        task_runs["items"].append(receipt)

    save("research.json", research)
    save("recommendations.json", recommendations)
    save("task_runs.json", task_runs)
    print(json.dumps({"report":REPORT_ID,"recommendations":[x["id"] for x in new_recs],"receipt":receipt_id,"completed_at":completed_at},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
