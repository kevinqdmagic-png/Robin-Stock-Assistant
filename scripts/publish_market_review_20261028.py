#!/usr/bin/env python3
"""Append the complete 2026-10-28 market review and truthful receipt."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
T = "2026-10-28"
D = "2026-10-29"
EXIT = "2026-10-30"
REPORT_ID = "market-review-20261028-close-v1"
RUN_ID = "market-review-20261028-scheduled-close-v1"
EVIDENCE = "docs/research/market-review-2026-10-28-evidence.json"

SECTORS = {
    "000554":"成品油零售", "300539":"精密塑料/机器人", "300980":"功能泡棉", "605488":"功能性涂布材料",
    "600828":"零售", "002696":"水产养殖", "300549":"精密模具/机器人", "603337":"工业缝制设备",
    "603109":"发电机组/机械", "603037":"汽车减震/机器人", "001400":"挤压模具", "301225":"汽车零部件",
    "688836":"机器人", "300718":"滑动轴承/机器人", "600078":"磷化工", "603131":"焊接/航天",
    "002889":"供应链物流", "001296":"铸造材料", "002172":"医药健康", "003028":"智能控制/机器人",
    "603081":"文体旅设备/机器人", "688286":"MEMS传感器", "603926":"汽车传动", "300986":"建筑铝模",
    "603699":"工业阀门", "603633":"连接器", "300421":"精密轴承", "300473":"汽车零部件",
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
    indices = evidence["index_quotes"]["items"]
    current = {x["code"] for x in deep}
    prior_reports = [x for x in research["items"] if x.get("task_id") == "market_review" and x.get("date") < T and x.get("eligible_for_integrated_research") and x.get("codes")]
    prior_reports.sort(key=lambda x: x["date"], reverse=True)
    available5, available10 = prior_reports[:5], prior_reports[:10]
    union5 = set().union(*(set(x["codes"]) for x in available5)) if available5 else set()
    union10 = set().union(*(set(x["codes"]) for x in available10)) if available10 else set()
    repeat5 = round(len(current & union5) / len(current) * 100, 2)
    repeat10 = round(len(current & union10) / len(current) * 100, 2)

    deep_rows = [[
        f"{x['code']} {x['name']}", SECTORS[x["code"]], x["trade"], f"{float(x['changepercent']):+.2f}%",
        f"{x['rvol5']:.2f}/{x['rvol10']:.2f}/{x['rvol20']:.2f}", f"{float(x['turnoverratio']):.2f}%",
        f"{x['dist_ma20']:+.2f}%", f"{x['clv']:.3f}", f"{x.get('tail_1400_close_pct',0):+.2f}%",
    ] for x in deep]
    prior_rows = [[f"{x['code']} {x['name']}", f"{x['open_pct']:+.3f}%", f"{x['mfe_pct']:+.3f}%", f"{x['mae_pct']:+.3f}%", f"{x['close_pct']:+.3f}%"] for x in prior]
    worst = sorted(prior, key=lambda x: x["close_pct"])[:5]
    best = sorted(prior, key=lambda x: x["close_pct"], reverse=True)[:5]
    idx = {x["name"]: x for x in indices}

    body = f"""研究交易日T={T}，行情截止北京时间15:00；实际完成时间{stamp_cn}。全A扫描与判断只使用T及此前公开信息。计划观察日D={D}；若D真实买入，A股T+1下最早{EXIT}卖出。本报告是market_review独立完整研究，不是四模块综合裁决。

一、市场复盘与10月27日情景核验

上证{idx['上证指数']['close']:.2f}（{idx['上证指数']['change_pct']:+.2f}%）、深证成指{idx['深证成指']['close']:.2f}（{idx['深证成指']['change_pct']:+.2f}%）、创业板{idx['创业板指']['close']:.2f}（{idx['创业板指']['change_pct']:+.2f}%）、科创50 {idx['科创50']['close']:.2f}（{idx['科创50']['change_pct']:+.2f}%）。独立全A扫描5572只有效股票：{market['advance']}涨、{market['decline']}跌、{market['flat']}平，成交额约{market['amount_yuan_full_scan']/1e8:.2f}亿元。普通非ST主板代理口径：{market['standard_non_st_limit_up_sealed']}只封板、{market['standard_non_st_limit_up_touched']}只触板、{market['standard_non_st_failed_boards']}只触板未封、{market['standard_non_st_limit_down']}只跌停。

媒体收盘口径为66只涨停、70只炸板、封板率49%、8只连板，最高襄阳轴承5板；另一15:23未定版口径为73只涨停、68只炸板、5只跌停。两者覆盖范围不同，与本档普通非ST主板代理口径分别保存，不混算。机器人为最强主线，芯片、工业机械和汽车零部件扩散；白酒、电信运营及部分医药方向相对偏弱。最高板维持5板，但1进2约5/24、2进3约2/8，说明普涨修复与连板晋级质量并不同步。

10月27日冻结的三个情景没有一个完整触发：价格收盘仍在震荡区间，上证未站上3698、深成指未站上11534、创业板未收复2638；但上涨4156只、成交约1.642万亿元又超过震荡情景的宽度与量能上限，并满足上行情景的广度和量能部分条件。因此记录为“价格在震荡区间、广度量能强修复”的未预注册组合，不事后改成上行情景命中；下行情景失效。

市场判断：10月27日退潮后出现放量普涨修复，成长指数弹性明显强于上证；但触板134只而仅63只封住，代理炸板71只，媒体封板率约49%，说明筹码交换剧烈。主线从零售/机器人高标转向机器人首板扩散，情绪由退潮进入修复，尚不能凭一天普涨认定新上升周期。

下一交易日重点信号：①上证能否放量站稳3695、创业板能否突破2648而不是高开回落；②机器人首板潮次日1进2承接及襄阳轴承5板断板反馈；③今日大量触板未封品种是否转为负反馈，炸板率能否明显收窄。

二、全A覆盖与深筛28只

全A5572只→广泛池120只→深筛28只，覆盖机器人、汽车零部件、工业机械、功能材料、零售、水产、化工、物流、医药、MEMS、连接器、阀门等至少十二组。RVOL5/10/20=当日完整成交量/此前5/10/20个已完成交易日均量；CLV=(收盘-最低)/(最高-最低)，只表示收盘位置；距MA20使用此前20日均线。六个时点是离散价格观察，不能证明触发顺序或成交。

{table(['代码/名称','板块','收盘','涨跌','RVOL5/10/20','换手','距MA20','CLV','14时后'], deep_rows)}

三、10月27日完整深筛池28/28验证

原始冻结报告market-review-20261027-close-v1的28只全部取得10月28日日线：{stats['positive_close_count']}只收红，收盘观察均值{stats['mean_close_pct']:+.3f}%、中位{stats['median_close_pct']:+.3f}%，高点观察均值{stats['mean_mfe_pct']:+.3f}%、低点观察均值{stats['mean_mae_pct']:+.3f}%，{stats['mae_le_minus5_count']}只盘中不利幅度达到或超过5%。最弱为{', '.join(x['code']+' '+x['name']+f" {x['close_pct']:+.2f}%" for x in worst)}；最强为{', '.join(x['code']+' '+x['name']+f" {x['close_pct']:+.2f}%" for x in best)}。

{table(['代码/名称','开盘观察','MFE','MAE','收盘观察'], prior_rows)}

这些收益以10月27日收盘为观察基准，不是10月28日买入收益。原报告正式推荐为0，真实成交N=0；缺分钟触发、9:50/14:40成交和费用，不能计算可执行净收益、胜率或盈亏比。全池收盘中位转正但平均MAE仍达-4.441%，说明修复日内路径剧烈，T+1退出质量不能只看收盘。

四、量价发现、反例与双轨筛选

量价支持样本：纽威股份603699处于MA20下方2.93%，RVOL20=3.54、换手2.01%、CLV=0.997，14时后仍推进1.35%，属于低位相对放量与尾盘承接；横河精密300539 RVOL20=6.60、换手23.68%、CLV=0.967，14时后推进3.05%，属于高换手分歧后再转强，但已高于MA20约25.06%；优德精密300549 RVOL20=5.99、换手16.38%、CLV=0.904，14时后推进3.10%，是中位机器人扩散样本。

反例与兑现风险：祥源新材300980盘中冲高后14时后回落；恒勃股份301225、宇树科技688836、长盛轴承300718、敏芯股份688286均在高位放量后未收于日内最高，显示大成交不等于持续推进。福莱新材、杰克科技、凯众股份等封板或接近封板，盘后无法证明次日普通可得性；百洋股份尾盘回封虽强，但当日换手33.65%、距MA20 37.06%，隔夜风险高。

正式新增交易观察标的0只：盘后不能预先证明D日竞价承接与普通可得性，且当日炸板比例高，不把修复日高弹性直接写成正式买入卡。研究影子轨冻结两只（不写入正式recommendations）：603699纽威股份用于H1“低位放量+尾盘承接”，300539横河精密用于H3“板块逆势/扩散强度与绝对涨幅排序”及高位对照。D日9:25后若竞价超过+5%、板块同伴明显转弱、开盘量价背离或跌破T日14:00价格，则各自失效；即使触发也只形成前推研究样本，不自动成为交易指令。被替代候选包括300549优德精密（同板块但位置更高）、002696百洋股份（高换手回封与追高风险）、603337杰克科技（封板可得性不足）。

当前28只对最近{len(available5)}个可得完整报告池代码并集重复率{repeat5:.2f}%，对最近{len(available10)}个可得完整报告池并集重复率{repeat10:.2f}%。缺完整池的交易日不作0填充，因此严格5/10交易日重复率仍记N/A；正式推荐为0，推荐重复率N/A。

五、10月29日指数三情景（事前冻结，不给概率）

- 上行：上证站上3695并至少保持30分钟，深成指突破11530、创业板突破2650；上涨家数超过3500且成交不低于1.60万亿元，机器人首板晋级和炸板率同时改善。任一成长指数跌回今日收盘下方且上涨家数不足2500，情景失效。
- 震荡：上证3650—3695、深成指11290—11530、创业板2560—2650内运行；上涨家数约2200—3800、成交约1.45—1.70万亿元，高标分歧但跌停不扩散。放量突破上沿或跌破下沿使情景失效。
- 下行：上证跌破3650并30分钟不能收回，同时深成指跌破11290或创业板跌破2560；下跌家数超过3500、普通主板代理跌停超过20且成交放大。重新收复3681.47且上涨家数超过2800，情景失效。

阈值没有校准样本，不分配概率。下一次只核验实际触发与失效，不回看修改。

六、研究边界

规则版本market_review_close_v6保持冻结。量价、板块或席位标签不能确认资金身份；量化痕迹模块已取消，不再研究或作为前置。APP只展示归档与前推验证，不内置大模型、自动权重训练或自动下单。所有结果仅用于研究，不保证收益。"""

    report = {
        "id": REPORT_ID, "date": T, "market_date": T, "task_id": "market_review", "track": "market_review",
        "run_id": RUN_ID, "title": "每日复盘｜10月28日放量普涨修复、前池28只验证与三情景冻结",
        "summary": f"全A5572→广泛120→深筛28；4156只上涨，前池28/28验证，收盘中位{stats['median_close_pct']:+.3f}%，正式交易观察0、研究影子2。",
        "body": body,
        "sources": [EVIDENCE, "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688", "https://www.kanpanba.com/limit", "https://lianban.net/days/2026-10-28.html", "https://yuanchuang.10jqka.com.cn/20261028/c681177032.shtml"],
        "report_type": "full_daily_research", "eligible_for_integrated_research": True,
        "analysis_completed": True, "status": "completed", "published_at": stamp_cn, "recorded_at": stamp_cn,
        "data_cutoff_at": f"{T}T15:00:00+08:00", "provenance": "contemporaneous_close_research",
        "research_rule_version": "market_review_close_v6", "candidate_count": 0, "recommendation_ids": [],
        "research_shadow_codes": ["603699", "300539"], "evidence_file": EVIDENCE,
        "codes": [x["code"] for x in deep], "broad_pool_count": 120, "deep_pool_count": 28,
        "previous_pool_verified_count": 28, "planned_entry_date": D,
        "earliest_legal_exit_date_if_bought": EXIT,
        "prior_scenario_validation": "no complete scenario trigger; price stayed in sideways bands while breadth and turnover matched only part of upside scenario",
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
    save("docs/research/market-review-20261028-close-v1.json", report)
    print(json.dumps({"report_id": REPORT_ID, "run_id": RUN_ID, "deep": len(deep), "prior": stats, "repeat": [repeat5, repeat10]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
