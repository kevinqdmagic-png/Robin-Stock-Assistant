#!/usr/bin/env python3
"""Atomically append the completed 2026-10-15 component and combined research."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backend/data"
EVIDENCE_PATH = ROOT / "docs/research/combined-pair-2026-10-15-evidence.json"
CN = ZoneInfo("Asia/Shanghai")
STARTED_AT = "2026-10-15T17:29:00+00:00"
T = "2026-10-15"
REPORT_IDS = {
    "volume_price": "volume-price-20261015-close-v1",
    "low_position": "low-position-20261015-close-v1",
    "dragon_tiger": "dragon-tiger-20261015-close-v1",
    "combined_pair": "combined-pair-20261015-close-v1",
}
CNINFO_FOSU = "https://static.cninfo.com.cn/finalpage/2026-10-15/1225604903.PDF"


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text())


def dump(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fmt(value, digits=2):
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def signed(value, digits=2):
    if value is None:
        return "N/A"
    return f"{value:+.{digits}f}"


def md_table(headers, rows):
    lines = ["|" + "|".join(headers) + "|", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["|" + "|".join(str(cell).replace("|", "/") for cell in row) + "|" for row in rows]
    return "\n".join(lines)


def utc_iso(now: datetime) -> str:
    return now.isoformat(timespec="milliseconds")


def cn_iso(now: datetime) -> str:
    return now.astimezone(CN).isoformat(timespec="milliseconds")


def run_id(task: str, now: datetime) -> str:
    return f"{task.replace('_', '-')}-20261015-scheduled-{now.strftime('%H%M%S')}z"


def build_volume(evidence, stamp_cn, rid):
    samples = evidence["volume_price"]["deep_samples"]
    stats = evidence["volume_price"]["previous_statistics"]
    rows = []
    for sample in samples:
        rows.append([
            f"{sample['code']} {sample['name']}",
            f"{sample['close']:.2f}/{signed(sample['daily_change_pct'])}%",
            fmt(sample["turnover_pct"]),
            "/".join(fmt(sample["rvol"][str(n)]) for n in (5, 10, 20)),
            fmt(sample["clv"], 3),
            fmt(sample["range_position_pct"].get("120"), 1),
            f"{signed(sample['tail_return_1400_to_1500_pct'])}%/{fmt(sample['tail_volume_share_pct'],1)}%",
            sample["structure"],
        ])
    table = md_table(
        ["代码/名称", "收盘/涨跌", "换手%", "RVOL5/10/20", "CLV", "120日位置%", "14点后涨跌/量占", "结构"],
        rows,
    )
    body = f"""一、范围与口径

T={T}。本报告复用同日完整市场复盘的全A有效5,569只入口、120只广泛池，并对28只深筛样本逐只完成量价结构留档；数据截止北京时间15:35:45。RVOL5/10/20分母只使用T之前已完成交易日；CLV=(收盘-最低)/(最高-最低)，日内无区间时才记不适用。本次公开分钟数据为价格点和累计量额，不是逐笔或分钟OHLC，不能推断触发先后、真实成交或9:50/14:40可执行收益。

二、28只深筛全量样本（volume_price_close_v3）

{table}

三、结构发现与反例

- 低中位放量推进：000973佛塑科技、002812恩捷股份、301069凯盛新材、300771智莱科技均处120日区间较低位置，RVOL20为3.02—4.08且CLV不低于0.784。佛塑14点后+2.01%、恩捷+0.73%，是价格在成交放大后继续推进的正证据；仍须T+1回踩确认。
- 放量加速不等于可买：冰山冷热、广博股份、上海雅仕、向日葵等已封板，无法由收盘价证明次日存在普通成交。正业科技、朗特智能、中邮科技单日涨12%—13%；中邮尾盘-4.75%，均先列追高/兑现反例。
- 高量不涨/冲高回落：三维化学RVOL20=8.02但CLV0.576；新经典RVOL20=11.41但距MA20+37.4%；欢瑞世纪换手37.9%、CLV0.548且尾盘-3.37%。成交放大后没有稳定推进，不能机械加分。
- 龙虎榜共振与背离：远东股份公开榜单净买较高但RVOL20仅1.19；华林证券封板且120日位置74.9%；超声电子高换手上涨却榜单净卖。席位方向不替代量价和可成交验证。

四、上一冻结量价池完整前推

10月12日冻结26只已在10月13日取得26/26日日线和9:30、9:45、10:30、午盘、14:00、14:40、15:00历史价格点。开盘为正2只，收盘为正13只；开盘观察均值{signed(stats['mean_open_return_pct'])}%、中位{signed(stats['median_open_return_pct'])}%；收盘观察均值{signed(stats['mean_close_return_pct'])}%、中位{signed(stats['median_close_return_pct'])}%；日高观察均值{signed(stats['mean_high_observation_pct'])}%，日低观察均值{signed(stats['mean_low_observation_pct'])}%。执行样本N=0：上一批没有统一冻结的全池触发、盘口与真实成交，策略胜率、净收益、盈亏比、可执行MFE/MAE均为N/A；不得以日高代替策略收益。

五、对综合选股和下一假设

量价独立支持000973与002812进入终选复核，优先级来自“120日低位+RVOL20约3+CLV高+距MA20小+尾盘仍推进”，不是单个形态标签。301069与300771为替代，但尾盘承接、成交容量或20%制度下的T+1回撤风险逊于前两只；688552虽有榜单净买和相对量，距MA20+12.4%且科创板波动更高。

冻结假设VP3：冰点日中，非封板且120日低位、RVOL20在2—4、CLV>0.80、距MA20<5%、尾盘价格为正的样本，只有T+1先缩量守回踩位再放量突破近压，才可能改善T+2退出质量。000973/002812为前推样本；若直接高开越过放弃位、放量不进或板块继续退潮，即为反例。往返20bp只作为未来真实模拟成交的占位成本，不用于本日价格观察。"""
    sources = [
        "docs/research/market-review-2026-10-15-evidence.json",
        "docs/research/combined-pair-2026-10-15-evidence.json",
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        "https://web.ifzq.gtimg.cn/appstock/app/day/query",
        "https://data.10jqka.com.cn/market/longhu/date/2026-10-15/",
    ]
    return {
        "id": REPORT_IDS["volume_price"], "date": T, "market_date": T,
        "task_id": "volume_price", "track": "volume_price", "report_type": "full_daily_research",
        "eligible_for_integrated_research": True, "run_id": rid,
        "published_at": stamp_cn, "recorded_at": stamp_cn, "data_cutoff_at": "2026-10-15T15:35:45+08:00",
        "title": "量价研究与验证｜2026-10-15 全池承接、反例与前推复核",
        "summary": "全A5569只入口、120只广泛池、28只深筛完整留档；完整补验10月12日冻结26只，10月13日收盘观察均值-0.26%，执行样本N=0。",
        "body": body, "sources": sources, "evidence_file": "docs/research/combined-pair-2026-10-15-evidence.json",
        "provenance": "contemporaneous_close_research", "codes": [row["code"] for row in samples],
        "rule_version": "volume_price_close_v3", "frozen_sample_codes": [row["code"] for row in samples],
        "coverage": {"all_a_entry": 5569, "broad_pool": 120, "deep_reviewed": 28, "full_market_complete": True},
        "previous_sample_validation": stats, "samples": samples,
        "typical_display_codes": ["000973", "002812", "301069", "000530", "000892"],
    }


def low_sector(code):
    return {
        "000973": "新材料/锂电隔膜", "002812": "锂电隔膜", "301069": "特种新材料",
        "688552": "军工雷达", "300771": "智能物流/物联网", "600199": "白酒",
    }.get(code, "待复核")


def build_low(evidence, stamp_cn, rid):
    existing = evidence["low_position"]["existing_validations"]
    new = evidence["low_position"]["new_candidates"]
    old_rows = [[
        f"{row['code']} {row['name']}", row.get("reference_date", ""), row.get("elapsed_trading_sessions", ""),
        signed(row.get("close_return_pct")), f"{signed(row.get('path_mfe_pct'))}/{signed(row.get('path_mae_pct'))}",
        "是" if row.get("observed_close_below_original_invalid") else "否",
    ] for row in existing]
    new_rows = [[
        f"{row['code']} {row['name']}", f"{row['close']:.2f}/{signed(row['daily_change_pct'])}%",
        fmt(row["turnover_pct"]), "/".join(fmt(row["rvol"][str(n)]) for n in (5, 10, 20)),
        fmt(row["range_position_pct"].get("120"), 1), fmt(row["clv"], 3), f"{row['low']:.2f}",
    ] for row in new]
    matured = evidence["low_position"]["matured_30_natural_days"]
    body = f"""一、全量跟踪口径

T={T}。复用同日全A5,569只入口、120只广泛池和28只深筛，不把关注、自选或用户询问股票自动纳入。历史18只全部保留并追加10月15日收盘及路径观察；新建6只低位启动研究样本；30自然日到期{matured}只。日线价格路径不是触发后交易收益，缺历史分钟触发、盘口和成交时，可执行净收益保持N/A。

二、既有18只样本全量节点

{md_table(['样本','入池日','交易日D+','入池至今%','路径MFE/MAE%','收盘破初始失效'], old_rows)}

双环传动、宝信软件、五方光电与天顺风能已以10月15日收盘跌破原初始失效位；失败样本不删除。传艺科技入池至今仍为正，但路径MFE与当前收益差距大，说明高波动兑现；东岳硅材路径MFE+20.00%、当前+6.82%，亦不能把日高当可执行收益。18只中旧快照仍有不满足模型统计条件者，且0只完成30自然日，正式30日平均/中位、胜率、盈亏比和10%/20%比例均N/A。

三、新增6只样本（low_position_30d_v1）

{md_table(['样本','收盘/涨跌','换手%','RVOL5/10/20','120日位置%','CLV','初始收盘失效位'], new_rows)}

- 000973佛塑科技：120日位置11.5%、RVOL20=3.02、CLV0.987；同日业绩预告形成事件催化，但公告明确4.56亿元营业外收入为一次性且无现金流入，整合与竞争风险仍在。初始30日样本失效为收盘跌破11.45。
- 002812恩捷股份：120日位置12.0%、RVOL20=3.02、CLV0.846，价格从低位向MA20上方推进；MA20仍低于MA60，50元压力未突破。收盘跌破45.05否定本轮低位结构。
- 301069凯盛新材、300771智莱科技：同为低中位放量，但尾盘分别-0.71%/-0.17%，承接弱于佛塑/恩捷；收盘失效15.00/10.83。
- 688552航天南湖：榜单净买与RVOL20=4.47形成共振，但距MA20+12.4%、科创板20%波动和高开兑现风险更高；收盘失效30.75。
- 600199金种子酒：白酒相对强、RVOL20=3.76，但120日位置51.5%只算中低位且换手12.4%；收盘失效7.10。

四、量价验证、统计边界和待证伪假设

正证据是000973/002812成交扩大后仍靠近日高，反例是历史低位样本中双环、五方、天顺跌破初始失效，以及吉林化纤巨量后未保持。公开数据不确认“主力吸筹”；低位、放量、榜单席位均只是可验证特征。

冻结假设LP1：120日位置<25%、RVOL20为2—4、CLV>0.80且非封板的样本，在T+1缩量回踩不破信号低点后，其5/10/20交易日退出质量可能优于单日10%/20%加速样本。后续按1/3/5/10/15/20/30自然日附近及5/10/20交易日追加，停牌/无行情保留缺失，不移动原节点。"""
    return {
        "id": REPORT_IDS["low_position"], "date": T, "market_date": T,
        "task_id": "low_position", "track": "low_position", "report_type": "full_daily_research",
        "eligible_for_integrated_research": True, "run_id": rid,
        "published_at": stamp_cn, "recorded_at": stamp_cn, "data_cutoff_at": "2026-10-15T15:35:45+08:00",
        "title": "低位启动股30天研究｜2026-10-15 全量18只节点与6只新样本",
        "summary": "完整验证18只历史样本并保留4只收盘失效反例；新增佛塑科技、恩捷股份等6只，30自然日到期0只，不宣称稳定胜率。",
        "body": body,
        "sources": [
            "docs/research/combined-pair-2026-10-15-evidence.json",
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
            CNINFO_FOSU,
        ],
        "evidence_file": "docs/research/combined-pair-2026-10-15-evidence.json",
        "provenance": "contemporaneous_close_research", "research_version": "low_position_30d_v1",
        "sample_ids": [f"low-position-20261015-{row['code']}" for row in new],
        "historical_sample_validated_count": len(existing), "new_sample_count": len(new),
        "matured_30_natural_days": matured,
    }


def build_dragon(evidence, stamp_cn, rid):
    dragon = evidence["dragon_tiger"]
    selected = dragon["selected_observations"]
    prior = dragon["previous_validations"]
    names = {row["code"]: row["name"] for row in selected}
    rows = [[
        f"{row['code']} {row['name']}", signed(row["change_pct"]), fmt(row["turnover_pct"]),
        f"{signed((row['net_cny'] or 0)/100000000)}亿", fmt(row.get("rvol20")), fmt(row.get("clv"), 3),
        fmt((row.get("range_position_pct") or {}).get("120"), 1),
    ] for row in selected]
    previous_close = [row["close_return_pct"] for row in prior]
    previous_high = [row["high_observation_pct"] for row in prior]
    previous_low = [row["low_observation_pct"] for row in prior]
    body = f"""一、榜单范围与情绪环境

T={T}为A股交易日。东方财富公开接口取得66条上榜原因记录、去重60个证券代码；同花顺页面为62行摘要，供应商范围差异原样保留，不混作一个精确全市场分母。市场复盘显示全A仅429涨、5,108跌，36涨停、26—28跌停，昨日首板晋级2/21、二板及以上晋级4/15，情绪为冰点/系统性风险释放。公开席位标签只代表交易通道，不能认定个人、机构最终持仓、量化身份、锁仓或做T。

二、五只龙虎榜观察/反例

{md_table(['样本','涨跌%','换手%','榜单净额','RVOL20','CLV','120日位置%'], rows)}

1. 600869远东股份：榜单净买约2.64亿元，公开买方含北京知春路、国新北京分公司等多路通道；收涨6.79%、CLV0.911且120日位置21.0%。反证是RVOL20仅1.19、日振幅上榜且成交42.20亿元，量价没有形成“首次放量”确认。10月16日仅在非高开加速、回踩守17.00附近且重新站18.10、板块同步时观察；高开追涨或跌破16.50放弃。
2. 002945华林证券：榜单净买约1.93亿元，涨停且RVOL20=6.42；但120日位置74.9%、封板不证明次日普通成交，多条“机构专用”买卖方向交错。仅作证券板块强度样本，开盘一字/高开超过+5%或板块无扩散直接放弃。
3. 000892欢瑞世纪：榜单净买约1.08亿元，但换手37.9%、CLV0.548、14点后-3.37%，且公开机构席位买卖分歧明显；量价否定席位净买的单独有效性。次日未缩量守5.20并重站5.55不观察。
4. 000823超声电子：收涨5.38%却榜单净卖约2.37亿元，换手36.0%、120日位置78.5%。连续高换手与席位卖出构成拥挤风险；不因PCB板块强而追，跌破24.50或高开量大价不进直接放弃。
5. 000530冰山冷热：涨停、换手41.0%、RVOL20=16.99且120日位置100%，榜单小幅净卖；这是“封板强价格+高位巨量+席位未同向”的风险样本。无普通成交/开板后不能快速回封一律不算可买。

天津普林净买约0.85亿元且涨停，但已封板且不在本轮量价深筛前两名；远东的席位合力、华林的涨停都没有替代可成交确认。席位信息只服务于次日承接与兑现风险。

三、上一龙虎榜组验证

10月12日冻结的吉林化纤、中文在线、绿盟科技、芒果超媒、大金重工5只，在10月13日均取得日线与历史分钟价格点。开盘观察均为负；收盘观察均值{signed(statistics.fmean(previous_close))}%、中位{signed(statistics.median(previous_close))}%，日高观察均值{signed(statistics.fmean(previous_high))}%，日低观察均值{signed(statistics.fmean(previous_low))}%。大金重工收跌停，直接反驳“前日修复或榜单净买可机械延续”；中文在线收+1.10%是唯一正收盘。没有统一触发/成交，策略N=0，净收益与胜率N/A。

四、阶段结论与待验证

市场冰点下，榜单净买只有同时满足低/中位置、非封板可成交、相对量和价格推进、板块广度时才进入下一层；本日远东仍缺相对量，华林/冰山缺次日可成交，欢瑞/超声存在量价或席位背离。因此龙虎榜不直接支持综合两只，只对高位/高换手替代者形成否定，并对000973/002812保持中性——二者未上榜不等于利空，也不能推断机构未参与。

下一假设DT2：在冰点日，“低中位+多路净买+CLV高”若缺RVOL，次日退出质量未必优于“无榜单但RVOL与尾盘推进同步”的容量股。后续分席位组合、位置、板块、情绪和封板质量累计；样本不足不报稳定胜率。"""
    return {
        "id": REPORT_IDS["dragon_tiger"], "date": T, "market_date": T,
        "task_id": "dragon_tiger", "track": "dragon_tiger", "report_type": "full_daily_research",
        "eligible_for_integrated_research": True, "run_id": rid,
        "published_at": stamp_cn, "recorded_at": stamp_cn, "data_cutoff_at": stamp_cn,
        "title": "龙虎榜超短研究｜2026-10-15 合力、背离与高换手兑现风险",
        "summary": "交叉核对66条上榜原因与62行公开摘要，完整验证上一组5只；远东/华林为正向结构，欢瑞/超声/冰山为量价或高位反例。",
        "body": body,
        "sources": [
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            "https://data.10jqka.com.cn/market/longhu/date/2026-10-15/",
            "https://www.stcn.com/article/detail/4220898.html",
            "https://finance.eastmoney.com/a/202610153896965011.html",
            "docs/research/combined-pair-2026-10-15-evidence.json",
        ],
        "evidence_file": "docs/research/combined-pair-2026-10-15-evidence.json",
        "provenance": "contemporaneous_close_research", "rule_version": "dragon_tiger_close_v2",
        "codes": [row["code"] for row in selected],
        "billboard_reason_rows": dragon["raw_reason_rows"],
        "eastmoney_unique_security_count": dragon["unique_security_count_including_bse_and_convertibles"],
        "ths_summary_rows": dragon["ths_summary_unique_rows"],
        "observation_samples": selected, "previous_sample_validations": prior,
    }


def build_combined(evidence, stamp_cn, rid, component_ids):
    deep = evidence["volume_price"]["deep_samples"]
    index = {row["code"]: row for row in deep}
    fsp, enjie = index["000973"], index["002812"]
    body = f"""一、唯一决定、组别与时间轴

交易日T={T}；计划介入日T+1=2026-10-16；若10月16日真实买入，周末不计交易日，最早可执行卖出日T+2=2026-10-19。唯一决策id={REPORT_IDS['combined_pair']}，组别“综合盘后组”，模型combined_limitup_watch_v4。本次冻结两只条件观察：000973佛塑科技、002812恩捷股份；盘后名单不是开盘即买，竞价后不满足条件则0只触发。

二、四份同日完整研究与回执

{md_table(['模块','报告id','交易日','完整性','对终选的作用'], [
    ['市场复盘','market-review-20261015-close-v1',T,'全A5569/广泛120/深筛28','冰点强反对，要求市场修复与低追涨'],
    ['量价',component_ids['volume_price'],T,'28/28；上一池26/26','支持佛塑/恩捷，否定高位封板和尾盘回落'],
    ['低位启动',component_ids['low_position'],T,'历史18/18；新增6','两只120日位置约12%，同时保留失败反例'],
    ['龙虎榜',component_ids['dragon_tiger'],T,'66原因记录/62行摘要','对两只中性；否定高换手/高位替代'],
])}

量化痕迹任务已取消，不生成、不跟踪，也不作为前置。自动扫描和旧blocked审计未计为完整研究。四份报告均有各自同日completed回执后才形成本决策；市场复盘复用先前已完成的同日报告及回执，其余三项在本次补齐。

三、市场环境与证据冲突

10月15日上证-1.59%、深成指-2.43%、创业板-2.92%、科创50-1.50%；沪深成交约1.63万亿元但全市场5,108跌、仅429涨，36涨停、26—28跌停。昨日首板晋级2/21、二板及以上4/15，环境是冰点/系统性风险释放而非确认见底。这是两只共同的最大反对项：10月16日若跌停扩散、红盘不足或锂电/新材料无承接，两只都放弃。

量价正证据：佛塑RVOL20={fsp['rvol']['20']:.2f}、CLV={fsp['clv']:.3f}、120日位置{fsp['range_position_pct']['120']:.1f}%、14点后{signed(fsp['tail_return_1400_to_1500_pct'])}%；恩捷RVOL20={enjie['rvol']['20']:.2f}、CLV={enjie['clv']:.3f}、120日位置{enjie['range_position_pct']['120']:.1f}%、14点后{signed(enjie['tail_return_1400_to_1500_pct'])}%。低位组独立把两者列为新样本。龙虎榜没有两者当日上榜记录，故既无席位加分，也不能把“未上榜”当成卖出证据。

佛塑在收盘后披露前三季度业绩预告：预计归母净利润12—14亿元、扣非7.5—9.5亿元；增长主要受金力新能源并表推动，但公司同时明确约4.56亿元营业外收入为一次性、无对应现金流入，整合、竞争、原料和政策仍有不确定性。该公告增加次日催化，也显著增加高开/涨停排队买不到风险，不能只读增幅。

四、候选一：000973佛塑科技（优先级1）

模型：事件催化+低位放量推进+平台突破确认。冻结参考价12.19元（10月15日15:00收盘，不是成交价）；换手8.28%、RVOL20=3.02、CLV0.987、距MA20+3.8%、120日位置11.5%，近压12.38。胜过替代者的核心是价格/量/位置与同日晚间官方公告共振；反证是一次性收益占比、弱市、公告后高开不可执行和12.38压力。

10月16日确认：开盘11.90—12.45；先有普通连续成交，回踩11.80—12.00期间成交较上冲窗口收缩，随后重新站上12.20，并放量通过12.38；恩捷/凯盛新材至少一只不弱，跌停数不继续扩散。全部成立后只在12.20—12.38研究入场。

放弃：一字或无普通成交；高开/可见成交已高于12.65；开盘区间不符；回踩放量破11.80或盘中跌破11.45；12.38附近放量不进；新材料/隔膜批量转弱。失效位11.45。若10月16日买后跌破，A股T+1不能当天卖：停止加仓、保留敞口，最早10月19日首个有流动性的时点处理，跌停/停牌/无成交不得按计划价虚构退出。

T+2退出：10月19日弱开或仍低于11.45，首个可成交时点优先退出；保持12.38上方且板块同步时，12.80与13.35—13.41分批观察，不以最高价作成交。按10%制度用12.19静态估算的理论涨停约13.41元，实际涨停价须以当日交易所/券商行情核验。路径假设是守11.80—12.00→重站12.20/12.38→隔膜方向扩散→12.80以上加速；反例为公告兑现高开回落、一次性收益被重新定价或高量滞涨。

五、候选二：002812恩捷股份（优先级2）

模型：低位容量修复+平台确认。冻结参考价48.39元；成交27.04亿元、换手6.92%、RVOL20=3.02、CLV0.846、距MA20+2.8%、120日位置12.0%。它胜过301069/300771在于容量和退出流动性，且相较封板股可等待普通成交；反证是MA20仍低于MA60、50元压力、没有同日公司级新公告，并与佛塑同属隔膜/新材料方向，不能视为分散。

10月16日确认：开盘47.40—49.20；47.40—47.90缩量回踩守住，随后重新站48.60，向49.00推进时成交扩张但价格不回落；隔膜/锂电材料不明显转弱，且市场不继续系统性下杀。成立后只在48.60—49.20研究入场。

放弃：高开或可成交已到50.00以上；跌破46.35；48.60上方量大价不进；板块仅佛塑一只受公告刺激而恩捷无跟随；市场跌停继续扩散。失效位46.35。若10月16日买后跌破，同样不能当天卖，只能最早10月19日处理。

T+2退出：10月19日弱开/低于46.35，首个可成交时点优先退出；保持50.00上方且成交连续时，50.00、51.00、52.80—53.20为分批观察。按48.39静态估算理论10%涨停约53.23元，实际价需核验。路径假设是守47.40→重站48.60/49.00→突破50→板块容量共振；反例为50元放量不进、佛塑高开兑现拖累板块、指数继续破位。

若两只同时满足，仍逐只核验普通成交和相关性；不把同主题两只当作风险分散。任何一只T+1直接涨停且没有成交证据，只记价格观察，不记买入或策略浮盈。

六、替代者与为何未换股

- 301069凯盛新材：低位与RVOL支持，但尾盘-0.71%、20%制度下T+1回撤风险和容量不如恩捷。
- 300771智莱科技：位置/CLV合格，但尾盘略弱、成交容量较小且没有同日官方催化。
- 688552航天南湖：龙虎榜与相对量正向，但距MA20+12.4%、科创板波动与高开兑现风险更高。
- 600869远东股份：榜单净买约2.64亿元、位置不高，但RVOL20仅1.19且日振幅上榜，未满足本轮量价组合。
- 002945华林证券、000530冰山冷热：封板、高相对量，但位置/换手和次日买不到风险高；不以涨停强度替代可执行性。
- 300410正业科技、300916朗特智能、中邮科技：单日涨12%—13%，中邮尾盘-4.75%，追高与T+1锁仓风险高。

本次最终两只与近三次有效综合组选股不重复；可核验有效历史组仍太少，不给稳定5/10日重复率。重新保留市场复盘原两只不是机械复制：低位、量价与官方公告复核后仍胜过替代者；龙虎榜则提供中性/反对而不是跟随理由。

七、上一综合组真实跟踪与发布后计划

上一完整综合组为10月12日先导智能300450。10月13日开36.21元，低于冻结开盘下界37.30元，必要条件失败，未触发、未成交，执行收益N/A。以原参考37.88元作价格观察，10月13/14/15收盘分别约-9.58%/-14.78%/-14.60%；这是未入场后的3交易日风险观察，不是策略亏损或可执行收益。

本组发布后冻结所有参考价、区间、触发和失效条件，只追加结果。10月16日记录竞价、开盘、9:45、10:30、午盘、14:00后与收盘；若真实满足条件，再从10月19日起记录首个可执行退出、20bp占位成本、MFE/MAE，并追加3/5/10/20/30交易日价格观察。缺分钟OHLC、盘口、排队和真实成交时，不推断触发顺序或成交。

独立limitup_single最新计划日D=2026-10-15已完成limitup_single_v2并给出空仓决定，本次复用、不重复补写，也不把它混入综合组。研究不保证收益。"""
    sources = [
        "docs/research/market-review-2026-10-15-evidence.json",
        "docs/research/combined-pair-2026-10-15-evidence.json",
        CNINFO_FOSU,
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        "https://web.ifzq.gtimg.cn/appstock/app/day/query",
        "https://data.10jqka.com.cn/market/longhu/date/2026-10-15/",
        "https://www.stcn.com/article/detail/4220898.html",
    ]
    return {
        "id": REPORT_IDS["combined_pair"], "date": T, "market_date": T,
        "task_id": "combined_pair", "track": "market_review", "report_type": "full_trading_research",
        "eligible_for_integrated_research": True, "strategy": "combined_limitup_watch",
        "model_version": "combined_limitup_watch_v4", "run_id": rid,
        "published_at": stamp_cn, "recorded_at": stamp_cn, "data_cutoff_at": stamp_cn,
        "title": "盘后综合双标｜2026-10-15 佛塑科技/恩捷股份条件观察",
        "summary": "四份同日完整研究与completed回执齐备；全A5569只入口、120只广泛池、28只深筛。冰点环境下冻结佛塑科技、恩捷股份两只严格条件观察，10月16日竞价后再验证。",
        "body": body, "sources": sources,
        "evidence_file": "docs/research/combined-pair-2026-10-15-evidence.json",
        "provenance": "contemporaneous_combined_decision", "codes": ["000973", "002812"],
        "selected_codes": ["000973", "002812"],
        "coverage": {"all_a_entry": 5569, "broad_pool": 120, "deep_reviewed": 28, "selected": 2, "full_market_complete": True},
        "deep_screen_samples": [fsp, enjie],
        "selection_comparison": ["301069", "300771", "688552", "600869", "002945", "000530", "300410", "300916", "688648"],
        "dependency_report_ids": ["market-review-20261015-close-v1", component_ids["volume_price"], component_ids["low_position"], component_ids["dragon_tiger"]],
        "integrated_prerequisite_policy": "market_review+volume_price+low_position+dragon_tiger; quant_research cancelled",
        "prior_group_status": evidence["prior_combined"],
        "planned_entry_date": "2026-10-16", "earliest_legal_exit_date_if_bought": "2026-10-19",
        "future_horizons": [1, 3, 5, 10, 20, 30],
    }


def recommendation(code, name, model_label, reason, reference, entry, invalid_price, trigger, invalid, exit_plan, limitup_path, stamp_cn, report_id, evidence_snapshot, sources):
    return {
        "id": f"combined-pair-20261015-{code}-close-v1", "date": T, "published_at": stamp_cn,
        "code": code, "name": name, "group": "close", "group_label": "综合盘后组",
        "strategy": "combined_limitup_watch", "task_id": "combined_pair", "model": "combined_limitup_watch_v4",
        "model_label": model_label, "reason": reason, "reference_price": reference,
        "reference_price_time": "2026-10-15T15:00:00+08:00", "reference_price_market_date": T,
        "reference_price_source": f"https://qt.gtimg.cn/q={'sh' if code.startswith('6') else 'sz'}{code}",
        "trigger": trigger, "invalid": invalid, "reference_entry_range": entry,
        "operational_invalid_price": invalid_price, "sources": sources,
        "provenance": "contemporaneous", "data_cutoff_at": stamp_cn,
        "planned_entry_date": "2026-10-16", "earliest_legal_exit_date_if_bought": "2026-10-19",
        "report_ids": [report_id], "evidence_snapshot": evidence_snapshot,
        "exit_plan": exit_plan, "limitup_path_hypothesis": limitup_path,
        "roundtrip_cost_assumption_bps": 20,
        "execution_note": "盘后候选不是开盘即买；T+1入场当日不能卖。无真实成交则策略收益N/A。",
        "results": [{
            "id": f"combined-pair-20261015-{code}-close-v1-frozen", "as_of": T,
            "recorded_at": stamp_cn, "market_date": "2026-10-16", "status": "pending_auction_revalidation",
            "trigger_status": "not_observable_before_auction", "entry_fill_status": "not_verified",
            "executed_trade": False, "executable_net_return_pct": None,
        }],
    }


def configure_tasks(tasks, stamp_utc):
    tasks["updated_at"] = stamp_utc
    by_id = {row["id"]: row for row in tasks["items"]}
    common_confirmed = stamp_utc
    market = by_id["market_review"]
    market.update(
        summary="市场、情绪、板块与全A深筛完整复盘；外部完整研究为主，GitHub局部证据只作兜底，局部扫描不冒充完整报告。",
        schedule_text="工作日盘后外部完整研究；北京时间17:17/18:17/19:17 GitHub局部证据仅作失败审计与补充",
        execution_mode="external_scheduled_full_research_with_github_partial_fallback",
        effective_enabled=True, full_executor_enabled=True, configuration_confirmed_at=common_confirmed,
    )
    for task_id, title in (("volume_price", "量价独立完整研究"), ("low_position", "低位启动独立完整研究"), ("dragon_tiger", "龙虎榜独立完整研究")):
        row = by_id[task_id]
        row.update(
            enabled=True,
            summary=f"{title}分别留档；同日缺项由盘后综合任务按完整要求补做，自动局部观察不满足综合前置。",
            schedule_text="盘后综合任务核对同日完整报告；缺项时完整补做并保留独立栏目和回执",
            schedule="COMBINED_PAIR_COMPONENT",
            timezone="Asia/Shanghai",
            timing_mode="dependency_driven",
            execution_mode="combined_pair_component_full_research_with_partial_fallback",
            effective_enabled=True,
            full_executor_enabled=True,
            executor_task_id="combined_pair",
            configuration_confirmed_at=common_confirmed,
        )
    combined = by_id["combined_pair"]
    combined.update(
        summary="盘后综合双标只在市场复盘、量价、低位与龙虎榜四份同日完整报告齐备后裁决；缺项由本任务实际补做，量化痕迹已取消。",
        schedule_text="盘后外部完整研究与补偿复查；GitHub局部证据只作审计，不能替代四份深度研究",
        dependencies=["market_review", "volume_price", "low_position", "dragon_tiger"],
        executes_missing_tasks=["market_review", "volume_price", "low_position", "dragon_tiger"],
        execution_mode="external_scheduled_full_research_with_github_partial_fallback",
        effective_enabled=True, full_executor_enabled=True,
        integrated_prerequisite_count=4, quant_research_required=False,
        configuration_confirmed_at=common_confirmed,
    )
    return tasks


def main():
    evidence = json.loads(EVIDENCE_PATH.read_text())
    now = datetime.now(timezone.utc)
    stamp_utc = utc_iso(now)
    stamp_cn = cn_iso(now)
    completed_at = stamp_utc

    research = load("research.json")
    recommendations = load("recommendations.json")
    runs = load("task_runs.json")
    volume_samples = load("volume_price_samples.json")
    low_samples = load("low_position_samples.json")
    tasks = load("tasks.json")

    existing_reports = {row["id"] for row in research["items"]}
    if REPORT_IDS["combined_pair"] in existing_reports:
        print(json.dumps({"status": "duplicate_skipped", "report_id": REPORT_IDS["combined_pair"]}, ensure_ascii=False))
        return

    rids = {task: run_id(task, now) for task in REPORT_IDS}
    volume_report = build_volume(evidence, stamp_cn, rids["volume_price"])
    low_report = build_low(evidence, stamp_cn, rids["low_position"])
    dragon_report = build_dragon(evidence, stamp_cn, rids["dragon_tiger"])
    combined_report = build_combined(evidence, stamp_cn, rids["combined_pair"], REPORT_IDS)
    research["items"].extend([volume_report, low_report, dragon_report, combined_report])

    deep_index = {row["code"]: row for row in evidence["volume_price"]["deep_samples"]}
    common_sources = combined_report["sources"]
    recs = [
        recommendation(
            "000973", "佛塑科技", "事件催化＋低位放量推进＋平台确认",
            "120日低位、RVOL20=3.02、CLV0.987、尾盘推进，并获同日晚间业绩预告催化；反证是一次性收益、冰点市场、12.38压力和高开买不到风险。",
            12.19, [12.20, 12.38], 11.45,
            "10月16日开盘11.90—12.45且有普通连续成交；11.80—12.00缩量守住后重站12.20并放量通过12.38；恩捷/凯盛至少一只不弱且跌停不扩散。成立后只在12.20—12.38研究入场。",
            "一字或无普通成交；高开/可成交价高于12.65；开盘区间不符；放量破11.80或跌破11.45；12.38量大价不进；隔膜/新材料批量转弱。任一发生即未触发。",
            "若10月16日真实触发，最早10月19日可卖。弱开或低于11.45时在首个有流动性时点优先退出；保持12.38上方时观察12.80与13.35—13.41分批。涨跌停/停牌无成交不得按计划价算退出。",
            "守11.80—12.00→重站12.20/12.38→隔膜方向扩散→12.80以上加速，才可能接近静态理论10%上限约13.41；公告兑现高开回落、一次性收益重估或高量滞涨为反例。",
            stamp_cn, REPORT_IDS["combined_pair"], deep_index["000973"], common_sources,
        ),
        recommendation(
            "002812", "恩捷股份", "低位容量修复＋平台确认",
            "120日低位、RVOL20=3.02、CLV0.846、27.04亿元成交提供容量；反证是MA20仍低于MA60、50元压力、无同日公司级新公告且与佛塑主题相关。",
            48.39, [48.60, 49.20], 46.35,
            "10月16日开盘47.40—49.20；47.40—47.90缩量守住后重站48.60，向49.00推进时量价同步；隔膜/锂电材料不弱且市场不继续系统性下杀。成立后只在48.60—49.20研究入场。",
            "高开/可成交价达到50.00以上；跌破46.35；48.60上方量大价不进；板块仅佛塑受公告刺激而恩捷无跟随；跌停扩散。任一发生即未触发。",
            "若10月16日真实触发，最早10月19日可卖。弱开或低于46.35时在首个有流动性时点优先退出；保持50.00上方时观察50.00、51.00、52.80—53.20分批。",
            "守47.40→重站48.60/49.00→突破50→容量共振，才可能接近静态理论10%上限约53.23；50元放量不进、佛塑兑现拖累板块或指数破位为反例。",
            stamp_cn, REPORT_IDS["combined_pair"], deep_index["002812"], common_sources,
        ),
    ]
    recommendations["items"].extend(recs)

    previous = next(row for row in recommendations["items"] if row["id"] == "combined-pair-20261012-300450-close-v1")
    if not any(result.get("id") == "combined-pair-20261012-300450-close-v1-d3-20261015" for result in previous.get("results", [])):
        observation = evidence["prior_combined"]["price_observations"][-1]
        previous.setdefault("results", []).append({
            "id": "combined-pair-20261012-300450-close-v1-d3-20261015",
            "as_of": T, "market_date": T, "recorded_at": stamp_cn, "horizon": 3,
            "status": "not_triggered_price_observation", "trigger_status": "opening_condition_failed_on_2026-10-13",
            "entry_fill_status": "no_valid_strategy_entry", "executed_trade": False,
            "executable_net_return_pct": None,
            "reason": "10月13日开盘低于冻结37.30元下界，原策略未入场；10月15日只追加3交易日价格观察。",
            "source_report_ids": [REPORT_IDS["combined_pair"]],
            "source_urls": ["https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz300450,day,,,180,qfq", "https://web.ifzq.gtimg.cn/appstock/app/day/query?code=sz300450"],
            "price_observation_only": True, "reference_price": previous["reference_price"],
            "open_return_pct": observation["open_return_pct"], "close_return_pct": observation["close_return_pct"],
            "daily_high_observation_pct": observation["high_observation_pct"], "daily_low_observation_pct": observation["low_observation_pct"],
            "executable_mfe_pct": None, "executable_mae_pct": None,
        })

    names = {row["code"]: row["name"] for row in evidence["volume_price"]["deep_samples"]}
    full_validations = []
    for row in evidence["volume_price"]["previous_validations"]:
        checkpoints = {clock: point["return_vs_prior_close_pct"] for clock, point in row["minute_checkpoints"].items()}
        full_validations.append({
            "id": f"volume-price-20261012-close-v1-cohort-{row['code']}-full-20261015",
            "code": row["code"], "name": names.get(row["code"], row["code"]), "date": row["validation_date"],
            "reference_date": row["reference_date"], "reference_close": row["reference_close_qfq"],
            "recorded_at": stamp_cn, "origin_cohort_id": "volume-price-20261012-close-v1-cohort",
            "report_ids": [REPORT_IDS["volume_price"]], "observation_type": "price_observation",
            "evidence_status": "verified_daily_and_historical_minute_price_points",
            "full_validation_completed": True, "eligible_for_model_statistics": True,
            "reference_verified_against_current_provider": True,
            "minute_checkpoints": row["minute_checkpoints"], "checkpoint_returns_pct": checkpoints,
            "trigger_status": row["trigger_status"], "entry_fill_status": "not_verified", "executed_trade": False,
            "executable_net_return_pct": None, "executable_mfe_pct": None, "executable_mae_pct": None,
            "source_urls": ["https://web.ifzq.gtimg.cn/appstock/app/fqkline/get", "https://web.ifzq.gtimg.cn/appstock/app/day/query"],
            "missing": ["auction_0925", "verified_minute_OHLC", "order_book", "fill", "legal_exit"],
            "open_return_pct": row["open_return_pct"], "daily_high_price_excursion_pct": row["high_observation_pct"],
            "daily_low_price_excursion_pct": row["low_observation_pct"], "close_return_pct": row["close_return_pct"],
            "price_observation_note": "完整日线与历史分钟价格点；不是触发后可执行收益。",
        })
    volume_samples["items"].append({
        "id": "volume-price-20261012-validation-full-20261015-v1", "date": T, "kind": "forward_validation",
        "task_id": "volume_price", "origin_cohort_id": "volume-price-20261012-close-v1-cohort",
        "origin_report_ids": ["volume-price-20261012-close-v1"], "report_ids": [REPORT_IDS["volume_price"]],
        "rule_version": "volume_price_close_v2", "recorded_at": stamp_cn,
        "full_pool_summary": evidence["volume_price"]["previous_statistics"], "executable_sample_count": 0,
        "full_pool_validations": full_validations, "full_validation_completed": True,
        "eligible_for_model_statistics": True,
    })
    volume_samples["items"].append({
        "id": "volume-price-20261015-close-v1-cohort", "date": T, "task_id": "volume_price",
        "report_ids": [REPORT_IDS["volume_price"]], "rule_version": "volume_price_close_v3",
        "frozen_at": stamp_cn, "data_cutoff_at": "2026-10-15T15:35:45+08:00",
        "provenance": "contemporaneous_close_research", "broad_pool_count": 120, "deep_screen_count": 28,
        "eligible_for_model_statistics": True, "samples": evidence["volume_price"]["deep_samples"],
    })

    low_index = {row["code"]: row for row in low_samples["items"]}
    for observation in evidence["low_position"]["existing_validations"]:
        if observation.get("status") == "unavailable":
            continue
        observation = dict(observation, recorded_at=stamp_cn)
        target = low_index[observation["code"]]
        if not any(old.get("id") == observation["id"] for old in target.get("observations", [])):
            target.setdefault("observations", []).append(observation)
    for row in evidence["low_position"]["new_candidates"]:
        code = row["code"]
        item_id = f"low-position-20261015-{code}"
        if item_id in {item["id"] for item in low_samples["items"]}:
            continue
        low_samples["items"].append({
            "id": item_id, "date": T, "code": code, "name": row["name"], "sector": low_sector(code),
            "day0_close": row["close"], "invalid_close_below": row["low"],
            "initial_invalidation_basis": "收盘跌破信号日低点，后续仅追加结果，不回写",
            "primary_model": "低中位放量推进/平台确认",
            "tags": ["底部放量启动", "平台突破", "量价共振"],
            "original_snapshot_provenance": "contemporaneous_market_scan_and_tencent_daily",
            "original_snapshot_verified": True, "eligible_for_model_statistics": True,
            "day0_change_pct": row["daily_change_pct"], "day0_turnover_pct": row["turnover_pct"],
            "day0_amount_yi": round(row["amount_cny"] / 100000000, 4),
            "day0_rvol5": row["rvol"]["5"], "day0_rvol10": row["rvol"]["10"], "day0_rvol20": row["rvol"]["20"],
            "day0_clv": row["clv"], "day0_amplitude_pct": row["amplitude_pct"],
            "day0_range_position_pct": row["range_position_pct"],
            "day0_moving_averages": {"ma5": row["ma"]["5"], "ma10": row["ma"]["10"], "ma20": row["ma"]["20"]},
            "observations": [],
            "sources": [row["daily_source"], "docs/research/market-review-2026-10-15-evidence.json", "docs/research/combined-pair-2026-10-15-evidence.json"] + ([CNINFO_FOSU] if code == "000973" else []),
        })
    low_samples["updated_at"] = stamp_cn

    for task in ("volume_price", "low_position", "dragon_tiger", "combined_pair"):
        rec_ids = [row["id"] for row in recs] if task == "combined_pair" else []
        report_id = REPORT_IDS[task]
        runs["items"].append({
            "id": rids[task] + "-completed", "run_id": rids[task], "task_id": task, "date": T,
            "trigger": "scheduled", "started_at": STARTED_AT, "completed_at": completed_at,
            "recorded_at": completed_at, "status": "completed",
            "summary": {
                "volume_price": "完成全A入口、28只深筛量价留档及上一26只完整前推；执行样本N=0。",
                "low_position": "完成18只历史样本全量节点并新增6只，30自然日到期0只。",
                "dragon_tiger": "完成66条原因记录、公开席位结构与上一5只前推验证。",
                "combined_pair": "四份同日完整研究齐备；冻结佛塑科技、恩捷股份两只10月16日条件观察。",
            }[task],
            "report_ids": [report_id], "recommendation_ids": rec_ids,
            "sources": ["docs/research/combined-pair-2026-10-15-evidence.json"],
            "analysis_completed": True, "eligible_for_integrated_research": True,
        })

    tasks = configure_tasks(tasks, stamp_utc)

    dump(DATA / "research.json", research)
    dump(DATA / "recommendations.json", recommendations)
    dump(DATA / "task_runs.json", runs)
    dump(DATA / "volume_price_samples.json", volume_samples)
    dump(DATA / "low_position_samples.json", low_samples)
    dump(DATA / "tasks.json", tasks)
    (ROOT / "docs/research/combined-pair-2026-10-15.md").write_text(combined_report["body"] + "\n")

    print(json.dumps({
        "status": "published_locally", "completed_at": completed_at, "recorded_at_cn": stamp_cn,
        "reports": [volume_report["id"], low_report["id"], dragon_report["id"], combined_report["id"]],
        "recommendations": [row["id"] for row in recs],
        "receipts": [rids[task] + "-completed" for task in REPORT_IDS],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
