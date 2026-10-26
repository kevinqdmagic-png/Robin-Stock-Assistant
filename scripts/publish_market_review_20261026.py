#!/usr/bin/env python3
"""Append the complete 2026-10-26 market review and truthful receipt."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
T = "2026-10-26"
D = "2026-10-27"
EXIT = "2026-10-28"
REPORT_ID = "market-review-20261026-close-v1"
RUN_ID = "market-review-20261026-scheduled-close-v1"
EVIDENCE = "docs/research/market-review-2026-10-26-evidence.json"

SECTORS = {
    "002535":"工程机械", "603331":"汽车零部件", "603901":"包装机械", "603089":"汽车零部件",
    "000810":"消费电子", "603007":"机械设备", "002931":"机器人/园林机械", "002696":"食品",
    "300552":"智能交通", "301313":"数字创意", "603683":"新材料", "688277":"医疗机器人",
    "300307":"纺织机械/机器人", "000995":"白酒", "688836":"人形机器人", "300298":"医疗器械",
    "000700":"汽车零部件", "002578":"铝加工", "000559":"汽车零部件", "001219":"食品",
    "000678":"轴承/机器人", "603138":"数据中心", "300860":"文化创意", "603719":"休闲食品",
    "688306":"智能制造/机器人", "000411":"医药商业", "003021":"微型传动/机器人", "605333":"汽车线束",
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
    current = {x["code"] for x in deep}
    prior_reports = [x for x in research["items"] if x.get("task_id") == "market_review" and x.get("date") < T and x.get("eligible_for_integrated_research") and x.get("codes")]
    prior_reports.sort(key=lambda x: x["date"], reverse=True)
    available5 = prior_reports[:5]
    available10 = prior_reports[:10]
    union5 = set().union(*(set(x["codes"]) for x in available5)) if available5 else set()
    union10 = set().union(*(set(x["codes"]) for x in available10)) if available10 else set()
    repeat5 = round(len(current & union5) / len(current) * 100, 2) if current else None
    repeat10 = round(len(current & union10) / len(current) * 100, 2) if current else None

    deep_rows = []
    for x in deep:
        deep_rows.append([
            f"{x['code']} {x['name']}", SECTORS[x["code"]], x["trade"], f"{x['changepercent']:+.2f}%",
            f"{x['rvol5']:.2f}/{x['rvol10']:.2f}/{x['rvol20']:.2f}", f"{x['turnoverratio']:.2f}%",
            f"{x['dist_ma20']:+.2f}%", f"{x['clv']:.3f}", f"{x.get('tail_1400_close_pct',0):+.2f}%",
        ])
    prior_rows = [[f"{x['code']} {x['name']}", f"{x['open_pct']:+.3f}%", f"{x['mfe_pct']:+.3f}%", f"{x['mae_pct']:+.3f}%", f"{x['close_pct']:+.3f}%"] for x in prior]
    worst = sorted(prior, key=lambda x: x["close_pct"])[:5]
    best = sorted(prior, key=lambda x: x["close_pct"], reverse=True)[:5]

    body = f"""研究交易日T={T}，行情截止北京时间15:00；实际完成时间{stamp_cn}。全A扫描与所有判断只使用T及此前公开数据。计划观察日D={D}；若D日真实买入，A股T+1下最早{EXIT}卖出。本报告是market_review独立研究，不是四模块综合双标结论。

一、市场、宽度与情绪

上证3697.52（+0.19%），深证成指11534.38（-1.19%），创业板2638.23（-1.71%），科创50 1315.50（-2.23%）。媒体口径两市成交约1.61万亿元，较上一交易日减少3475亿元，全市场超过3100只下跌。独立全A扫描5573只有效股票：2252涨、3156跌、165平，成交额约16227.66亿元。两个成交口径接近但样本范围不同，不混算。

财联社口径55只涨停、15只连板、7只3板及以上，上一交易日连板12只、晋级率58.33%，跌停超过20只；最高可见上海九百4板。独立普通非ST主板代理口径为47只封板、81只触板、34只触板未封、29只跌停。前者用于全市场情绪，后者只作可复算代理，不能直接相减。

判断：指数明显分化、缩量且个股偏弱，属于强修复后的分歧日。大消费、机器人、数据要素和石油相对活跃，算力硬件偏弱；机器人内部也出现高位兑现。高度仍有4板，但跌停扩散与前一深筛池大幅回撤说明隔夜质量下降，不能把沪指收红解释为普遍风险下降。

下一交易日最值得观察：①上海九百4板与机器人高位股开板后的亏钱扩散；②上证3700附近能否得到深成指、创业板和市场宽度确认；③今日低乖离放量样本能否缩量承接，而不是高开后再次放量不涨。

二、全A覆盖与深筛28只

全A5573只→广泛研究池120只→深筛28只，覆盖机械/机器人、汽车零部件、数据与数字创意、消费食品、医疗、材料、智能交通、医药商业等至少八组。RVOL5/10/20=当日完整成交量/此前5/10/20个已完成交易日均量；CLV=(收盘-最低)/(最高-最低)，只表示收盘位置；距MA20使用此前20日均线。六个时点只作离散价格观察，不替代完整分钟成交序列。

{table(['代码/名称','研究组','收盘','涨跌','RVOL5/10/20','换手','距MA20','CLV','14时后'], deep_rows)}

三、上一交易日完整深筛池28/28前推验证

关联原始冻结组volume-price-20261023-close-v1-cohort，28只全部取得10月26日日线；8只收红，收盘观察均值{stats['mean_close_pct']:+.3f}%、中位{stats['median_close_pct']:+.3f}%，高点观察均值{stats['mean_mfe_pct']:+.3f}%、低点观察均值{stats['mean_mae_pct']:+.3f}%，13只盘中不利幅度达到或超过5%。最弱为{', '.join(x['code']+' '+x['name']+f" {x['close_pct']:+.2f}%" for x in worst)}；最强为{', '.join(x['code']+' '+x['name']+f" {x['close_pct']:+.2f}%" for x in best)}。

{table(['代码/名称','开盘观察','MFE','MAE','收盘观察'], prior_rows)}

这些是相对10月23日收盘的价格路径，不是10月26日买入收益。上一market_review正式推荐为0，故本任务真实成交N=0；缺分钟触发顺序、9:50/14:40成交和费用，不能计算可执行净收益、胜率或盈亏比。T+1退出难度的事实反证是：慧辰股份、大普微、慈文传媒等开盘或盘中已明显低于前收，盘后信号即使D日入场也不能在同日止损卖出。

四、结构有效性、风险反例与筛选结论

支持观察的结构：顺景科技603007收4.59、RVOL20=5.46、距MA20仅+4.65%、CLV=0.898且14时后价格仍略强，是“低乖离+高相对量+收盘靠上”的典型研究样本。百达精工603331距MA20+5.98%但已封板，普通成交可得性弱于顺景。三诺生物300298 RVOL20=6.73、CLV=0.868，但距MA20+17.40%，位置更高。

否定/反例：万集科技300552 RVOL20=4.76却14时后回落约5.10%，说明大成交未继续推进；宇树科技688836距MA20+41.63%、14时后回落约4.95%，属于高位爆量分歧；慈星股份300307 RVOL20=7.71但尾盘回落约3.00%，不能把巨量自动解释为承接。林州重机、正裕工业、百洋股份、凡拓数创、兆威机电距MA20约34%至91%，不符合低位启动，也不因涨停/大涨直接进入本组条件卡。

正式新增交易观察标的0只。顺景科技、百达精工、三诺生物仅为量价研究对象：本轮未完成足以支持个股交易卡的公告/减持/解禁与次日竞价核验，且市场宽度、深成指和创业板不支持提高隔夜暴露。至少三个被替代对象为顺景科技（结构最佳但基本面风险核验未闭环）、百达精工（封板可得性不足）、三诺生物（乖离与20%制度波动更高）；万集科技因尾盘回落被否决。宁缺毋滥，不用事后价格补造盘中推荐。

与现有可核完整池比较，当前28只对最近{len(available5)}个可得完整报告池的代码并集重复率{repeat5:.2f}%，对最近{len(available10)}个可得完整报告池并集重复率{repeat10:.2f}%。这不是严格5/10交易日重复率：缺少完整池的交易日不作0填充，故严格5日、10日指标均记N/A。今日正式推荐0只，推荐重复率N/A。

五、10月27日指数条件情景（事前冻结、不设概率）

- 上行：上证站上3700并至少保持30分钟，深成指收复11639附近、创业板收复2672且上涨家数超过3200；成交额按收盘口径不低于约1.65万亿元，涨停扩散而跌停收窄。任一主要成长指数再次跌回今日低点附近且宽度转负，情景失效。
- 震荡：上证在3665—3720区间，深成指11432—11639、创业板2601—2672内运行；上涨家数约1800—3000、成交约1.45—1.70万亿元，主线轮动快。放量突破区间或跌破今日低点使情景失效。
- 下行：上证跌破3664.82且不能在30分钟内收回，同时深成指失守11432.29或创业板失守2601.09；下跌家数超过4200、跌停超过40且成交放大。重新收复上述低点并使上涨家数占优，情景失效。

没有校准样本支撑，不给三种情景分配概率。下一轮只核验触发事实，不回看后修改阈值。

六、研究边界

本次规则版本market_review_close_v5保持冻结。量价形态、席位或板块标签都不能证明资金身份；APP仅展示档案与前推验证，不内置大模型、自动权重训练或自动下单。所有结果仅用于研究，不保证收益。"""

    report = {
        "id": REPORT_ID, "date": T, "market_date": T, "task_id": "market_review", "track": "market_review",
        "run_id": RUN_ID, "title": "每日复盘｜10月26日缩量分化、前池28只验证与三情景冻结",
        "summary": f"全A5573→广泛120→深筛28；前池28/28验证，收盘中位{stats['median_close_pct']:+.3f}%，正式新观察标的0。",
        "body": body,
        "sources": [EVIDENCE, "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688",
                    "https://www.cls.cn/detail/2514665", "https://finance.sina.com.cn/tob/2026-10-26/doc-iniwprzs2532865.shtml"],
        "report_type": "full_daily_research", "eligible_for_integrated_research": True,
        "analysis_completed": True, "status": "completed", "published_at": stamp_cn, "recorded_at": stamp_cn,
        "data_cutoff_at": f"{T}T15:00:00+08:00", "provenance": "contemporaneous_close_research",
        "research_rule_version": "market_review_close_v5", "candidate_count": 0, "recommendation_ids": [],
        "evidence_file": EVIDENCE, "codes": [x["code"] for x in deep],
        "broad_pool_count": 120, "deep_pool_count": 28, "previous_pool_verified_count": 28,
        "planned_entry_date": D, "earliest_legal_exit_date_if_bought": EXIT,
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
    save("docs/research/market-review-20261026-close-v1.json", report)
    print(json.dumps({"report_id": REPORT_ID, "run_id": RUN_ID, "deep": len(deep), "prior": stats, "repeat": [repeat5, repeat10]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
