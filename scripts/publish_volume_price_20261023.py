#!/usr/bin/env python3
"""Append the complete 2026-10-23 volume/price report, cohort, and receipt."""

from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
T = "2026-10-23"
REPORT_ID = "volume-price-20261023-close-v1"
RUN_ID = "volume-price-20261023-scheduled-close-v1"
EVIDENCE = "docs/research/volume-price-20261023-close-evidence.json"


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def save(path, value):
    (ROOT / path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def line(x):
    return (f"{x['code']} {x['name']}：收盘{x['trade']}，{x['changepercent']:+.2f}%，"
            f"换手{x['turnoverratio']:.2f}%，RVOL5/10/20="
            f"{x['rvol5']:.2f}/{x['rvol10']:.2f}/{x['rvol20']:.2f}，"
            f"CLV={x['clv']:.3f}，距MA20 {x['dist_ma20']:+.2f}%，"
            f"14:00后{x['tail_1400_close_pct']:+.2f}%。")


def main():
    research = load("backend/data/research.json")
    runs = load("backend/data/task_runs.json")
    volume = load("backend/data/volume_price_samples.json")
    evidence = load(EVIDENCE)
    if any(x.get("id") == REPORT_ID for x in research["items"]):
        print("already published")
        return

    started_utc = evidence["retrieved_at_utc"]
    now = datetime.now(timezone.utc)
    stamp_utc = now.isoformat(timespec="seconds")
    stamp_cn = now.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    deep = evidence["deep_pool"]
    prior = evidence["previous_pool_validation"]
    stats = evidence["previous_pool_statistics"]
    by_code = {x["code"]: x for x in deep}

    typical_codes = ["300184", "300503", "603448", "301707", "688500"]
    typical = [by_code[c] for c in typical_codes]
    high_divergence = [x for x in deep if x["dist_ma20"] >= 25]
    near_ma = [x for x in deep if x["dist_ma20"] <= 6 and x["rvol20"] >= 3 and x["clv"] >= .75]
    low_volume_rebound = [x for x in deep if x["rvol20"] < 2]
    weakest = sorted(prior, key=lambda x: x["close_pct"])[:5]
    strongest = sorted(prior, key=lambda x: x["close_pct"], reverse=True)[:5]

    deep_lines = "\n".join(f"- {line(x)}" for x in deep)
    typical_text = "\n".join(f"- {line(x)}" for x in typical)
    body = f"""一、范围与数据口径

T={T}，收盘数据截止北京时间15:00。本次全A入口5573只有效记录，独立保留120只广泛研究池和28只深筛池；逐只记录收盘、涨跌、换手、相对前5/10/20个已完成交易日均量、CLV、距MA20、14:00后价格变化及六个时点快照。全市场4525涨、909跌、139平，成交额约1.9724万亿元。普通非ST主板代理口径为66只封板、87只触板、21只触板未封、11只跌停；不同媒体全市场涨跌停口径不可与该代理混算。

相对量采用完整日成交量除以前5/10/20个已完成交易日均量；CLV=(收盘-最低)/(最高-最低)，区间为零时记不适用。本报告没有把盘口形态解释为确定资金身份。六个时点只是快照，并非完整分钟OHLC，不能证明杀跌、承接、回踩、突破的先后顺序。

二、上一交易日冻结28只的完整T+1价格验证

10月22日冻结池28/28取得10月23日日线。收涨{stats['positive_close_count']}/28，收盘观察均值{stats['mean_close_pct']:+.3f}%、中位{stats['median_close_pct']:+.3f}%；相对前收的日内高点观察均值{stats['mean_mfe_pct']:+.3f}%、低点观察均值{stats['mean_mae_pct']:+.3f}%，其中{stats['mae_le_minus5_count']}只盘中低点不利幅度达到或超过5%。最强收盘：{', '.join(x['code']+' '+x['name']+f" {x['close_pct']:+.2f}%" for x in strongest)}。最弱收盘：{', '.join(x['code']+' '+x['name']+f" {x['close_pct']:+.2f}%" for x in weakest)}。

这组数据出现“收盘多数上涨但盘中不利波动仍深”的并存：反弹日改善了收盘分布，却没有消除T+1退出路径风险。由于缺10月23日完整分钟线、竞价、触发顺序和真实成交，可执行成交N=0；MFE/MAE只是相对冻结收盘的价格观察，胜率、盈亏比、成本后收益和9:50/14:40退出质量均不计算。

三、当日28只深筛全量记录

{deep_lines}

四、五个典型结构与反例

{typical_text}

力源信息与昊志机电同时满足“距MA20不超过6%、RVOL20大于3、CLV大于0.75”，属于低/中位放量推进的待验证组；但两者均为20%制度股票，且今日属于全市场普涨修复，不能把单日共振写成已确认启动。天博智能距MA20为负且收于区间上沿，但RVOL20仅1.83且接近10%封板，量能确认不足、普通成交可得性也弱。展芯股份距MA20约-8.38%、上涨11.33%，但RVOL20仅1.61，暂归“缩量反弹/待确认”，不是放量突破。慧辰股份RVOL20约4.21但CLV仅0.63、距MA20约+37.4%，大成交后价格推进质量弱于同组，是高位放量风险对照。

28只中距MA20≥25%的高乖离样本{len(high_divergence)}只；RVOL20<2的量能不足反弹样本{len(low_volume_rebound)}只；近MA20且高相对量、高CLV样本{len(near_ma)}只。前两类不因涨幅靠前自动晋级，后一类也只进入次日观察，不直接进入综合双标。

五、对全A筛选与下一步假设

当日有效信息是“市场宽度修复后，高相对量和强收盘广泛出现”，因此量价因子的区分度下降；应优先比较低乖离推进与高乖离封板，而不是按涨幅排序。10月26日9:25后，只有市场宽度未迅速恶化、所属板块同步、竞价不过度高开、回踩缩量且重新站回关键位，力源信息/昊志机电组才保留观察；天博智能若一字或明显不可成交直接放弃，展芯股份若不能补量确认则继续列为反例。

冻结三项可证伪假设：H6，普涨修复日中“距MA20≤6%、RVOL20>3、CLV>0.75”的样本，后续退出质量是否优于高乖离封板组；H7，RVOL20<2的大涨样本次日若不能补量，是否更易冲高回落；H8，上一冻结池收盘转正但MAE≤-5%的样本，次日开盘/9:45/10:30退出质量是否显著差于低MAE组。样本外验证前不改规则或权重，也不编造概率。

六、T+1与统计边界

10月23日盘后信号若在10月26日实际入场，最早10月27日卖出。APP档案只保存研究证据，不自动下单，不内置大模型或自动权重训练。本次新增28只冻结样本，待下个交易日逐只追加竞价、开盘、时段与收盘验证；当前可执行策略样本仍为0，不保证收益。"""

    report = {
        "id": REPORT_ID, "date": T, "market_date": T, "task_id": "volume_price", "track": "volume_price",
        "title": "量价完整研究｜10月23日全A5573只扫描、28只深筛与前池28只验证",
        "summary": f"全A5573只、广泛池120只、深筛28只；前池28/28验证，收盘中位{stats['median_close_pct']:+.3f}%，可执行成交N=0。",
        "body": body, "sources": [EVIDENCE, "docs/research/low-dragon-2026-10-23-market-scan.json",
                                           "https://qt.gtimg.cn/", "https://web.ifzq.gtimg.cn/appstock/app/kline/kline"],
        "report_type": "full_daily_research", "eligible_for_integrated_research": True,
        "published_at": stamp_cn, "recorded_at": stamp_cn, "data_cutoff_at": f"{T}T15:00:00+08:00",
        "run_id": RUN_ID, "evidence_file": EVIDENCE, "provenance": "contemporaneous_close_research",
        "rule_version": "volume_price_close_v4", "broad_pool_count": 120, "deep_pool_count": 28,
        "previous_pool_verified_count": 28, "executed_trade_count": 0,
        "codes": [x["code"] for x in deep], "next_validation_date": "2026-10-26",
    }
    research["items"].append(report)

    validation = {
        "id": "volume-price-20261022-validation-20261023-v1", "date": T,
        "recorded_at": stamp_cn, "task_id": "volume_price", "kind": "full_forward_price_validation",
        "origin_cohort_id": evidence["previous_cohort_id"], "origin_report_ids": ["volume-price-20261022-close-v1"],
        "report_ids": [REPORT_ID], "rule_version": "volume_price_close_v4", "full_validation_completed": True,
        "full_pool_summary": stats, "full_pool_validations": prior,
        "executed_trade_count": 0, "executable_strategy_statistics": None,
    }
    cohort = {
        "id": "volume-price-20261023-close-v1-cohort", "date": T, "task_id": "volume_price",
        "frozen_at": stamp_cn, "report_ids": [REPORT_ID], "rule_version": "volume_price_close_v4",
        "data_cutoff_at": f"{T}T15:00:00+08:00", "broad_pool_count": 120,
        "broad_pool_verified_count": 120, "deep_screen_count": 28,
        "deep_adjusted_history_verified_count": 28, "eligible_for_model_statistics": True,
        "provenance": "contemporaneous_full_market_research", "samples": deep,
    }
    volume["items"].extend([validation, cohort])
    volume["validation_status"] = "append_only_forward_validation_current_through_2026-10-23"

    runs["items"].append({
        "id": RUN_ID + "-completed", "run_id": RUN_ID, "task_id": "volume_price", "date": T,
        "trigger": "scheduled", "started_at": started_utc, "recorded_at": stamp_utc,
        "completed_at": stamp_utc, "status": "completed", "summary": report["summary"],
        "report_ids": [REPORT_ID], "recommendation_ids": [], "analysis_completed": True,
        "eligible_for_integrated_research": True, "delivery_status": "repository_prepared_not_yet_verified",
        "sources": [EVIDENCE],
    })

    save("backend/data/research.json", research)
    save("backend/data/task_runs.json", runs)
    save("backend/data/volume_price_samples.json", volume)
    save("docs/research/volume-price-20261023-close-v1.json", report)
    print(json.dumps({"report_id": REPORT_ID, "run_id": RUN_ID, "deep": len(deep), "prior": stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
