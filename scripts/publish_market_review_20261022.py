#!/usr/bin/env python3
"""Publish the complete 2026-10-22 market review and immutable receipts."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backend" / "data"
EVIDENCE_PATH = ROOT / "docs" / "research" / "market-review-2026-10-22-evidence.json"
REPORT_ID = "market-review-20261022-close-v1"
RUN_ID = "market-review-20261022-scheduled-close-v1"
RECOMMENDATION_ID = "market-review-20261022-002520-close-v1"

SECTOR = {
    "002076": "LED/机器人", "600202": "工业制冷/能源装备", "603330": "胶粘材料/光伏",
    "000530": "冷链设备/机器人", "002307": "基建/新疆", "603138": "数据库/软件",
    "603370": "电机铁芯/新能源", "002724": "特种照明/机器人", "600838": "商业零售",
    "000576": "军工电子", "002593": "汽车车轮/钢结构", "603089": "汽车零部件",
    "601999": "出版传媒", "601091": "能源装备/次新", "002520": "机床/智能制造",
    "002097": "工程机械/机器人", "002249": "电机/氢能", "300045": "卫星导航/军工",
    "603728": "电机/机器人", "600698": "汽车零部件/军工", "301622": "稀土磁材/机器人",
    "301666": "存储芯片", "605488": "胶粘材料/机器人", "603278": "工业材料/机器人",
    "688500": "数据服务/AI", "000678": "汽车轴承/机器人", "603280": "工程机械",
    "002877": "工业控制",
}


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def save(name: str, value):
    (DATA / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt(value):
    return "N/A" if value is None else f"{value:+.2f}%"


def main():
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    now_utc = dt.datetime.now(dt.timezone.utc)
    now_cn = now_utc.astimezone(dt.timezone(dt.timedelta(hours=8)))
    recorded_at = now_utc.isoformat(timespec="seconds")
    completed_at = now_cn.isoformat(timespec="seconds")

    sources = [
        "https://finance.eastmoney.com/a/202610223904049940.html",
        "https://www.cls.cn/detail/2511964",
        "https://www.cls.cn/detail/2512173",
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData",
        "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData",
        "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688",
        "https://82.push2.eastmoney.com/api/qt/clist/get",
        "https://www.cninfo.com.cn/new/disclosure/stock?stockCode=002520",
        "docs/research/market-review-2026-10-22-evidence.json",
    ]

    table_rows = []
    for x in evidence["deep_pool"]:
        table_rows.append(
            f"|{x['code']} {x['name']}|{SECTOR[x['code']]}|{number(x['trade']):.2f}/{number(x['changepercent']):+.2f}%|"
            f"{number(x['turnoverratio']):.1f}%|{number(x.get('rvol5')):.2f}/{number(x.get('rvol10')):.2f}/{number(x.get('rvol20')):.2f}|"
            f"{number(x.get('clv')):.3f}|{fmt(x.get('dist_ma20'))}|{fmt(x.get('tail_1400_close_pct'))}|"
            f"{'封板/普通成交可买性待验' if number(x['changepercent']) >= 9.5 else '放量异动/次日承接待验'}|"
        )
    table = "\n".join(table_rows)
    previous = evidence["previous_partial_pool_summary"]

    body = f"""交易日T=2026-10-22，行情事实截止当日16:30:00+08:00；报告实际完成时间{completed_at}。这是market_review独立完整研究，不替代volume_price、low_position、dragon_tiger；quant_research已取消。APP只展示归档与统计，不内置大模型或自动训练权重。

一、市场复盘（事实）

上证3658.03（-1.48%，日内3649.86—3714.48）、深成指11357.32（-2.96%）、创业板2576.90（-4.37%，收在日内低位）、科创50 1305.87（-2.78%）。沪深京公开口径成交约1.54万亿元，较10月21日放量约1000亿元；本地Sina全A有效股票汇总1.541万亿元，两个口径不混用。

全A原始5576只、有效5571只：535涨、4998跌、38平。公开收评确认仅500余股上涨、逾30股涨停；本地可复算的非ST普通主板代理口径为30只封板、65只触板、35只触板未封、58只跌停，代理炸板率35/65=53.8%。该代理不含ST、20%/30%制度和上市初期无上限股票，不能冒充全市场官方总数。

医疗美容、机器人、工程机械逆势；电机行业涨4.13%，机器人行业约涨0.48%。影视院线、广告营销、传媒、电子元件、教育、互联网电商、游戏及算力硬件显著偏弱。高位可见为海洋王、大业股份5连板；财联社收盘分析称连板晋级率跌破三成。盘面是风险扩散中的高标抱团，不是普遍修复。前日4板晋级至5板并不抵消4998家下跌与58只代理跌停。

情绪阶段：退潮/风险释放。支持证据是指数和宽度同步恶化、成交放量但价格下行、代理炸板和跌停扩张；反证是机器人、电机和工程机械仍有局部持续性。下一交易日最值得观察：①上证能否重新站回3700、创业板能否收复2625；②代理跌停能否从58降到30以下且上涨家数恢复至2000以上；③海洋王、大业股份5板反馈及机器人非一字换手核心是否继续承接，若高标补跌则局部抱团也可能瓦解。

二、全市场筛选、28只深研与重复说明

本轮实际有效覆盖5571只，建立120只可复核广泛池并深筛28只，覆盖机器人、电机、工程机械、军工、软件、芯片、传媒、消费、材料、基建、汽车与能源装备等至少12个方向。关注、持仓和用户问过的股票没有自动进入候选。

|代码/名称|板块|收盘/涨跌|换手|RVOL5/10/20|CLV|距MA20|14点后|结构|
|---|---|---:|---:|---|---:|---:|---:|---|
{table}

量价支持主要集中在极少数逆势方向：日发精机002520收6.10、涨7.77%、换手14.67%，RVOL20=4.36、CLV=0.768、距MA20仅+1.09%；英思特301622收35.62、涨8.04%、RVOL20=4.52、距MA20+1.32%，但属于20%制度高波动品种。反例包括冰山冷热距MA20约+59.7%、大业股份+45.1%、海洋王+50.1%，均为高乖离；星光股份等封板对象无法证明下一交易日普通成交可执行性；智能自控14点后约-3.91%，量大但价格推进失败。

严格过去5/10交易日重复率仍不能完整计算：10月21日没有合格的20—30只冻结深筛，10月14—20若干旧报告现被审计为evidence_only，不能拿其局部代码反推完整池。当前池中的星光股份、冰山冷热、海洋王、大业股份、福莱新材等属于公开高活跃方向重复出现；保留是因为同日全市场排序仍靠前，并非为降低重复率机械换股。

三、上一批验证与T+1可执行性

10月21日没有合格完整market_review，只有blocked_partial来源池，不能冒充冻结策略样本。本轮仍将其121个唯一代码全部纳入补证：119只取得10月22日日线，2只北交所代码缺同源数据；平均开盘{previous['average_open_pct']:+.3f}%、平均收盘{previous['average_close_pct']:+.3f}%、中位收盘{previous['median_close_pct']:+.3f}%，平均MFE {previous['average_mfe_pct']:+.3f}%、平均MAE {previous['average_mae_pct']:+.3f}%；仅{previous['positive_close_count']}/119收涨，{previous['mae_le_minus5_count']}/119的MAE不高于-5%。这些只是局部来源池的全量价格观察，不进入策略胜率。

上一次完整冻结的10月20日两只本组条件样本继续保留失败/未验证结果：全志科技300458在10月21日最低28.56，未进入冻结回踩区27.45—28.05，明确未触发、无成交；10月22日收28.26，较21日收盘-2.38%、较20日参考-1.33%。阿尔特300825在21日开11.28、低11.18、高12.12、收11.80，日线触及回踩区且高于重站位，但缺分钟先后与板块同步证据，只能记not_verified/no_fill；22日收10.92，较21日-7.46%、较20日参考-5.21%。不能从日高倒推买卖或策略盈利。

四、10月23日唯一条件观察（不是综合双标）

日发精机002520，参考价6.10元，模型为“极端弱市中的近MA20放量承接”。相较英思特，它是普通主板10%制度、距MA20更近；相较星光股份、海洋王、大业股份，它没有封板排队和巨大正乖离。但14点后回落约1.13%、当天高点6.23未能收复，且公司限制性股票激励、估值和股权质押等公开风险不能忽视，因此只保留严格条件样本。

计划交易日D=2026-10-23。只有同时满足以下条件才进入模拟观察：开盘5.80—6.15；09:45—10:30先回踩5.76—5.92且不破5.72，再放量重新站上6.05并在6.02—6.12出现普通成交；同口径上涨家数不少于2000、普通非ST主板代理跌停少于30，机器人/机床方向至少两只非一字核心不低于-2%。高开6.18以上不追，开盘前新增重大风险、先破5.72、10:30前未完成顺序或板块条件缺证，直接放弃。初始失效5.65；压力6.23/6.50。

若10月23日真实买入，A股T+1最早2026-10-26卖出。弱开或跌破5.65，在10月26日首个可证明可成交的时点退出；若延续强势，50%在首个可成交时点处理，25%观察6.23、25%观察6.50，余仓不晚于10:30首个可成交时点。跌停无买盘或停牌必须保留未退出风险。20bp成本仅是未校准占位，不在没有真实成交、数量、费用和滑点时计算净收益。

至少三只替代否决：英思特虽近MA20且放量，但20%制度、当日振幅11.6%使T+1隔夜尾部更大；华力创通距MA20约+20.2%、换手21.4%，不是低位首次启动；智能自控14点后明显回落，量价背离；所有封板对象还存在无法普通成交风险。本组不凑第二只。

五、10月23日指数情景冻结（无概率）

上行/修复：上证重新站上3700并保持30分钟、创业板站上2625，上涨家数>2500，全天成交节奏不低于约1.45万亿元，代理跌停降至30以下，机器人/电机不只高标抱团。失效为上证再破3675、创业板失守2600且上涨不足1500。

震荡/弱反抽：上证主要运行3649.86—3714.48、创业板2576.90—2688.11，成交约1.40—1.65万亿元，上涨家数1000—2500，热点轮动但没有多板块扩散。任一指数有效越界并同时满足上行或下行宽度条件，则震荡情景失效。

下行/风险继续扩散：上证跌破3649.86或创业板跌破2576.90后30分钟不能收回，上涨家数<800、下跌家数>4700，成交放大且代理跌停高于60。失效为上证重新站回3675、创业板站回2625且上涨超过2200、跌停明显收缩。

六、量价发现与待验证假设

本次最重要发现不是“强者恒强”，而是放量下跌环境中封板强度与全市场T+1退出环境明显背离。冻结H5：在上涨不足800家的极弱日，距MA20不高于+3%、RVOL20>3、CLV>0.70且未封板的少数逆势样本，只有次日市场宽度和板块同步先修复，再完成缩量回踩—重新站回关键位，才可能比高乖离封板组拥有更好的T+1退出质量。日发精机是前推样本；英思特为20%制度对照；冰山冷热、大业股份和海洋王为高乖离封板对照。后续只追加结果，不改今日门槛。

术语：CLV=(收盘-最低)/(最高-最低)，越接近1表示收盘越靠近全天高位；RVOL20为当日成交量相对前20个完成交易日均量；MFE/MAE分别为冻结参考后的最大有利/不利价格波动。事实、推断和假设已分开，本研究不保证收益。"""

    report = {
        "id": REPORT_ID, "date": "2026-10-22", "track": "market_review", "task_id": "market_review",
        "run_id": RUN_ID, "report_type": "full_trading_research", "eligible_for_integrated_research": True,
        "status": "completed", "published_at": completed_at, "recorded_at": completed_at,
        "data_cutoff_at": "2026-10-22T16:30:00+08:00", "market_date": "2026-10-22",
        "title": "2026-10-22 A股收盘复盘、全池风险验证与10月23日唯一条件观察",
        "summary": "全A有效5571只、广泛池120只、深筛28只；535涨4998跌，市场处于风险扩散。补证前日局部池121个代码并仅冻结日发精机一只严格条件观察。",
        "body": body, "sources": sources, "research_version": "market_review_close_v8",
        "volume_price_version": "volume_price_close_v4", "broad_pool_count": 120, "deep_pool_count": 28,
        "previous_pool_verified_count": previous["verified"], "facts_hypotheses_separated": True,
        "codes": [x["code"] for x in evidence["deep_pool"]], "provenance": "contemporaneous_close_research",
        "integrated_prerequisite_policy": "market_review+volume_price+low_position+dragon_tiger; quant_research cancelled",
    }

    research = load("research.json")
    if not any(x["id"] == REPORT_ID for x in research["items"]):
        research["items"].append(report)

    recommendations = load("recommendations.json")
    by_id = {x["id"]: x for x in recommendations["items"]}
    followups = {
        "market-review-20261020-300458-close-v1": {
            "id": "market-review-20261020-300458-close-v1-followup-20261022", "as_of": "2026-10-22T15:00:00+08:00",
            "recorded_at": completed_at, "market_date": "2026-10-22", "horizon": "second-session price follow-up",
            "observation_type": "price_observation", "status": "no_trade_followup", "executed_trade": False,
            "strategy_sample_activated": False, "observed_open": 28.70, "observed_high": 29.44,
            "observed_low": 28.25, "observed_close": 28.26, "close_vs_previous_pct": -2.3834,
            "close_vs_original_reference_pct": -1.3268, "executable_net_return_pct": None,
            "source": "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol=sz300458&scale=240&ma=no&datalen=10",
            "report_id": REPORT_ID, "note": "10月21日原条件明确未触发、无成交；本条只追加价格观察。",
        },
        "market-review-20261020-300825-close-v1": {
            "id": "market-review-20261020-300825-close-v1-trigger-and-followup-20261022", "as_of": "2026-10-22T15:00:00+08:00",
            "recorded_at": completed_at, "market_date": "2026-10-22", "horizon": "entry-day verification and second-session follow-up",
            "observation_type": "price_observation", "status": "not_verified", "trigger_status": "daily_range_met_but_intraday_sequence_and_sector_confirmation_missing",
            "entry_fill_status": "no_fill", "executed_trade": False, "strategy_sample_activated": False,
            "entry_day_20261021": {"open": 11.28, "high": 12.12, "low": 11.18, "close": 11.80},
            "observed_open": 11.80, "observed_high": 12.11, "observed_low": 10.90, "observed_close": 10.92,
            "close_vs_previous_pct": -7.4576, "close_vs_original_reference_pct": -5.2083,
            "executable_net_return_pct": None,
            "source": "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol=sz300825&scale=240&ma=no&datalen=10",
            "report_id": REPORT_ID, "note": "10月21日日线触及回踩区且高于重站位，但缺分钟先后、板块同步和成交证据；保守记未验证、无成交。",
        },
    }
    for rec_id, result in followups.items():
        if rec_id in by_id and not any(x.get("id") == result["id"] for x in by_id[rec_id].setdefault("results", [])):
            by_id[rec_id]["results"].append(result)

    new_rec = {
        "id": RECOMMENDATION_ID, "date": "2026-10-22", "published_at": completed_at,
        "group": "close", "strategy": "market_review_conditional", "task_id": "market_review",
        "provenance": "contemporaneous_close_research", "data_cutoff_at": "2026-10-22T16:30:00+08:00",
        "planned_entry_date": "2026-10-23", "earliest_legal_exit_date_if_bought": "2026-10-26",
        "current_stage": "frozen_conditional_observation", "report_ids": [REPORT_ID], "sources": sources,
        "roundtrip_cost_assumption_bps": 20, "results": [], "code": "002520", "name": "日发精机",
        "model": "weak_market_near_ma20_reclaim_v8",
        "reason": "收6.10、涨7.77%、换手14.67%，RVOL20 4.36、CLV0.768、距MA20约+1.09%；极弱市场中的近均线放量样本，但尾盘回落，须次日市场及板块先修复。",
        "reference_price": 6.10, "reference_price_time": "2026-10-22T15:00:00+08:00",
        "reference_price_market_date": "2026-10-22",
        "reference_price_source": "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData",
        "reference_entry_range": [6.02, 6.12], "operational_invalid_price": 5.65,
        "trigger": "10月23日开盘5.80—6.15；09:45—10:30先回踩5.76—5.92且不破5.72，再放量站上6.05并在6.02—6.12普通成交；上涨家数≥2000、代理跌停<30，机器人/机床至少两只非一字核心≥-2%。",
        "invalid": "高开6.18以上不追；先破5.72、10:30前未完成顺序、板块/宽度不符或新增重大风险均放弃；初始失效5.65。",
        "exit_plan": "若10月23日真实触发，最早10月26日卖；弱开或破5.65首个可成交退出，强势观察6.23/6.50，余仓不晚于10:30处理。",
    }
    if RECOMMENDATION_ID not in by_id:
        recommendations["items"].append(new_rec)

    task_runs = load("task_runs.json")
    receipt_id = RUN_ID + "-completed"
    receipt = {
        "id": receipt_id, "run_id": RUN_ID, "task_id": "market_review", "date": "2026-10-22",
        "trigger": "scheduled", "started_at": "2026-10-22T08:42:33+00:00",
        "recorded_at": recorded_at, "completed_at": recorded_at, "status": "completed",
        "summary": "完成10月22日全A有效5571只扫描、120只广泛池、28只深筛、前日局部池119只有效补证、唯一条件观察及10月23日指数三情景冻结。",
        "report_ids": [REPORT_ID], "recommendation_ids": [RECOMMENDATION_ID],
        "research_rule_version": "market_review_close_v8", "analysis_completed": True,
        "delivery_status": "repository_pending", "sources": sources,
    }
    if not any(x["id"] == receipt_id for x in task_runs["items"]):
        task_runs["items"].append(receipt)

    save("research.json", research)
    save("recommendations.json", recommendations)
    save("task_runs.json", task_runs)
    print(json.dumps({"report": REPORT_ID, "recommendation": RECOMMENDATION_ID,
                      "receipt": receipt_id, "completed_at": completed_at}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
