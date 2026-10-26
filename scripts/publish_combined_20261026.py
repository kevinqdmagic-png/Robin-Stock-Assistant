"""Append the independently researched T26 modules and D27 decisions atomically.

Run only after reviewing the collected sources. This one-off publisher refuses
to replace a completed module or an existing same-date decision.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo
import gzip
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from learning_loop import nth_session_after
from prepare_completion_20261023 import pct, stats
from publish_market_review_20261026 import SECTORS

T, D, EXIT = "2026-10-26", "2026-10-27", "2026-10-28"
BASE = "9320b4284c2915e72b5460680a74c6de4d058dba"
EV = "docs/research/combined-pair-20261026-evidence.json.gz"
IDS = {
    "market_review": "market-review-20261026-close-v1",
    "volume_price": "volume-price-20261026-close-v1",
    "low_position": "low-position-20261026-close-v1",
    "dragon_tiger": "dragon-tiger-20261026-close-v1",
    "combined_pair": "combined-pair-20261026-close-v1",
    "limitup_single": "limitup-single-20261026-close-v2",
}
NEW_LOW = ["603007", "002991", "001219"]


def load(p):
    return json.loads((ROOT / p).read_text())


def save(p, x):
    (ROOT / p).write_text(json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def fmt(x, n=3):
    return "N/A" if x is None else str(round(x, n)) if isinstance(x, (int, float)) else str(x)


def table(headers, rows):
    return "\n".join(["|"+"|".join(headers)+"|", "|"+"|".join(["---"]*len(headers))+"|"] +
                     ["|"+"|".join(fmt(x) for x in row)+"|" for row in rows])


def main():
    research = load("backend/data/research.json")
    runs = load("backend/data/task_runs.json")
    low = load("backend/data/low_position_samples.json")
    vp = load("backend/data/volume_price_samples.json")
    recs = load("backend/data/recommendations.json")
    catalog = load("backend/data/research_stocks.json")
    for task in IDS:
        if task == "market_review":
            continue
        if any(r.get("task_id") == task and r["date"] == T and
               r.get("report_type") in ("full_daily_research", "full_trading_research")
               for r in research["items"]):
            raise RuntimeError("Same-session full module already exists: " + task)
    market_report = next(r for r in research["items"] if r["id"] == IDS["market_review"])
    assert market_report["eligible_for_integrated_research"] and market_report["analysis_completed"]
    assert any(r.get("status") == "completed" and IDS["market_review"] in r.get("report_ids", []) for r in runs["items"])
    raw = load("tmp/combined-20261026-raw.json")
    ext = load("tmp/combined-20261026-extension.json")
    raw["daily_histories"].update(ext["daily_histories"])
    raw["minute_price_points"].update(ext.get("minute_price_points", {}))
    de = load("tmp/combined-20261026-derived.json")
    cumulative = load("tmp/combined-20261026-statistics.json")
    official = load("tmp/combined-20261026-announcements.json")
    extra_official = load("tmp/combined-20261026-extra-announcements.json")
    files = load("tmp/combined-20261026-official-files.json")
    ths = load("tmp/combined-20261026-ths.json")
    market = load("docs/research/market-review-2026-10-26-evidence.json")
    benchmarks = load("tmp/combined-20261026-benchmarks.json")
    assert len(de["broad_recomputed"]) == 120 and len(de["deep_recomputed"]) == 28
    assert not de["crosscheck"]["ohlc_mismatches"]
    assert len(de["previous_whole_pool"]) == 28 and all(r["status"] == "price_observed" for r in de["previous_whole_pool"])
    assert de["low_summary"]["all_paths_complete"] and len(de["low_validations"]) == 39
    assert all(r["seat_reconciliation"]["matched"] and r["ths_close_match"] for r in de["dragon_selected"])
    assert all(r["missing"] == 0 for r in de["progression_main_10pct"].values())
    now = datetime.now(timezone.utc)
    stamp = now.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    lookup = {r["code"]: r for r in de["broad_recomputed"]}
    daily = {c: r["bars"] for c, r in raw["daily_histories"].items() if r["ok"]}
    for s in de["deep_recomputed"]:
        s["sector_research_label"] = SECTORS[s["code"]]
        s["signal_frozen_at"] = stamp
        s["rule_version"] = "volume_price_close_v4"
        s["is_recommendation"] = False
    low_models = {"603007": "低位放量试盘", "002991": "低位放量试盘", "001219": "低中位箱体突破"}
    low_sectors = {"603007": "转型科技/原园林工程", "002991": "休闲食品", "001219": "食品"}
    low_reasons = {
        "603007": "120日区间13.197%、低位放量且收盘靠上；仍未越过4.75前20日高点，低于MA60，定为试盘而非确认启动。",
        "002991": "120日区间18.449%、60日区间35.561%，放量推进；尚未收过39.39前20日高点与MA60，保留低位试盘的可证伪观察。",
        "001219": "120日区间48.676%属低中位而非绝对底部；收盘突破13.26前20日高点，季报利润增长支持进一步研究，等待突破后承接。",
    }
    low_risks = {
        "603007": "二审诉讼仍未定；公司预计因重整债权处置而无重大本期利润影响，这属于公司判断，不是结果保证。MA60未收复。",
        "002991": "Q3营收同比-6.40%、归母净利-7.05%，不能只看累计现金流改善；分时补取失败，尾盘承接与竞价未验证。",
        "001219": "已在20/60日区间顶部附近，封板不能证明次日可成交；累计经营现金流下降30.72%，参股项目业绩承诺未完成的后续回购尚未正式决策。",
    }
    new_low = []
    for c in NEW_LOW:
        s = lookup[c]
        urls = [raw["daily_histories"][c]["source"], EV]
        urls += [files[k]["source"] for k in ({"603007": ["603007-litigation"], "002991": ["002991-q3"], "001219": ["001219-q3"]}[c])]
        new_low.append({"id": f"low-position-20261026-{c}", "date": T, "recorded_at": stamp,
            "code": c, "name": s["name"], "sector": low_sectors[c], "primary_model": low_models[c],
            "research_rule_version": "low_position_30d_v1", "feature_calculation_version": "unadjusted_MA_including_T_v3",
            "day0_close": s["close"], "day0_change_pct": s["daily_change_pct"],
            "day0_amount_yi": s["amount_yi"], "day0_turnover_pct": s["turnover_pct"],
            "day0_rvol20": s["rvol"]["20"], "day0_clv": s["clv"],
            "day0_range_position_pct": s["range_position_pct"], "day0_moving_averages": s["ma"],
            "invalid_close_below": s["low"], "initial_invalidation_basis": "未来收盘跌破T信号日低点；不后移，不冒充盘中保证止损价",
            "snapshot": s, "reason": low_reasons[c], "risk": low_risks[c],
            "original_snapshot_provenance": "contemporaneous_after_close_research_sample_not_recommendation",
            "original_snapshot_verified": True, "eligible_for_model_statistics": True,
            "statistical_scope": "future_price_observation_only_not_executable_trade_return",
            "is_recommendation": False, "default_watch": False, "capital_identity": "unknown",
            "lhb_today": any(r["SECURITY_CODE"] == c for r in raw["lhb_lists"][T]["payload"]["result"]["data"]),
            "announcement_scope": "CNINFO bounded exact-code queries; not a complete security-master, insider-sale or unlock clearance",
            "sources": list(dict.fromkeys(urls)), "report_ids": [IDS["low_position"]], "observations": []})
    # Five frozen Dragon-Tiger observation samples; no trading candidate/fill is created.
    dragon_conditions = {
        "000559": "机器人二板观察。D27竞价与9:45/10:30须核验，回踩不失守12.71且机器人同伴模塑科技000700、永创智能603901同步才继续观察；跌破T低点11.90、板块转弱或一字无普通成交即放弃交易研究。",
        "300006": "20%制度独立观察。D27守住T低点7.02后，须有缩量回踩、重新放量推进且医药同伴三诺生物300298、英特集团000411不走弱；高开后放量不涨或失守7.02放弃。不能与10%主板混算。",
        "002354": "炸板/席位背离反例。D27只有重新站回T高点8.83并经回踩维持、同伴凡拓数创301313和创维数字000810同步改善才研究修复；失守8.13或冲高继续回落即否决。不是抄底指令。",
        "301313": "高位爆量反例。D27先看能否守65.01，再看缩量回踩和板块同步；持续放量而收盘位置仍弱、跌破65.01或竞价大幅脱离T参考价即放弃。当前未列交易候选。",
        "002696": "食品高位/反包对照。12天8板不记8连板；D27需守9.50且青岛食品001219、甘源食品002991同向，不能仅因羊字题材或一笔封单继续观察；重复开板、爆量不推进直接放弃。",
    }
    selected = {s["code"]: s for s in de["dragon_selected"]}
    dragon_obs = [{"id": f"dragon-tiger-20261026-watch-{c}", "code": c, "name": selected[c]["name"],
        "date": T, "frozen_at": stamp, "planned_observation_date": D,
        "reference_price": selected[c]["close"], "reference_price_at": T+"T15:00:00+08:00",
        "board_regime": selected[c]["board_regime"], "selected_trade_id": selected[c]["selected_trade_id"],
        "condition": text, "is_recommendation": False, "executed_trade": False,
        "research_rule_version": "dragon_tiger_original_contract", "report_ids": [IDS["dragon_tiger"]], "results": []}
        for c, text in dragon_conditions.items()]
    # Reviewable official facts, not full PDF copies or unverified secondary headlines.
    fact_notes = [
        {"code": "603331", "source_keys": ["603331-h1-summary", "603331-guarantees"],
         "fact": "2026H1营收6.8827亿元(-11.15%)、归母1.0202亿元(+130.66%)，扣非-2085.24万元，经营现金流3564.76万元(-77.90%)；9月担保公告提示对外担保总额相当于最近审计净资产134.85%，不将担保总额误称实际损失。"},
        {"code": "603007", "source_keys": ["603007-litigation"],
         "fact": "6983.43万元诉讼请求处于二审、结果未定；公司称相关债权已按重整计划剥离至信托，预计不构成重大利润影响。公司判断与实际裁判结果分开。"},
        {"code": "002991", "source_keys": ["002991-q3"],
         "fact": "未经审计Q3营收5.5017亿元(-6.40%)、归母7582.46万元(-7.05%)；前三季营收16.1972亿元(+5.67%)、归母1.5591亿元(-0.18%)、扣非1.4721亿元(+5.45%)、经营现金流2.7440亿元(+19.39%)。"},
        {"code": "001219", "source_keys": ["001219-q3"],
         "fact": "未经审计前三季营收4.4881亿元(+6.00%)、归母1.0239亿元(+10.38%)、经营现金流8808.02万元(-30.72%)；公司解释现金流变化与上年票据集中兑付有关。Q3归母增长31.17%。参股项目承诺未达标的回购尚未作正式决策。"},
        {"code": "000411", "source_keys": ["000411-q3"],
         "fact": "未经审计前三季营收259.7325亿元(+4.05%)、归母2.9995亿元(-6.99%)、经营现金流-11.7170亿元；Q3归母1.0475亿元(+41.59%)，单季改善不能替代累计现金流风险。"},
        {"code": "603719", "source_keys": ["603719-control-litigation"],
         "fact": "控股股东合同纠纷一审尚未生效，公司为第三人，判决付款义务不涉及上市公司；不能写成公司已败诉赔款，也不能视为控制权风险已完全消除。"},
        {"code": "002535", "source_keys": ["002535-sanction"],
         "fact": "行政处罚事先告知涉及2025半年报收入确认，拟对公司警告并罚400万元；是事先告知而非最终处罚。公司判断未触及重大违法退市及其他风险警示，未将该判断当监管保证。"},
        {"code": "688096", "source_keys": ["688096-h1-summary"],
         "fact": "未经审计H1营收2.2709亿元(+8.11%)、归母174.39万元(-24.93%)、经营现金流-6278.72万元。长期位置低但仍低于MA20/60，不选作新启动样本。"},
        {"code": "002696", "source_keys": ["002696-risk"],
         "fact": "10月22日风险公告列半年归母亏损8253.64万元；反包涨停不证明基本面反转，N天M板不作连续板高度。"},
        {"code": "600838", "source_keys": ["600838-risk"],
         "fact": "10月24日风险提示列半年收入4322.53万元(-4.06%)、归母2507.38万元(+5.40%)，4板只是本次可见高度，不据此追最高板。"},
    ]
    for r in fact_notes:
        r["sources"] = [files[k]["source"] for k in r["source_keys"]]
    sources = list(dict.fromkeys([EV, "docs/research/market-review-2026-10-26-evidence.json",
        "https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml",
        "https://m.cls.cn/detail/2515015", "https://m.cls.cn/detail/2515094",
        "https://data.10jqka.com.cn/market/longhu/date/2026-10-26/"] +
        [r["source"] for r in files.values() if r["ok"]] +
        [raw["lhb_lists"][T]["source"], raw["limit_up_pools"][T]["source"]]))
    intro = f"研究交易日T={T}，收盘行情截止北京时间15:00；实际完成{stamp}。计划介入/观察日D={D}，若D日实际买入，最早{EXIT}可卖。本轮所有新增条件在未来结果未知时冻结，未倒填盘前候选或成交。"
    scope = ("复用同T完整market_review及真实completed回执，独立重算其120只广泛池和28只深筛；120/120与新浪当日OHLC交叉一致。"
             f"重新抓取新浪全A5576条原始记录、5573只有效行情；另取得{len(daily)}只相关股票的未复权日线。"
             "广泛池是研究队列而非推荐，不使用原扫描启发式分数推算胜率。深筛覆盖机械/机器人、汽车零部件、食品、医药/医疗、材料、数字创意、消费电子与交通等至少八组。")
    method = ("RVOL5/10/20=完整当日成交量/此前5/10/20个已完成交易日均量；收盘相对均量不同于盘中同一时点量比，后者N/A。"
              "本轮MA和20/60/120日区间含T，严格要求足额历史，短历史记N/A；原扫描的前T窗口字段和旧样本保持原样。"
              "CLV=(收盘-最低)/(最高-最低)，高低相同记N/A。成交量使用同一日线序列的手数，新浪股数/100复核。"
              "分钟资料是带日期的价格点和累计量额；不证明每分钟OHLC、逐笔、封单撤单、队列成交或同一分钟内触发先后。"
              "缺9:25竞价、历史逐日换手，故量比/换手变化记N/A。相对前收的最高/最低观察可为负/正，不冒充实际持仓MFE/MAE；低位全路径回撤包含起始收盘。")
    market_text = ("上证3697.52(+0.19%)，深成指11534.38(-1.19%)，创业板2638.23(-1.71%)，科创50 1315.50(-2.23%)。"
                   "新浪覆盖2252涨/3156跌/165平、成交16227.66亿元；媒体沪深口径约1.61万亿元，较前日少3475亿元。"
                   "覆盖范围不同分开保留。推断为强修复后的缩量分歧：食品、大消费和部分机器人延续，算力偏弱，机器人高位兑现加重；"
                   "沪指收红不足以说明多数股票隔夜质量改善。")
    emotion_table = table(["交易日", "财联社涨停/炸板/封板率", "连板数", "新浪普通非ST主板跌停代理"], [
        ["10月22日", "33 / 23 / 59%", 9, 58], ["10月23日", "82 / 12 / 87%", 12, 11],
        ["10月26日", "55 / 23 / 71%", 15, 29]])
    layers = de["board_ladder"][T]["layers"]
    ladder = table(["普通非ST主板连续梯队", "家数", "逐股名单"], [
        [f"{n}板" if n < 5 else "5板及以上", len(layers[str(n)]),
         "、".join(r["name"]+r["code"] for r in layers[str(n)]) or "无"] for n in range(1, 6)])
    progression = table(["T23→T26层级", "原逐股分母", "晋级", "断板", "停牌/缺失", "描述性晋级%"], [
        [k.replace("_to_", "进"), r["prior_full_denominator"], r["advanced"], r["broken"], r["missing"], r["verified_advancement_pct"]]
        for k, r in de["progression_main_10pct"].items()])
    space = ("空间参照实际查询T之前20个交易日原池，取得14日，9月18/21/22/23/24/28日6池为空；"
             "可见范围最高是10月16日新华传媒600825的11板，价格已与当日日线核对。完整20日最高仍N/A。"
             "本轮高标尝试截至23日是海洋王002724/大业603278六板，26日均断板；今日普通主板最高上海九百600838四板，"
             "次高三板为襄阳轴承000678、林州重机002535、赛福天603028、正裕工业603089、多伦科技603528。"
             "华阳智能301502三板属20%制度另列，百洋12天8板、福莱6天4板均不当作8连板/4连板。"
             "不宣称空间已打开，完整情绪周期起点未获得可检验定义，记未知。")
    denominator_note = ("晋级分母由date=T23历史全池独立取回，按普通非ST主板逐股锁定后与T26对照，"
                        "所有53+8+1+2条前收均核对日线；原完整分母与断板明细在证据中保留。"
                        "这是T26的历史重建，不伪称T23事前发布过的预测样本。接口qdate是查询当日元数据，"
                        "历史日期由请求参数及逐股价格交叉核验，不能直接拿qdate当行情日。"
                        "媒体58.33%的整体连板晋级率不套到首板进二板；无分母的0/0记N/A。")
    deep_table = table(["代码/名称", "研究组", "收盘", "RVOL5/10/20", "20/60/120日位置%", "距MA20% / CLV", "14时后%"], [
        [r["code"]+" "+r["name"], SECTORS[r["code"]], r["close"], "/".join(fmt(r["rvol"][str(k)]) for k in (5,10,20)),
         "/".join(fmt(r["range_position_pct"][str(k)]) for k in (20,60,120)),
         fmt(r["distance_ma20_pct"])+" / "+fmt(r["clv"]), r["tail_1400_close_pct"]] for r in de["deep_recomputed"]])
    previous_table = table(["代码/名称", "开盘观察%", "最高观察%", "最低观察%", "收盘观察%"], [
        [r["code"]+" "+r["name"], r["open_pct"], r["mfe_pct"], r["mae_pct"], r["close_pct"]] for r in de["previous_whole_pool"]])
    previous_note = ("先完成10月23日冻结池28/28验证，未只挑最后两只：8只收红，收盘观察均值-1.985%、中位-2.776%，"
                     "平均最高观察+3.058%、平均最低观察-4.110%，13只最低相对前收≤-5%。"
                     "市场复盘与量价引用同一原cohort，关联原id避免重复计数。"
                     "对上一综合现金组、D26打板现金组，候选和成交均0，无策略盈亏；研究池回撤不是持仓亏损。")
    stats_table = table(["冻结量价版本", "样本/独立日期", "T+1价观N", "均值/中位%", "平均最低观察%", "对沪指平均价差%"], [
        [v, f"{r['frozen_sample_count']}/{r['independent_dates']}", r["horizons"]["1"]["n"],
         fmt(r["horizons"]["1"]["mean_pct"])+" / "+fmt(r["horizons"]["1"]["median_pct"]),
         r["horizons"]["1"]["mean_mae_pct"], r["horizons"]["1"]["mean_excess_price_pct"]]
        for v, r in cumulative["vp_by_rule_version"].items()])
    stats_note = ("历史9个明确id的量价cohort共229条日期-股票样本：228个原收盘锚能与日线一致，10月8日1条不匹配保留为待补证；"
                  "无id的9月29/30回溯样本另存，不纳统计。v4只有5个独立日期，140条不是140个独立交易日，重复股票与同日相关性明显。"
                  "所有1/2/3/5/10/20/30交易日节点、版本、失败和缺锚均逐条保存，T+2及更长不成熟节点仍pending。"
                  "收益定义为信号日收盘到目标日收盘的价格观察；基准为同日期上证指数，均未计持仓成交。"
                  "交易手续费、最低佣金、数量及滑点未校准，20bp只为旧占位假设，不扣出来伪称净收益；"
                  "首板/二板/回封、情绪、板块与买入窗口的策略净收益/胜率/盈亏比/退出质量均N/A，实际可验证成交N=0。"
                  "旧形态和行业标签不全，缺失项保持未知，不事后按结果补标签。9:50、14:40和盘后组分开留存，"
                  "本轮价格点可做同一时刻描述，不能反推当时建仓或当日可卖。")
    facts_text = "\n".join(f"- {r['code']}：{r['fact']} 来源："+"、".join(r["sources"]) for r in fact_notes)
    volume_body = f"""{intro}

一、独立量价研究覆盖与量价口径
{scope}
{method}
{market_text}

二、完整28只新冻结样本
{deep_table}
每只原始OHLC、前5/10/20日相对量、换手/成交额、20/60/120日位置、突破标记、14时后量价及日期已冻结；54只当日分时价格点覆盖旧28池与新28池并集及席位比较对象。额外补取甘源/京源分时失败，如实记缺，未以日线补尾盘。

三、先验证上一完整池与历史版本
{previous_note}
{previous_table}
{stats_table}
{stats_note}

四、3—5个典型结构及反例
顺景科技603007是低位放量试盘：RVOL20=5.458、CLV=0.898，但未收过4.75且低于MA60，不叫确认突破。青岛食品001219收过前20日高点13.26、CLV=1，属于突破描述，仍需下一日回踩验证。百达精工603331 RVOL20=8.713且封板，但H1扣非亏损、经营现金流下降及担保风险否决把巨量直接当优质启动。万集科技300552在高相对量后14时至收盘约-5.10%，是不推进的反例。凡拓数创301313、宇树科技688836高位爆量后收盘位置偏弱，不能把大成交和板块热度单独解释成承接。
本次尚不能证明“缩量回踩”已成功：T26刚放量的对象必须等待未来可得数据。缩量上涨要看价格是否推进，放量下跌要留失败样本，高位爆量/长上影要结合尾盘退回，而不是仅用K线名称确认账户行为。全池对前一日量的比值和20日突破标记已保存；无法取得连续历史分钟OHLC，分时分歧→低点抬高→缩量回踩→再转强的完整顺序不作已验证判断。

五、对筛选/买点/退出的影响与下一假设
不单凭量价发交易卡，正式新增交易候选0。低位试盘只入30天研究池，综合组和打板组另行裁决；D27买入当日不能因失效当日卖。下一前推假设：①低乖离放量后守住T低点的样本，是否有较小T+1/T+2不利观察；②T26尾盘回落超过3%的组，D27是否较弱；③首板大增但1进2仅8/53时，封板后的隔夜可成交性是否更差。均为待证伪假设，旧规则和权重未改，不把本轮描述性统计当稳定规律。
"""
    new_low_table = table(["代码/名称", "分类", "收盘/初始失效", "涨跌/成交额亿/换手%", "RVOL5/10/20", "20/60/120日位置%", "反证"], [
        [s["code"]+" "+s["name"],s["primary_model"],fmt(s["day0_close"])+" / "+fmt(s["invalid_close_below"]),
         fmt(s["day0_change_pct"])+" / "+fmt(s["day0_amount_yi"])+" / "+fmt(s["day0_turnover_pct"]),
         "/".join(fmt(s["snapshot"]["rvol"][str(k)]) for k in (5,10,20)),
         "/".join(fmt(s["day0_range_position_pct"][str(k)]) for k in (20,60,120)),s["risk"]] for s in new_low])
    low_table = table(["原日期/代码/名称", "自然日/交易日", "当前价观%", "路径高/低点%", "收盘峰谷回撤%", "首次收破原失效"], [
        [r["reference_date"]+" "+r["code"]+" "+r["name"],str(r["elapsed_natural_days"])+"/"+str(r["elapsed_trading_sessions"]),
         r["close_return_pct"],fmt(r["path_mfe_pct"])+"/"+fmt(r["path_mae_pct"]),r["max_close_to_close_drawdown_pct"],r["first_verified_close_below_original_invalid"]]
        for r in de["low_validations"]])
    low_models_table = table(["原模型", "原样本", "本次价格资格合格", "30自然日合格模型N"], [
        [r["model"],r["all_n"],r["eligible_n"],r["mature_30d_eligible_n"]] for r in de["low_model_statistics"]])
    low_body = f"""{intro}

A. 新增独立30天研究样本
{scope}
本轮在广泛池中另外比较甘源食品/京源环保等低涨幅对象，新增3条研究样本，并非每日短线交易推荐，default_watch=false；原39条完整保留。本轮不使用低位名义追已经加速的林州、正裕、百洋与凡拓。新样本理由与反证均在实际完成时间冻结：
{new_low_table}
顺景初始失效4.15、甘源38.00、青岛13.08均为T低点，未来“收盘跌破”用于研究失效，不后移；它们不是保证成交止损价。顺景和甘源都未确认越过前20日高点且未站稳MA60，分别标低位试盘；青岛只称低中位突破，不宣称仍在绝对底部。三只均有T日未复权收盘和新浪交叉、完整20/60/120日位置与均线，资金账户身份未知，T日无对应龙虎榜。减持/解禁、未来停牌/除权的完整证券主档未接入，不能将公告搜索无结果当风险清零。
{method}
新增样本将验证1/3/5/10/15/20/30自然日和5/10/20交易日节点；非交易日取目标日之前最近可得交易日，记录真实报价日。三条都是本轮新冻结，尚无未来绩效，不把它们加入成熟30天统计。D27可能出现的竞价/回踩都待核验，不能冒称已形成买点。

B. 全部旧样本的重要变化
39条/38股全路径已核验，无交易日缺口、未删除失效与下跌样本；吉林化纤两个日期分别保留。每条追加本日观察和完整自然日/交易日节点，不修改原价格/失效位。
{low_table}

C. 已到期30自然日复盘
只有9月23日双环传动002472、宝信软件600845两条达到30自然日；截至T26已经33自然日、17个实际交易日，仍不是30交易日。30日固定节点取10月23日，而非把26日价格倒填节点。两条original_snapshot_verified=false，且原初失效曾触发，继续排除正式模型统计。合格30自然日模型N=0，30交易日成熟N=0；不提供虚构30天胜率、盈亏比或10%/20%达标率。

D. 模型阶段统计与下一验证
{low_models_table}
模型原数合计39，本次新增3另外起算；不同入选日期的当前价观不能混成30日收益。相同窗口的5/10/20日价格节点和原始基准在证据中逐条保存；未成熟不补值，费用和实际可执行净收益N/A。
下一假设：低位放量试盘若下一交易日不能缩量守原低点，其5/10日不利波动是否更大；青岛的箱体突破与顺景/甘源的未确认试盘分组前推，不按结果合并或改规则。低位30天研究与短线综合、打板分别统计。

E. 官方补证（事实与推断分开）
{facts_text}
上述财务为相应报告期，未经审计状态保留；形态不是确定主力吸筹、财务增长不是股价上涨保证。研究自选新理由只在完整报告之后追加，旧理由不改。
"""
    seat_table = table(["代码/名称", "日榜净额万元", "机构净额万元", "股通净额万元", "买1/卖1集中度%", "日榜TRADE_ID"], [
        [r["code"]+" "+r["name"],r["net_cny"]/1e4,r["institution_net_wan"],r["stock_connect_net_wan"],
         fmt(r["buy_concentration_top1_pct"])+"/"+fmt(r["sell_concentration_top1_pct"]),r["selected_trade_id"]] for r in de["dragon_selected"]])
    dragon_prev_table = table(["前8只重点/代码", "开盘%", "收盘%", "最高/最低观察%"], [
        [r["name"]+r["code"],r["open_pct"],r["close_pct"],fmt(r["mfe_pct"])+"/"+fmt(r["mae_pct"])] for r in de["dragon_previous_focused_eight"]])
    dragon_group_table = table(["上一披露全池分组", "N", "正收盘数", "均值/中位%", "最差/最好%"], [
        [b,s["n"],s["positive_n"],fmt(s["mean_pct"])+"/"+fmt(s["median_pct"]),fmt(s["min_pct"])+"/"+fmt(s["max_pct"])] for b,s in de["dragon_previous_by_board"].items()])
    dragon_body = f"""{intro}

一、独立完整龙虎榜覆盖
当日东方财富87条理由行、71只去重股票，包含多日榜与不同制度；同花顺摘要84行按单日/3日区分。独立深比9只，9/9买卖五席合计与原榜核对、9/9同周期同花顺收盘价一致；不把重复理由、多日榜与单日榜相加。完整原行、买五/卖五、TRADE_ID和聚合口径留档，机构与股通净额用去重席位并集，买入额不当净买入。没有将接口EXPLAIN自带的厂商“成功率”用于本研究。
{seat_table}
名单覆盖封板/连板、炸板、冲高回落与高位分歧。席位和成交数据为收盘后披露，未提前用于T26盘中。

二、结构与席位画像
万向钱潮000559日榜机构+8525.794万元、股通+12636.705万元，收盘封板但距MA20约19.38%、买1集中45.424%；共振只支持观察，不能确认锁仓。莱美药业300006机构+3343.603万元、股通+2797.529万元，20%制度单列，其距MA20约27.24%也不算低位。
天娱数科002354从T23机构+6738.887万元转为本日-6354.574万元，股通仍净买2895.678万元；本日CLV约0.029、盘中触板后回落，席位方向不一致。榕基软件002474机构-3996.654万元而股通+896.881万元，收盘接近日低，是另一背离反例。凡拓数创301313机构净卖10596.708万元、CLV约0.492且高乖离，不能用上涨10.43%抵消兑现风险。
襄阳轴承000678机构小幅正向而股通-2516.142万元，三板未意味着所有资金同向。林州重机002535封板但机构净卖1555.935万元且有官方处罚事先告知，优先否决纯形态跟随。百洋股份002696榜单净买同时机构净卖2482.616万元，且为12天8板反包，应与连续板分开。大业603278日榜小幅净买不抹去六进七失败和高位波动。
营业部画像保留原始实名部门、买卖双向额、集中度与不同日期记录；公开前五名不能看见未上榜持仓或推断实际持仓周期。相同席位双侧出现只记双向交易迹象，不确认为某游资本人、量化账户、做T利润或对倒；历史风格/胜率尚无同口径足够样本，N/A。

三、先验证上一组全部重点与全披露池
T23原8只重点全部核验，见下；正式交易候选0因此成交0。更广的T23披露池78只也全部有T26价格观察，失败/退市/北交样本均保留。8只北交标的腾讯仅返回当前日K，前收使用T23已归档榜单CLOSE_PRICE，显式标注历史路径不可得；没有伪造完整历史日线。
{dragon_prev_table}
{dragon_group_table}
各组是价格观察，不能混成同一涨跌幅制度策略胜率。席位组合×位置×板块×情绪×封板质量分层的可执行净收益仍N/A；全量逐股开盘、最高/最低、收盘及缺分钟项存证据，不只追涨的对象。

四、D27五只条件观察样本（不是交易推荐）
{table(['对象/参考收盘','冻结观察与放弃条件'],[[r['name']+r['code']+' / '+fmt(r['reference_price']),r['condition']] for r in dragon_obs])}
窗口冻结为D27 9:25、9:45、10:30及14:00后，北京时间；现时D27竞价、实时盘口和成交均待验证。若另行真实买入，最早D28卖出；D27失效不能当日止损卖。跌停/停牌或无买盘保留无法退出状态，不假定阈值成交。

五、情绪、高度、空间与晋级
{market_text}
{emotion_table}
{ladder}
{progression}
{denominator_note}
{space}
下一可证伪假设：同日机构/股通同向且较低乖离的组，是否比机构净卖与弱CLV组有较小次日不利观察。当前9只只有一个日期，不宣布组合有效；规则未按结果调整。
"""
    alternative_table = table(["真实备选", "T26参考收盘", "当前/计划板数与角色", "支持", "否决/未闭环"], [
        ["百达精工603331",12.91,"首板→二板；机械跟随待确认","高RVOL、封板","扣非亏损/现金流及担保，20日高点13.28未有效收过"],
        ["青岛食品001219",13.62,"首板→二板；食品跟随待确认","20日突破、Q3利润增长","60日区间97.1%、可能高开不可得，板块持续性待验"],
        ["英特集团000411",10.52,"首板→二板；医药商业待确认","单季利润改善，低乖离","累计利润下降、经营现金流为负，医药主线地位待验"],
        ["永创智能603901",10.63,"二板→三板；机器人/包装设备","板块同步与封板","距MA20较高，二进三接力风险与队列未知"],
        ["万向钱潮000559",12.71,"二板→三板；机器人换手核心待确认","机构与股通净买","约19.4%乖离、买1集中，非低位首板"],
        ["林州重机002535",3.33,"三板→四板；高位参考","梯队继续","约31.4%乖离、机构净卖、处罚事先告知，否决"],
        ["上海九百600838",12.10,"四板→五板；消费高度参考","当前可见最高","已有官方风险提示，不因最高板追板"],
    ])
    v2old = []
    for c in ["002009","002354","002747","002241","002724","603278"]:
        b = {s["date"]:s for s in daily[c]};a,b26=b["2026-10-23"],b[T]
        v2old.append({"code":c,"group":"T23_low_deviation_main_comparison" if c in ["002009","002354","002747","002241"] else "T23_six_board_controls",
                      "reference_date":"2026-10-23","reference_close":a["close"],"observed_date":T,
                      "close_pct":pct(b26["close"],a["close"]),"high_observation_pct":pct(b26["high"],a["close"]),
                      "low_observation_pct":pct(b26["low"],a["close"]),"executed_trade":False})
    limit_body = f"""{intro}

结论：D27空仓，无合格打板候选。独立limitup_single_v2模拟研究完成，未把综合组结论直接复制为本组结论，也未把T26涨停当作事前已买入。

一、最近三日情绪先于个股
{scope}
{market_text}
{emotion_table}
整体连板仍有延续是正证据，涨停由82降55、炸板由12升23、普通主板跌停代理由11升29、六板高标两只全断是反证。判断为分歧加重，尚不能当新一轮一致加速；不使用沪指涨跌单一指标定性。

二、高度、空间与逐股晋级
{ladder}
{progression}
{denominator_note}
{space}
四板消费高标和三板机器人均有，但同一板块内高位兑现扩散，会影响低位首板的D27承接与D28退出。三板参考对象不自动进入本实验首板/二板范围。

三、独立否决与至少三只真实备选
{alternative_table}
普通主板10%与创业/科创20%、北交30%、ST/退市各自分组；排除上市初期无上限、流动性不足、一字排队板和高位缩量加速。本轮即使百达/青岛的量价好于高标，仍不足以超过公告与隔夜质量的否决，故不为一天一只降标准。用户关注/持仓和旧询问名单不作为入口。

四、固定交付卡（现金组）
资料边界为T26已收盘行情、截至实际完成时间已取回的官方公告和已披露龙虎榜。参考价均为T26收盘，不是成交价；D27权威涨停价、除权/停牌和实时队列尚不存在完整当日报价证据，记N/A，不用前收×1.1冒充已核验上限。当前没有入选股票，故无买入区间、委托价或虚构失效成交位。
后续验证窗口冻结D27 9:25、9:35—10:30与14:00后；观察高标上海九百600838、旧高标海洋王002724/大业603278，机器人同伴万向000559/永创603901和食品同伴青岛001219/甘源002991，基准全部T26。D27如高标继续跌停、主线断层、连续开板/撤单、爆量不推进、一字无普通成交、盘口不能核实，直接放弃，不视单笔封单为触发。本轮无候选，不预告盘中会自动买入或持续秒级监控。
若未来另行事前冻结合格模拟卡、在D27买入，最早D28可卖；强开/平开/弱开均按原固定退出规则在D28 9:30起首个可证明可成交的窗口核验，不事后挑最高价；弱开或失效不保证止损价格，跌停/停牌保留未能卖出与后续敞口。D27炸板不能靠当天卖出止损。当前继续20—30实际交易日的首轮前推复核，不代表优势已证明或自动转实盘。

五、上一候选与前推统计
D26原现金组候选0、成交0，没有当日封板成功率或策略盈亏。龙溪股份600592的v1原条件与必要开盘条件未满足的旧结果保持冻结；本轮仅追加价格节点，不重新激活。v1唯一原候选N=1、可验证成交N=0；v2正式候选与成交截至本轮均0。
T23已公开的六只比较对象继续验证，而非事后新推荐：
{table(['代码/原比较组','收盘观察%','最高/最低观察%'],[[r['code']+' / '+r['group'],r['close_pct'],fmt(r['high_observation_pct'])+'/'+fmt(r['low_observation_pct'])] for r in v2old])}
这些只有1个日期、低乖离4只/六板对照2只，不是策略胜率；全部负例保留。按首板/二板/回封、市场情绪、板块阶段、高度、空间尝试、版本及长假单列的可执行均值/中位净收益、盈亏比、封板率/炸板率、尾部损失与退出质量N/A。20bp旧成本占位未校准，没有排队成交和两侧费用证据不算净收益。市场封板率不等于本策略封板率或赚钱率。
本轮新发现是首板晋级8/53远弱于媒体整体连板口径、同一主线内部的席位与量价分化扩大。下一假设：只有D27低乖离且公告清楚、回封承接完整的首/二板样本，才值得未来版本前推；现在不修改v2或承诺涨停概率。
"""
    combined_body = f"""{intro}

结论：综合盘后组0只，空仓观察。规则combined_limitup_watch_v5保持，综合研究和D27独立打板v2分别裁决、分别归档。

一、四项同T完整前置与真实完成回执
{table(['模块','同T完整报告','支持/反对'],[
 ['market_review',IDS['market_review'],'支持食品及部分机器人延续；反对缩量分化、3156只下跌与旧池中位-2.776%'],
 ['volume_price',IDS['volume_price'],'支持顺景/青岛量价；反对巨量后不推进、尾盘回落与单因子失效'],
 ['low_position',IDS['low_position'],'3条新的30天研究样本，有冻结失效；不是短线交易信号，未收MA60的试盘仍未确认'],
 ['dragon_tiger',IDS['dragon_tiger'],'万向机构/股通同向；天娱、凡拓等机构卖出与弱CLV形成反证']])}
市场复盘复用已线上完整报告及原回执；另三项由本轮独立完整补做，有各自task_id/track/report_id、样本和scheduled回执。未将配置审计、automated_observation或eligible=false当作四项前置，已取消量化不恢复。联合只是编排。

二、全A筛选及重新比较
{scope}
{method}
{deep_table}
{alternative_table}
顺景603007/甘源002991较高位备选更接近长期低位，但尚未确认过前20日高点与MA60；青岛001219有突破与盈利支持却已在短中期区间顶部。百达603331即使量价突出也被扣非、现金流与担保反证否决。万向000559虽有机构/股通支持，但高度、乖离与买侧集中度不利于隔夜退出。林州002535另有处罚事先告知，最高板上海九百600838不能因高度自动入选。当前没有任何对象在证据、执行可得性与隔夜质量上同时胜出。
过去5日市场复盘codes仅2日可核，10日同样2日；可得池交集5/28=17.857%，不是完整5/10日重复率，严格值N/A。新增正式推荐0，推荐重复率N/A；不为降低重复率硬换股。已有同T唯一决策后不反复换名单，重大新事实另追加有时间戳修订。

三、量价验证与上一综合组真实表现
{previous_note}
{previous_table}
{stats_table}
{stats_note}
旧9:50/14:40样本、盘后组和打板v1/v2分别追加结果，未将T26盘中最高涨幅当实际盈利。没有分钟OHLC/委托与成交证据，不推断触发先后；失败、未触发与无法成交样本均留档。

四、D27介入与D28退出边界
本轮无合格标的，故无新买入区间/失效位/止盈卡；30天观察池不冒充综合两只。D27竞价后仍需二次核验，T26收盘候选不能开盘即买。若未来另行事前冻结研究卡并在D27真实买入，最早D28才可卖；D27失效不能当日止损，涨停浮盈与可执行退出分开，跌停/停牌可能卖不出。不给未经校准的涨停概率或收益承诺。
下一交易日重点：①上海九百4板与六板断板股的负反馈是否收敛；②首板晋级8/53后低位能否真正承接；③顺景、甘源的试盘与青岛突破能否缩量守原低点。若宽度恶化、主线断层、爆量不推进或实时盘口无法核验，保持现金，不盘后补造事前交易。

五、独立打板检查与事实/假设边界
D27完整limitup_single_v2报告{IDS['limitup_single']}独立裁决0只，非第五项前置。空间20日历史只取得14日，完整高点未知，未把4板说成打开空间。APP只展示真实研究与验证，不内置大模型、不会自动训练权重。上述量价和席位解释是可证伪假设；官方财务/监管事实见独立模块与证据，均有明确日期。
"""
    bodies = {"volume_price": volume_body, "low_position": low_body, "dragon_tiger": dragon_body,
              "limitup_single": limit_body, "combined_pair": combined_body}
    titles = {"volume_price": "量价研究｜10月26日完整28池、旧池验证与巨量不推进反例",
              "low_position": "低位启动30天｜10月26日新增3条研究样本与全部39条旧样本验证",
              "dragon_tiger": "龙虎榜研究｜10月26日9只席位复核、5只条件观察与78只旧池验证",
              "limitup_single": "打板v2｜10月27日空仓，分层晋级与空间缺项先于形态",
              "combined_pair": "综合双标｜10月26日四项齐备，10月27日空仓观察"}
    summaries = {"volume_price": "全A5573→120→28；前池28/28中位-2.776%，v4历史140条/5日期；不以巨量代替承接。",
                 "low_position": "新增顺景、甘源、青岛3条非交易研究样本；39条旧样本全路径验证，合格30自然日模型N=0。",
                 "dragon_tiger": "87理由行/71股、9只席位核对、5只条件观察；旧披露池78只分制度价格验证。",
                 "limitup_single": "D27无合格打板候选；主板1进2为8/53、2进3为5/8、六进七0/2；20日空间缺6池。",
                 "combined_pair": "四项同T完整齐备；综合0只、D27打板另组0只，旧综合现金无盈亏。"}
    rule_versions = {"volume_price": "volume_price_close_v4", "low_position": "low_position_30d_v1",
                     "dragon_tiger": "dragon_tiger_original_contract", "limitup_single": "limitup_single_v2",
                     "combined_pair": "combined_limitup_watch_v5"}
    new_reports = []
    for task in bodies:
        rid = IDS[task];run_id = f"{task.replace('_','-')}-20261026-scheduled-close-{'v2' if task=='limitup_single' else 'v1'}"
        r = {"id":rid,"date":T,"market_date":T,"task_id":task,
             "track":task if task in ("volume_price","low_position","dragon_tiger") else "market_review",
             "run_id":run_id,"title":titles[task],"summary":summaries[task],"body":bodies[task].strip(),"sources":sources,
             "report_type":"full_trading_research" if task=="combined_pair" else "full_daily_research",
             "eligible_for_integrated_research":task!="limitup_single","analysis_completed":True,"status":"completed",
             "published_at":stamp,"recorded_at":stamp,"market_data_cutoff_at":T+"T15:00:00+08:00",
             "data_cutoff_at":stamp,"planned_entry_date":D,"earliest_legal_exit_date_if_bought":EXIT,
             "research_rule_version":rule_versions[task],"provenance":"contemporaneous_after_close_research",
             "candidate_count":0,"recommendation_ids":[],"evidence_file":EV,
             "full_scan_count":5573,"broad_pool_count":120,"deep_pool_count":28,
             "codes":[s["code"] for s in de["deep_recomputed"]]}
        if task=="low_position":r.update(new_sample_count=3,new_sample_ids=[s["id"] for s in new_low],previous_samples_verified=39,codes=sorted({s["code"] for s in low["items"]+new_low}))
        if task=="dragon_tiger":r.update(observation_count=5,signal_observations=dragon_obs,codes=[s["code"] for s in de["dragon_selected"]])
        if task=="combined_pair":r.update(dependency_report_ids=[IDS[t] for t in ["market_review","volume_price","low_position","dragon_tiger"]],
                                           strategy="combined_limitup_watch",group="close",cohort_label="综合盘后组",decision="cash_no_qualified_candidate")
        if task=="limitup_single":r.update(strategy="limitup_single_v2",decision="cash_no_qualified_candidate",group="close",full_20_session_space_reference_available=False)
        new_reports.append(r)
        runs["items"].append({"id":run_id+"-completed","run_id":run_id,"task_id":task,"date":T,"trigger":"scheduled",
            "started_at":raw["actual_started_at_utc"],"completed_at":stamp,"recorded_at":stamp,"status":"completed",
            "summary":summaries[task],"report_ids":[rid],"recommendation_ids":[],"analysis_completed":True,
            "eligible_for_integrated_research":task!="limitup_single","delivery_status":"repository_prepared_not_yet_ci_or_production_verified",
            "sources":[EV]})
        (ROOT/f"docs/research/{rid}.md").write_text("# "+titles[task]+"\n\n"+bodies[task].strip()+"\n\n来源：\n\n"+"\n".join("- "+s for s in sources)+"\n")
    research["items"].extend(new_reports)
    # The original rows and prior observations are left intact, including failures.
    for s in low["items"]:
        obs = next(r for r in de["low_validations"] if r["origin_cohort_id"] == s["id"])
        s.setdefault("observations", []).append({**obs,"recorded_at":stamp,"calculated_at":de["calculated_at"]})
    low["items"].extend(new_low);low["updated_at"]=stamp
    # Verify the prior whole pool before appending the newly frozen cohort.
    vp["items"].append({"id":"volume-price-20261023-validation-20261026-v1","date":T,"task_id":"volume_price",
        "recorded_at":stamp,"report_ids":[IDS["volume_price"]],"origin_cohort_id":"volume-price-20261023-close-v1-cohort",
        "rule_version":"volume_price_close_v4","full_validation_completed":True,
        "full_pool_summary":de["previous_whole_pool_summary"],"full_pool_validations":de["previous_whole_pool"],
        "executed_trade_count":0,"eligible_for_model_statistics":False,"statistical_scope":"price_observation_not_executable_strategy"})
    vp["items"].append({"id":"volume-price-historical-validation-20261026-v1","date":T,"task_id":"volume_price",
        "recorded_at":stamp,"report_ids":[IDS["volume_price"]],"cohort_ids":[r["origin_cohort_id"] for r in cumulative["vp_all_cohort_validations"]],
        "frozen_sample_count":229,"matched_original_close_count":228,"rule_version_groups":cumulative["vp_by_rule_version"],
        "evidence_file":EV,"executed_trade_count":0,"eligible_for_model_statistics":False,
        "note":"Only descriptive frozen-signal closing-price observations; no mixing versions, fills or net returns."})
    vp["items"].append({"id":"volume-price-20261026-close-v1-cohort","date":T,"task_id":"volume_price",
        "frozen_at":stamp,"report_ids":[IDS["volume_price"]],"rule_version":"volume_price_close_v4",
        "feature_calculation_version":"unadjusted_MA_including_T_v3","data_cutoff_at":T+"T15:00:00+08:00",
        "broad_pool_count":120,"broad_pool_verified_count":120,"deep_screen_count":28,
        "eligible_for_model_statistics":True,"statistical_scope":"future_price_observation_not_trade_profitability",
        "provenance":"contemporaneous_full_market_research","samples":de["deep_recomputed"]})
    # Results are price-only and never reactivate a necessary condition that failed.
    for r in recs["items"]:
        bs=daily[r["code"]];by={b["date"]:b for b in bs};anchor=r.get("planned_entry_date") or r["date"];a=by.get(anchor)
        hs=[]
        for h in (1,3,5,10,20,30):
            target=nth_session_after(date.fromisoformat(anchor),h);ds=target.isoformat() if target else None
            b=by.get(ds);path=[p for p in bs if anchor<p["date"]<=str(ds)]
            mature=bool(ds and ds<=T);ok=bool(mature and b and a)
            hs.append({"h":h,"date":ds,"status":"price_observed" if ok else "missing" if mature else "pending",
                       "close_pct":pct(b["close"],a["close"]) if ok else None,
                       "high_observation_pct":pct(max(p["high"] for p in path),a["close"]) if ok and path else None,
                       "low_observation_pct":pct(min(p["low"] for p in path),a["close"]) if ok and path else None})
        r.setdefault("results",[]).append({"id":r["id"]+"-price-review-20261026","date":T,"market_date":T,
            "recorded_at":stamp,"report_ids":[IDS["limitup_single"] if r.get("task_id")=="limitup_single" else IDS["combined_pair"]],
            "status":"price_observation_only","observed_daily":by[T],"anchor_date":anchor,"anchor_close":a["close"] if a else None,
            "horizons":hs,"trigger_status":"original_no_entry_preserved" if r["id"]=="limitup-single-20261008-600592-v1" else "not_reconstructed_from_daily_extremes",
            "executed_trade":False,"executable_net_return_pct":None,"source":raw["daily_histories"][r["code"]]["source"],
            "note":"Original group/rules/recommendation and prior outcomes preserved; price observation is not actual entry/exit P/L."})
    stock_updates=[]
    for stock in catalog["items"]:
        rows=[r for r in de["low_validations"] if r["code"]==stock["code"]]
        if not rows:continue
        r=rows[-1];episode={"id":f"research-stock-{stock['code']}-20261026-low-followup-v1","date":T,"recorded_at":stamp,
            "title":"30天研究价格跟踪与原失效核验","reason":f"{stock['name']}原低位样本继续跟踪；本次相对原收盘价格观察{r['close_return_pct']}%，原样本和资格不改。",
            "evidence_status":"verified_daily_price_observation_not_trade_return",
            "fact_note":f"原日期{r['reference_date']}，原失效位{r['original_invalid_close_below']}；曾收破={r['ever_verified_close_below_original_invalid']}。",
            "validation":["继续按原自然日与交易日节点观察，未成熟不补结果","原快照资格与初始失效位冻结"],
            "risk":"价格回升不抹去曾触发失效；未验证委托成交、净收益或主力身份。",
            "report_ids":[IDS["low_position"]],"sources":[raw["daily_histories"][stock["code"]]["source"],EV]}
        stock["history"].append(episode);stock_updates.append({"code":stock["code"],"history_id":episode["id"]})
    for s in new_low:
        assert not any(r["code"]==s["code"] for r in catalog["items"])
        ep={"id":f"research-stock-{s['code']}-20261026-origin-v1","date":T,"recorded_at":stamp,
            "title":"新增30天研究样本，非短线交易推荐","reason":s["reason"],"evidence_status":"verified_closed_daily_snapshot_with_official_filing_risk_notes",
            "fact_note":f"{s['name']}T26收盘{s['day0_close']}，初始收盘失效位{s['invalid_close_below']}；未来结果尚未知。",
            "validation":["按1/3/5/10/15/20/30自然日及5/10/20交易日节点前推","跟踪放量后的承接、原低点和板块持续性，不据形态确认资金身份"],
            "risk":s["risk"],"report_ids":[IDS["low_position"]],"sources":s["sources"]}
        catalog["items"].append({"code":s["code"],"name":s["name"],"sector":s["sector"],"role":"research","default_watch":False,"history":[ep]})
        stock_updates.append({"code":s["code"],"history_id":ep["id"]})
    evidence={"market_date":T,"actual_started_at_utc":raw["actual_started_at_utc"],"actual_completed_at":stamp,
        "planned_entry_date":D,"earliest_legal_exit_if_bought":EXIT,"base_main":BASE,
        "reused_market_report_id":IDS["market_review"],"reused_market_report_sha256":hashlib.sha256(json.dumps(market_report,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
        "sina_pages":raw["sina_pages"],"daily_histories":raw["daily_histories"],"minute_price_points":raw["minute_price_points"],
        "minute_retry_attempts":ext.get("minute_retry_attempts",{}),"lhb_lists":raw["lhb_lists"],"seat_queries":raw["seat_queries"],
        "limit_up_pools":raw["limit_up_pools"],"historical_20_session_pools":ext["historical_20_session_pools"],
        "derived":de,"cumulative":cumulative,"official_queries":official,"extra_official_queries":extra_official,
        "official_files":{k:{a:b for a,b in r.items() if a not in ("pdf_path","text_path")} for k,r in files.items()},
        "official_verified_fact_notes":fact_notes,"ths_summary_rows":ths["tables"][5],"ths_source":ths["source"],
        "benchmarks":benchmarks,"new_low_samples":new_low,"new_dragon_observations":dragon_obs,
        "prior_v2_frozen_comparison_results":v2old,"stock_history_updates":stock_updates,
        "limitations":["20 prior-session space pools available 14/20; full highest unknown",
            "Minute quote points are not OHLC/ticks/order-book/fills; extra two quote queries failed",
            "T27 auction, official daily limit/security status and liquidity not yet verified",
            "One T8 original VP closing anchor mismatch and legacy samples retained outside statistics",
            "Strict 5/10 session repeat-rate archive incomplete; statistical date clustering and regime differences",
            "No executable trading win rate, fee-calibrated net return or automatic parameter update"]}
    (ROOT/EV).write_bytes(gzip.compress(json.dumps(evidence,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode(),mtime=0))
    save("backend/data/research.json",research);save("backend/data/task_runs.json",runs)
    save("backend/data/volume_price_samples.json",vp);save("backend/data/low_position_samples.json",low)
    save("backend/data/recommendations.json",recs);save("backend/data/research_stocks.json",catalog)
    save("app/src/main/assets/research_stocks.json",catalog)
    manifest={"base_main":BASE,"market_date":T,"planned_entry_date":D,"actual_started_at_utc":raw["actual_started_at_utc"],
        "analysis_completed_at":stamp,"new_report_ids":[r["id"] for r in new_reports],"reused_report_ids":[IDS["market_review"]],
        "new_recommendations":0,"new_low_samples":len(new_low),"old_low_observations_appended":39,
        "new_volume_samples":28,"old_frozen_recommendation_results_appended":len(recs["items"]),
        "stock_history_updates":stock_updates,"evidence_file":EV,"evidence_sha256":hashlib.sha256((ROOT/EV).read_bytes()).hexdigest(),
        "delivery_state_at_preparation":"not_yet_ci_or_production_verified","rules_and_task_schedule_changed":False}
    save("docs/research/combined-pair-20261026-publication-manifest.json",manifest)
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
