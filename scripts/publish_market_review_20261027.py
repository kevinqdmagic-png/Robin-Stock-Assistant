#!/usr/bin/env python3
"""Append the complete 2026-10-27 market review and truthful receipt."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
T = "2026-10-27"
D = "2026-10-28"
EXIT = "2026-10-29"
REPORT_ID = "market-review-20261027-close-v1"
RUN_ID = "market-review-20261027-scheduled-close-v1"
EVIDENCE = "docs/research/market-review-2026-10-27-evidence.json"

SECTORS = {
    "300961":"环保/水处理", "301083":"智能装备", "002196":"汽车电机", "300307":"纺织机械/机器人",
    "002724":"照明设备", "002820":"食品", "300949":"景观/数字创意", "000888":"旅游",
    "002823":"汽车零部件", "600826":"会展服务", "001219":"食品", "300631":"膜材料/环保",
    "605333":"汽车线束", "600626":"纺织/汽车材料", "603370":"电机铁芯", "002249":"电机/机器人",
    "600785":"零售", "603528":"智能交通", "002284":"汽车制动", "600865":"零售",
    "000678":"轴承/机器人", "002187":"零售", "603489":"电驱动", "603350":"电机",
    "001318":"乳业", "603037":"汽车零部件", "601086":"零售", "300549":"精密模具",
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
        f"{x['code']} {x['name']}", SECTORS[x["code"]], x["trade"], f"{x['changepercent']:+.2f}%",
        f"{x['rvol5']:.2f}/{x['rvol10']:.2f}/{x['rvol20']:.2f}", f"{x['turnoverratio']:.2f}%",
        f"{x['dist_ma20']:+.2f}%", f"{x['clv']:.3f}", f"{x.get('tail_1400_close_pct',0):+.2f}%",
    ] for x in deep]
    prior_rows = [[f"{x['code']} {x['name']}", f"{x['open_pct']:+.3f}%", f"{x['mfe_pct']:+.3f}%", f"{x['mae_pct']:+.3f}%", f"{x['close_pct']:+.3f}%"] for x in prior]
    worst = sorted(prior, key=lambda x: x["close_pct"])[:5]
    best = sorted(prior, key=lambda x: x["close_pct"], reverse=True)[:5]
    idx = {x["name"]: x for x in indices}

    body = f"""研究交易日T={T}，行情截止北京时间15:00；实际完成时间{stamp_cn}。全A扫描与判断只使用T及此前公开信息。计划观察日D={D}；若D真实买入，A股T+1下最早{EXIT}卖出。本报告是market_review独立完整研究，不是四模块综合裁决。

一、市场复盘与前一日情景核验

上证{idx['上证指数']['close']:.2f}（{idx['上证指数']['change_pct']:+.2f}%）、深证成指{idx['深证成指']['close']:.2f}（{idx['深证成指']['change_pct']:+.2f}%）、创业板{idx['创业板指']['close']:.2f}（{idx['创业板指']['change_pct']:+.2f}%）、科创50 {idx['科创50']['close']:.2f}（{idx['科创50']['change_pct']:+.2f}%）。独立全A扫描5573只有效股票：{market['advance']}涨、{market['decline']}跌、{market['flat']}平，成交额约{market['amount_yuan_full_scan']/1e8:.2f}亿元。普通非ST主板代理口径：{market['standard_non_st_limit_up_sealed']}只封板、{market['standard_non_st_limit_up_touched']}只触板、{market['standard_non_st_failed_boards']}只触板未封、{market['standard_non_st_limit_down']}只跌停。

财联社11:48午间快照为46只涨停、13只连板、13只封板未遂、封板率78%；该数据只作午间交叉核验，不冒充收盘。收盘连板梯队可见上海九百5板，襄阳轴承、赛福天、多伦科技4板。上海九百5板得到当日13.31元涨停收盘行情交叉核验；席位或连板标签均不等于次日必涨。

10月26日冻结情景的核验：上证、深成指、创业板均跌破下行情景关键位，且全市场4921只下跌，价格与宽度触发了下行证据；但成交缩至约1.47万亿元，普通主板代理跌停34只，未同时满足“放量且跌停超过40”的完整触发条件。因此记为下行情景部分触发，不把它事后改写为完整命中。上行情景失效，震荡区间被向下突破。

市场判断：四大指数同步走弱，成长指数跌幅更深，收盘接近当日低位，且4921只下跌，属于退潮加速而非普通轮动。零售、旅游、食品和部分机器人连板方向仍有局部强度，但广度与指数均否定提高整体隔夜仓位。最高板从4板升至5板并不能抵消全市场风险扩散。

下一交易日重点信号：①上证3648与创业板2548能否快速收回，还是弱反抽后继续破位；②上海九百5板及三只4板的断板反馈是否扩散到零售、机器人；③10月27日涨停深筛股次日竞价是否出现大面积高开兑现或低开无承接。

二、全A覆盖与深筛28只

全A5573只→广泛池120只→深筛28只，覆盖环保、智能装备、汽车零部件、电机/机器人、食品、旅游、零售、会展、材料、智能交通等至少十组。RVOL5/10/20=当日完整成交量/此前5/10/20个已完成交易日均量；CLV=(收盘-最低)/(最高-最低)，只表示收盘位置；距MA20使用此前20日均线。六个时点是离散价格观察，不能证明触发顺序或成交。

{table(['代码/名称','板块','收盘','涨跌','RVOL5/10/20','换手','距MA20','CLV','14时后'], deep_rows)}

三、10月26日完整深筛池28/28验证

原始冻结报告market-review-20261026-close-v1的28只全部取得10月27日日线：10只收红，收盘观察均值{stats['mean_close_pct']:+.3f}%、中位{stats['median_close_pct']:+.3f}%，高点观察均值{stats['mean_mfe_pct']:+.3f}%、低点观察均值{stats['mean_mae_pct']:+.3f}%，10只盘中不利幅度达到或超过5%。最弱为{', '.join(x['code']+' '+x['name']+f" {x['close_pct']:+.2f}%" for x in worst)}；最强为{', '.join(x['code']+' '+x['name']+f" {x['close_pct']:+.2f}%" for x in best)}。

{table(['代码/名称','开盘观察','MFE','MAE','收盘观察'], prior_rows)}

这些收益以10月26日收盘为观察基准，不是10月27日买入收益。原报告正式推荐为0，真实成交N=0；缺分钟触发、9:50/14:40成交和费用，不能计算可执行净收益、胜率或盈亏比。盘中平均MFE较大而收盘中位仍为负，说明日内冲高并不等于T+1可实现收益，也不能用最高价替代退出质量。

四、结构支持、反例与筛选决定

典型支持样本：深水海纳300961 RVOL20=5.28、收涨11.43%、CLV靠近高位且14时后仍推进，但属于20%制度且涨幅已高；百胜智能301083 RVOL20=5.30、14时后继续推进，但同样有高波动和次日兑现风险；兰生股份600826 RVOL20=10.45、尾盘继续上行并封板，量价推进明确但普通成交可得性不足。

典型风险与反例：奥雅股份300949大涨9.73%却14时后回落2.69%，久吾高科300631放量大涨后尾盘回撤，说明“大量+上涨”仍可能是兑现；方正电机002196、慈星股份300307、八方股份603489虽量能显著但尾盘未继续推进。襄阳轴承、青岛食品、沪光股份等已处连板或高情绪链，不能归为低位稳健承接。

正式新增交易观察标的0只。深水海纳、百胜智能、兰生股份是展示用量价研究样本，不升级为交易卡：市场处于广度极弱的退潮日，前两只是20%制度高波动，兰生股份封板使盘后无法证明次日普通可得性。被替代候选还包括方正电机（尾盘回落）、奥雅股份（冲高回撤）、久吾高科（尾盘承接不足）。不因单一涨停、相对量或连板标签给出买入指令。

当前28只对最近{len(available5)}个可得完整报告池代码并集重复率{repeat5:.2f}%，对最近{len(available10)}个可得完整报告池并集重复率{repeat10:.2f}%。缺完整池的交易日不作0填充，因此严格5/10交易日重复率仍记N/A；正式推荐为0，推荐重复率N/A。

五、10月28日指数三情景（事前冻结，不给概率）

- 上行：上证重新站上3698并至少保持30分钟，深成指收复11534、创业板收复2638；上涨家数超过3200且成交不低于约1.55万亿元，跌停明显收窄。任一成长指数再次跌破今日低点且上涨家数转为不足2000，情景失效。
- 震荡：上证3625—3698、深成指11150—11534、创业板2520—2638内运行；上涨家数约1500—3000、成交约1.30—1.55万亿元，零售/机器人高标分歧但无系统性跌停扩散。放量突破上沿或跌破下沿使情景失效。
- 下行：上证有效跌破3625并30分钟不能收回，同时深成指跌破11150或创业板跌破2520；下跌家数超过4500、普通主板代理跌停超过45，成交较今日放大。重新收复3648.30且上涨家数超过2500，情景失效。

这些阈值没有校准样本，不分配概率。下一次只核验实际触发与失效，不回看修改。

六、研究边界

规则版本market_review_close_v5保持冻结。量价、板块或席位标签不能确认资金身份；APP只展示归档与前推验证，不内置大模型、自动权重训练或自动下单。所有结果仅用于研究，不保证收益。"""

    report = {
        "id": REPORT_ID, "date": T, "market_date": T, "task_id": "market_review", "track": "market_review",
        "run_id": RUN_ID, "title": "每日复盘｜10月27日退潮加速、前池28只验证与三情景冻结",
        "summary": f"全A5573→广泛120→深筛28；4921只下跌，前池28/28验证，收盘中位{stats['median_close_pct']:+.3f}%，正式新观察标的0。",
        "body": body,
        "sources": [EVIDENCE, "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688", "https://www.cls.cn/detail/2516200", "https://stockinsky.com/limit-ladder", "https://www.laocaifu.com/stock/600838/"],
        "report_type": "full_daily_research", "eligible_for_integrated_research": True,
        "analysis_completed": True, "status": "completed", "published_at": stamp_cn, "recorded_at": stamp_cn,
        "data_cutoff_at": f"{T}T15:00:00+08:00", "provenance": "contemporaneous_close_research",
        "research_rule_version": "market_review_close_v5", "candidate_count": 0, "recommendation_ids": [],
        "evidence_file": EVIDENCE, "codes": [x["code"] for x in deep],
        "broad_pool_count": 120, "deep_pool_count": 28, "previous_pool_verified_count": 28,
        "planned_entry_date": D, "earliest_legal_exit_date_if_bought": EXIT,
        "prior_scenario_validation": "downside_price_and_breadth_partial_trigger; volume_and_limit-down confirmation absent",
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
    save("docs/research/market-review-20261027-close-v1.json", report)
    print(json.dumps({"report_id": REPORT_ID, "run_id": RUN_ID, "deep": len(deep), "prior": stats, "repeat": [repeat5, repeat10]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
