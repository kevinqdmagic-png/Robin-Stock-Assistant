#!/usr/bin/env python3
"""Append the complete 2026-10-29 market review and truthful receipt."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
T = "2026-10-29"
D = "2026-10-30"
EXIT = "2026-11-02"
REPORT_ID = "market-review-20261029-close-v1"
RUN_ID = "market-review-20261029-scheduled-close-v1"
EVIDENCE = "docs/research/market-review-2026-10-29-evidence.json"

SECTORS = {
    "002708": "汽车零部件/机器人", "002943": "工业设备/机器人", "600715": "传媒",
    "603382": "化纤材料", "603131": "焊接设备/商业航天", "600643": "多元金融",
    "000530": "制冷设备", "002275": "中药", "603279": "过滤设备",
    "300900": "航空航天", "002086": "水产/医药", "600728": "智慧交通/软件",
    "600576": "文旅", "301005": "汽车零部件/商业航天", "002149": "特种材料",
    "002277": "零售", "300102": "光电", "601188": "交通运输",
    "002865": "光伏", "600118": "卫星/商业航天", "001379": "紧固件/商业航天",
    "300780": "工业机械", "688386": "膜材料", "603667": "轴承/机器人",
    "605179": "乳品", "002172": "医药健康", "600501": "航天装备",
    "603703": "通信设备/商业航天",
}


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def save(path, value):
    (ROOT / path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def table(headers, rows):
    return "|" + "|".join(headers) + "|\n|" + "|".join(["---"] * len(headers)) + "|\n" + "\n".join("|" + "|".join(str(v) for v in row) + "|" for row in rows)


def main():
    research = load("backend/data/research.json")
    runs = load("backend/data/task_runs.json")
    evidence = load(EVIDENCE)
    if any(x.get("id") == REPORT_ID for x in research["items"]):
        print("already published")
        return

    now = datetime.now(timezone.utc)
    stamp_utc = now.isoformat(timespec="seconds")
    stamp_cn = now.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    deep = evidence["deep_pool"]
    prior = evidence["previous_pool_validation"]
    stats = evidence["previous_pool_statistics"]
    market = evidence["market"]
    indices = {x["name"]: x for x in evidence["index_quotes"]["items"]}
    current = {x["code"] for x in deep}
    earlier = [x for x in research["items"] if x.get("task_id") == "market_review" and x.get("date") < T and x.get("eligible_for_integrated_research") is True and x.get("codes")]
    earlier.sort(key=lambda x: x["date"], reverse=True)
    available5, available10 = earlier[:5], earlier[:10]
    union5 = set().union(*(set(x["codes"]) for x in available5)) if available5 else set()
    union10 = set().union(*(set(x["codes"]) for x in available10)) if available10 else set()
    repeat5 = round(len(current & union5) / len(current) * 100, 2)
    repeat10 = round(len(current & union10) / len(current) * 100, 2)

    deep_rows = [[
        f"{x['code']} {x['name']}", SECTORS.get(x["code"], "待细分"), x["trade"], f"{float(x['changepercent']):+.2f}%",
        f"{x['rvol5']:.2f}/{x['rvol10']:.2f}/{x['rvol20']:.2f}", f"{float(x['turnoverratio']):.2f}%",
        f"{x['dist_ma20']:+.2f}%", f"{x['clv']:.3f}", f"{x.get('tail_1400_close_pct', 0):+.2f}%",
    ] for x in deep]
    prior_rows = [[f"{x['code']} {x['name']}", f"{x['open_pct']:+.3f}%", f"{x['mfe_pct']:+.3f}%", f"{x['mae_pct']:+.3f}%", f"{x['close_pct']:+.3f}%"] for x in prior]
    worst = sorted(prior, key=lambda x: x["close_pct"])[:5]
    best = sorted(prior, key=lambda x: x["close_pct"], reverse=True)[:5]

    body = f"""研究交易日T={T}，行情截止北京时间15:00；实际完成时间{stamp_cn}。全A扫描与判断只使用T及此前公开信息。计划观察日D={D}；若D真实买入，A股T+1下最早{EXIT}卖出。本报告是market_review独立完整研究，不是四模块综合裁决。

一、市场复盘与10月28日情景核验

上证{indices['上证指数']['close']:.2f}（{indices['上证指数']['change_pct']:+.2f}%）、深证成指{indices['深证成指']['close']:.2f}（{indices['深证成指']['change_pct']:+.2f}%）、创业板{indices['创业板指']['close']:.2f}（{indices['创业板指']['change_pct']:+.2f}%）、科创50 {indices['科创50']['close']:.2f}（{indices['科创50']['change_pct']:+.2f}%）。独立全A扫描{evidence['coverage']['full_scan']}只有效股票：{market['advance']}涨、{market['decline']}跌、{market['flat']}平，成交额约{market['amount_yuan_full_scan']/1e8:.2f}亿元。普通非ST主板代理口径：{market['standard_non_st_limit_up_sealed']}只封板、{market['standard_non_st_limit_up_touched']}只触板、{market['standard_non_st_failed_boards']}只触板未封、{market['standard_non_st_limit_down']}只跌停。

东方财富收盘口径为沪深京三市约1.57万亿元、较前日缩量713亿元；行业以航天装备、核电、风电、银行相对强，元件、半导体、通信设备、机器人、消费电子相对弱。看盘吧口径为40只涨停、23只炸板、封板率63%，最高青岛食品和光洋股份4板；1进2为7/57、2进3为3/5、高位晋级2/3。媒体全市场口径与本档普通非ST主板代理口径分别保存，不混算。

10月28日冻结的上行情景完整失效：三个指数均未突破阈值，宽度仅781只上涨。震荡情景也失效：深成指和创业板跌破下沿，下跌家数远超区间。下行情景出现大部分触发证据——上证盘中跌破3650、深成指低于11290、创业板低于2560、下跌4727只；但上证收盘回到3650上方，且本档没有连续30分钟低于3650的分钟证据，所以只记“下行情景部分触发、收盘未完成确认”，不事后改判完整命中。

市场判断：10月28日的放量普涨修复次日即转为成长方向集中退潮。成交仍高但较前日缩量，创业板与科创50跌幅显著大于上证，银行和航天对指数的支撑不能抵消4727只下跌。情绪从修复重新进入强分歧/退潮；最高板从5板降至4板，前高标襄阳轴承炸板，说明主线切换和接力风险同时上升。

下一交易日重点信号：①上证能否重新站上3680并带动创业板收复2560；②商业航天逆势强度能否扩散到非涨停股，而非只剩少数封板；③机器人、半导体和通信设备是否出现止跌承接，跌停与炸板是否继续扩散。

二、全A覆盖与深筛28只

全A{evidence['coverage']['full_scan']}只→广泛池120只→深筛28只，覆盖商业航天、机器人、汽车零部件、机械、材料、传媒、金融、制冷、医药、文旅、光伏、交通、零售、乳品等至少十四组。RVOL5/10/20=当日完整成交量/此前5/10/20个已完成交易日均量；CLV=(收盘-最低)/(最高-最低)，只表示收盘位置；距MA20使用此前20日均线。六个时点是离散价格观察，不能证明触发顺序或成交。

{table(['代码/名称','板块','收盘','涨跌','RVOL5/10/20','换手','距MA20','CLV','14时后'], deep_rows)}

三、10月28日完整深筛池28/28验证

原始冻结报告market-review-20261028-close-v1的28只全部取得10月29日日线：{stats['positive_close_count']}只收红，收盘观察均值{stats['mean_close_pct']:+.3f}%、中位{stats['median_close_pct']:+.3f}%，高点观察均值{stats['mean_mfe_pct']:+.3f}%、低点观察均值{stats['mean_mae_pct']:+.3f}%，{stats['mae_le_minus5_count']}只盘中不利幅度达到或超过5%。最弱为{', '.join(x['code']+' '+x['name']+f" {x['close_pct']:+.2f}%" for x in worst)}；最强为{', '.join(x['code']+' '+x['name']+f" {x['close_pct']:+.2f}%" for x in best)}。

{table(['代码/名称','开盘观察','MFE','MAE','收盘观察'], prior_rows)}

这些变化以10月28日收盘为观察基准，不是10月29日买入收益。原报告正式推荐为0，真实成交N=0；缺分钟触发、9:50/14:40成交和费用，不能计算可执行净收益、胜率或盈亏比。前池仅6只收红、收盘中位-3.011%，证伪了“普涨修复后的高弹性可直接延续”这一未经验证的直觉；同时平均MFE仍+4.161%，说明日内冲高不能替代T+1可执行退出。

四、量价发现、反例与双轨筛选

相对强样本集中在航天与少数事件线：600118中国卫星封板、300900广联航空涨9.53%且CLV接近高位、600501航天晨光封板；它们与航天装备板块逆势相符。603279景津装备、600728佳都科技、301005超捷股份虽大幅上涨，但14时后分别回落，不能把盘中推进直接认定为分歧转一致。002275桂林三金RVOL20约14.89且封板，超常成交只说明交换充分，需次日验证价格能否继续推进；603667五洲新春、688386泛亚微透等虽收涨，也处在成长退潮的大环境中。

风险结构更突出：全市场仅781只上涨，机器人、半导体、通信设备和消费电子显著回落；前日深池28只仅6只收红。大量新深筛对象本身已涨停或接近涨停，盘后无法证明D日普通可得性，且弱市中高开回落风险较高。

正式新增交易观察标的0只：没有把航天板块逆势涨停直接写成次日买入卡。研究影子轨仅冻结600118中国卫星与300900广联航空作为H3“逆势板块强度是否优于绝对涨幅”的前推对照，不写入正式recommendations。D日若竞价高于+5%、航天板块开盘30分钟强度转负、个股跌破T日14:00价格或高开后放量不能推进，研究观察失效；即使触发也不是实盘指令。被替代候选包括600501航天晨光（封板可得性不足）、603131上海沪工（机器人与航天双标签但已二板）、001379腾达科技（14时后回落且高波动）。

当前28只对最近{len(available5)}个可得完整报告池代码并集重复率{repeat5:.2f}%，对最近{len(available10)}个可得完整报告池并集重复率{repeat10:.2f}%。缺完整池的交易日不作0填充，因此严格5/10交易日重复率仍记N/A；正式推荐为0，推荐重复率N/A。

五、10月30日指数三情景（事前冻结，不给概率）

- 上行：上证重新站上3680并至少保持30分钟，深成指收复11290、创业板收复2560；上涨家数超过3200且成交不低于1.55万亿元，机器人/半导体止跌并且炸板率下降。任一成长指数跌回今日收盘下方且上涨家数不足2200，情景失效。
- 震荡：上证3625—3680、深成指10950—11290、创业板2450—2560内运行；上涨家数约1500—3200、成交约1.35—1.60万亿元，商业航天分化但跌停不继续扩散。放量突破上沿或跌破下沿使情景失效。
- 下行：上证跌破3625并30分钟不能收回，同时深成指跌破10950或创业板跌破2450；下跌家数超过4300、普通主板代理跌停超过70且成交放大。重新收复3651.43且上涨家数超过2800，情景失效。

阈值没有校准样本，不分配概率。下一次只核验实际触发与失效，不回看修改。

六、研究边界

规则版本market_review_close_v6保持冻结。量价、板块或席位标签不能确认资金身份；量化痕迹模块已取消，不再研究或作为前置。APP只展示归档与前推验证，不内置大模型、自动权重训练或自动下单。所有结果仅用于研究，不保证收益。"""

    report = {
        "id": REPORT_ID, "date": T, "market_date": T, "task_id": "market_review", "track": "market_review",
        "run_id": RUN_ID, "title": "每日复盘｜10月29日成长退潮、航天逆势与前池28只验证",
        "summary": f"全A{evidence['coverage']['full_scan']}→广泛120→深筛28；{market['decline']}只下跌，前池28/28验证、收盘中位{stats['median_close_pct']:+.3f}%，正式交易观察0、研究影子2。",
        "body": body,
        "sources": [EVIDENCE, "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688", "https://fund.eastmoney.com/a/202610293913948829.html", "https://www.kanpanba.com/limit"],
        "report_type": "full_daily_research", "eligible_for_integrated_research": True,
        "analysis_completed": True, "status": "completed", "published_at": stamp_cn, "recorded_at": stamp_cn,
        "data_cutoff_at": f"{T}T15:00:00+08:00", "provenance": "contemporaneous_close_research",
        "research_rule_version": "market_review_close_v6", "candidate_count": 0, "recommendation_ids": [],
        "research_shadow_codes": ["600118", "300900"], "evidence_file": EVIDENCE,
        "codes": [x["code"] for x in deep], "broad_pool_count": 120, "deep_pool_count": 28,
        "previous_pool_verified_count": 28, "planned_entry_date": D,
        "earliest_legal_exit_date_if_bought": EXIT,
        "prior_scenario_validation": "downside scenario partially triggered; growth indices and breadth broke thresholds, but SSE closed back above 3650 and 30-minute confirmation was unavailable",
    }
    research["items"].append(report)
    runs["items"].append({
        "id": RUN_ID + "-completed", "run_id": RUN_ID, "task_id": "market_review", "date": T,
        "trigger": "scheduled", "started_at": evidence["retrieved_at_utc"], "recorded_at": stamp_utc,
        "completed_at": stamp_utc, "status": "completed", "summary": report["summary"],
        "report_ids": [REPORT_ID], "recommendation_ids": [], "analysis_completed": True,
        "eligible_for_integrated_research": True, "delivery_status": "repository_prepared_not_yet_verified",
        "sources": [EVIDENCE],
    })
    save("backend/data/research.json", research)
    save("backend/data/task_runs.json", runs)
    save("docs/research/market-review-20261029-close-v1.json", report)
    print(json.dumps({"report_id": REPORT_ID, "run_id": RUN_ID, "deep": len(deep), "prior": stats, "repeat": [repeat5, repeat10]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
