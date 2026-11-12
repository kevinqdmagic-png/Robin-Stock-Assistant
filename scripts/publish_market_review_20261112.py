#!/usr/bin/env python3
"""Atomically append the complete 2026-11-12 market review and one 11/11 supplement."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
T, D, EXIT = "2026-11-12", "2026-11-13", "2026-11-16"
CN = ZoneInfo("Asia/Shanghai")
EVIDENCE = ROOT / "docs/research/market-review-20261112-evidence.json"
REPORT = ROOT / "docs/research/market-review-20261112-close-v1.md"
HIST = ROOT / "docs/research/market-review-20261111-event-ecosystem-supplement-v1.md"
RESEARCH = ROOT / "backend/data/research.json"
RUNS = ROOT / "backend/data/task_runs.json"
RID = "market-review-20261112-close-v1"
RUN_ID = "market-review-20261112-scheduled-close-v1"
RECEIPT = RUN_ID + "-completed"
HIST_RID = "market-review-20261111-event-ecosystem-supplement-v1"
HIST_RUN = "market-review-20261111-historical-event-supplement-v1"


def atomic_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp-market-review-20261112")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def f(v, n=2):
    return "N/A" if v is None else f"{v:.{n}f}"


def table(headers, rows):
    return "\n".join([
        "|" + "|".join(headers) + "|",
        "|" + "|".join(["---"] * len(headers)) + "|",
        *("|" + "|".join(str(v).replace("|", "/") for v in row) + "|" for row in rows),
    ])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    args = p.parse_args()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != args.base:
        raise ValueError(f"base_head_changed:{args.base}->{head}")

    ev = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    if ev["market_date"] != T or ev["snapshots"][T]["coverage"]["coverage_ratio"] < .99:
        raise ValueError("verified_current_evidence_required")
    if len(ev["broad_pool"]) != 120 or len(ev["deep_pool"]) != 28:
        raise ValueError("120_broad_and_28_deep_required")
    if ev["indices"]["status"] != "verified" or len(ev["indices"]["items"]) != 4:
        raise ValueError("four_verified_indices_required")

    stamp = datetime.now(timezone.utc).astimezone(CN).isoformat(timespec="seconds")
    stamp_min = stamp[:16].replace("T", " ")
    started = datetime.fromisoformat(ev["started_at"]).astimezone(CN).isoformat(timespec="seconds")
    scan = ev["market_scan"]
    idx = {r["name"]: r for r in ev["indices"]["items"]}
    pair = ev["relative_research_pair"]
    if [r["code"] for r in pair] != ["601789", "000882"]:
        raise ValueError("frozen_pair_changed")
    proxy = ev["limit_proxy"][T]
    ext = ev["external_close_crosscheck"]

    candidate_specs = {
        "601789": {
            "trigger": "11月13日09:35—10:30或14:00—14:40仅在3.94—3.87缩量承接后重新放量站上4.07，且基建/工程同向强度不弱于市场时继续观察。",
            "abandon": "较4.01高开超过3%（约4.13）不追；跌破3.87后不能回收、板块转弱或市场下行情景确认即放弃。",
            "risk": "仍低于MA60约4.16，4.20前高形成供给；本轮只有日线与历史日K，没有D日分钟、竞价或成交证明。",
        },
        "000882": {
            "trigger": "11月13日09:35—10:30或14:00—14:40仅在1.42—1.40承接后放量站稳1.52，且零售方向至少两只同向走强时继续观察。",
            "abandon": "高开到1.53以上不追；跌破1.40不能回收、低价股流动性恶化或板块孤立即放弃。",
            "risk": "低价股波动和滑点敏感，1.52为当日高点且20日位置已到80%；没有分钟顺序和公司公告穷尽核查。",
        },
    }
    candidate_sections = []
    shadow = []
    for r in pair:
        s = candidate_specs[r["code"]]
        candidate_sections.append(
            f"## **{r['name']}（{r['code']}）**\n\n"
            f"资格：**market_review待综合观察**，不是最终研究双标、正式买点或买入许可。参考价 **{r['close']:.2f}元**，实际时点为北京时间{T} 15:00；若D={D}真实入场，A股T+1最早{EXIT}退出。\n\n"
            f"当日涨跌{r['pct']:+.2f}%，RVOL5/10/20={r['rvol5']:.2f}/{r['rvol10']:.2f}/{r['rvol20']:.2f}，CLV={r['clv']:.3f}，120日位置{r['position120']*100:.1f}%。\n\n"
            f"触发观察：{s['trigger']}\n\n放弃：{s['abandon']}\n\n风险：{s['risk']}"
        )
        shadow.append({
            "task_id": "market_review", "code": r["code"], "name": r["name"],
            "reference_price": r["close"], "reference_as_of": f"{T}T15:00:00+08:00",
            "actual_frozen_at": stamp, "planned_observation_date": D,
            "earliest_legal_exit_if_entered": EXIT, "candidate_status": "pending_integrated_review_not_final",
            "formal_buy_signal": False, "buy_order_allowed": False,
            "trigger_condition": s["trigger"], "abandon_condition": s["abandon"], "risk": s["risk"],
        })

    deep_table = table(
        ["代码/名称", "收盘", "涨跌%", "RVOL5/10/20", "120日位置%", "CLV", "结构"],
        [[r["code"] + " " + r["name"], f(r["close"]), f(r["pct"]),
          "/".join(f(r[x]) for x in ("rvol5", "rvol10", "rvol20")),
          f(r["position120"] * 100, 1), f(r["clv"], 3), "、".join(r["tags"])] for r in ev["deep_pool"]],
    )
    indices_table = table(
        ["指数", "收盘", "涨跌%", "日高/日低", "源时间戳"],
        [[r["name"], f(r["close"]), f(r["change_pct"]), f(r["high"]) + "/" + f(r["low"]), r["quote_time"]]
         for r in ev["indices"]["items"]],
    )
    body = (
        f"研究交易日：{T}｜发布时间：北京时间 {stamp_min}（UTC+8）\n\n"
        + "\n\n".join(candidate_sections)
        + f"\n\n**资格总说明：**以上两只只是本模块从120只冻结广池、28只深池中得到的相对研究样本；最终综合尚未执行，正式买点0只源于D日竞价、板块和分钟承接尚未出现，不代表市场确定没有机会。\n\n"
        "## 一、市场事实与情绪\n\n"
        f"本次沪深股票（排除北交所）检查{ev['snapshots'][T]['coverage']['checked']}只、有效{scan['verified']}只，覆盖率{ev['snapshots'][T]['coverage']['coverage_ratio']:.3%}；"
        f"上涨{scan['advances']}、下跌{scan['declines']}、平盘{scan['flat']}，中位涨跌{scan['median_change_pct']:.3f}%。股票成交额简单加总{scan['amount_yuan']/1e8:.2f}亿元，较11月11日同口径{scan['amount_change_pct']:+.2f}%。该数为沪深股票快照求和，不冒充含ETF/北交所的交易所总额。\n\n"
        + indices_table
        + f"\n\n上证和深市成长指数收跌，科创50逆势{idx['科创50']['change_pct']:+.2f}%；在成交放大{scan['amount_change_pct']:.2f}%的同时，仅{scan['advances']}只上涨，属于放量分歧/风险释放，而非无量阴跌。\n\n"
        f"独立公开复盘页收盘口径为涨停{ext['current_counts_observed']['limit_up']}、炸板{ext['current_counts_observed']['broken']}、封板率{ext['current_counts_observed']['seal_rate_pct']}%、最高{ext['current_counts_observed']['highest_board']}板；"
        f"1进2为{ext['current_counts_observed']['one_to_two']}、2进3为{ext['current_counts_observed']['two_to_three']}、高位晋级{ext['current_counts_observed']['higher']}。前日分别为涨停{ext['previous_counts_observed']['limit_up']}、炸板{ext['previous_counts_observed']['broken']}、封板率{ext['previous_counts_observed']['seal_rate_pct']}%。"
        "涨停数量骤降、炸板上升和中低位晋级走弱共同说明情绪从11日扩散转为12日强分歧；最高板由4板升到5板只说明局部高度延续，不能代表全市场接力改善。\n\n"
        f"本地收盘代理另复算封板{proxy['sealed_up']}、触板{proxy['touched_up']}、触板未封{proxy['broken_after_touch']}、跌停{proxy['sealed_down']}。代理包含ST分制度并按0.01元复算，和第三方事件表分母不同，二者不混算。东财三类事件池均是HTTP200但rc=205/data=null，明确记失败。\n\n"
        "## 二、主线、强弱与持续性\n\n"
        "机器人仍是事件数量最大的主题，但较11日从大面积封板转为封板与炸板并存；光通信、PCB从11日扩散转为12日多只冲高未封，属于强转分歧。股权/重组、东方/羊字辈和消费保留局部连板高度，更多体现小范围抱团。半导体链早盘活跃且科创50收红，是当日最明确的相对强方向；贵金属与多数个股走弱，深成指、创业板和4320只下跌构成弱面对照。\n\n"
        "持续性判断：题材高度尚未完全塌陷，但宽度、封板率和中低位晋级同步恶化；次日需优先验证分歧后承接，不应把5板高度或科创50单指数收红解释成新上升周期。\n\n"
        "## 三、120只广池与28只深筛\n\n"
        "全沪深扫描后先按成交活跃、量能变化、涨跌与日内收盘位置冻结120只广池，再请求新浪150根未复权日线，120/120成功；随后固定28只深筛。RVOL分母仅含T以前的5/10/20个完成交易日，CLV只表示收盘在日内区间的位置，不证明分钟先后。\n\n"
        + deep_table
        + "\n\n被替代候选至少包括：长联科技301618（+14.07%，20%制度下追高与D可得性风险）、中重科技603135（收盘封板，次日普通可得性未证）、华东重机002685（RVOL20=5.04但CLV仅0.375，放量未能维持高位）、仁东控股002647（位置低但当日+6.94%，隔夜回撤更大）。相对排序不靠降低重复率硬换股票。\n\n"
        "## 四、涨停生态与公告风险\n\n"
        "公开收盘复盘页给出的最高5板为日出东方与大东方；本地三日收盘代理只能证明部分标的至少连续3日封板，不能用三日窗口冒充完整5板统计。前日代理封板87只中仅12只当日仍封板，13.79%是同代码收盘封板留存率，不等于首板晋级率。\n\n"
        "公告风险方面，上交所检索显示日出东方9月23日有董事及高级管理人员减持计划；天普股份10月30日风险提示称市净率显著高于行业，且证监会此前已就其异常波动公告涉嫌重大遗漏立案调查。它们都是高标风险反证，不能因连板标签消除；公告检索不是穷尽性风险证明。\n\n"
        "## 五、D=2026-11-13 三情景（事前冻结，无概率）\n\n"
        "- **上行修复**：上证重新站上3680并保持30分钟，深成指站上11300、创业板站上2550；上涨超过3000只、同口径成交不低于1.80万亿元且炸板率明显低于12日。若上涨不足2000或创业板再失2500则失效。\n"
        "- **震荡消化**：上证主要在3635—3680、深成指11100—11300、创业板2480—2550运行；上涨约1800—3000只、成交1.50—1.90万亿元，题材轮动但跌停不扩散。指数和宽度同时突破任一侧阈值则失效。\n"
        "- **下行延续**：上证跌破3647并30分钟不能收回，深成指跌破11190或创业板跌破2508；下跌超过4000只且跌停/炸板继续扩散。若上证收复3670并且上涨超过2800只则失效。\n\n"
        "阈值未做概率校准，不编造概率；下次只核验触发与失效，不回看改写。\n\n"
        "## 六、来源、失败与研究边界\n\n"
        f"- BaoStock单连接实际失败：10002007网络接收错误；证据见`backend/data/market_source_status/baostock-2026-11-12.json`。\n"
        f"- 新浪沪深收盘快照有效{scan['verified']}/{ev['snapshots'][T]['coverage']['checked']}，7只缺失保留；新浪历史日K 120/120。\n"
        "- 腾讯四指数均带20261112收盘后时间戳；东方财富行业Top100超时、三类事件池rc=205/data=null。\n"
        "- 独立市场复盘页用于涨停、炸板、连板与板块交叉；本地代理用于可复算对照，源口径不混合。\n"
        "- 没有用日线高低补造09:50/14:40触发、成交或退出；候选无实际成交，真实胜率和净收益为空。最终综合需等待同T四项完整上游、学习和独立打板材料，APP不会自动调权或交易。"
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("# 2026-11-12 A股市场复盘\n\n" + body + "\n", encoding="utf-8")

    hist_body = (
        f"研究交易日：2026-11-11｜补做发布时间：北京时间 {stamp_min}（UTC+8）\n\n"
        "本补证只推进11月11日原market_review的事件生态缺口，不改写原partial报告，也不把补证本身升级为完整同日研究。"
        "本次实际访问独立公开收盘复盘页，取得11月11日涨停84、炸板19、封板率82%、最高4板；1进2为9/62、2进3为5/15、高位2/5。"
        "机器人25只为最强扩散方向，光通信10只、股权重组9只、传媒8只；与11月12日37涨停/35炸板/51%封板率形成可核反转。"
        "东财11月11日三类事件池历史重试仍为HTTP200但rc=205/data=null，错误继续保留。该补证完成事件生态与次日反馈对照，"
        "但原报告仍缺当时完整分钟、交易所官方事件表等证据，eligible_for_integrated_research保持false。"
    )
    HIST.write_text("# 2026-11-11 市场事件生态历史补证\n\n" + hist_body + "\n", encoding="utf-8")

    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    runs = json.loads(RUNS.read_text(encoding="utf-8"))
    for item_id in (RID, HIST_RID):
        if any(x.get("id") == item_id for x in research["items"]):
            raise ValueError("duplicate_report:" + item_id)
    for item_id in (RECEIPT, HIST_RUN + "-receipt"):
        if any(x.get("id") == item_id for x in runs["items"]):
            raise ValueError("duplicate_receipt:" + item_id)

    sources = [
        str(REPORT.relative_to(ROOT)), str(EVIDENCE.relative_to(ROOT)),
        f"backend/data/sina_daily_full/{T}.json", "backend/data/market_source_status/baostock-2026-11-12.json",
        "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688",
        "https://www.kanpanba.com/limit/2026-11-12", "https://www.kanpanba.com/limit/2026-11-11",
        "https://www.sse.com.cn/home/search/?webswd=603366",
        "https://www.sse.com.cn/home/search/index.shtml?webswd=%E5%B8%82%E5%87%80%E7%8E%87",
    ]
    research["items"].append({
        "id": RID, "date": T, "market_date": T, "task_id": "market_review", "track": "market_review",
        "run_id": RUN_ID, "title": "每日复盘｜11月12日放量分歧、宽度退潮与科创相对强",
        "summary": f"沪深{scan['verified']}/{ev['snapshots'][T]['coverage']['checked']}只；上涨{scan['advances']}、下跌{scan['declines']}，成交{scan['amount_yuan']/1e8:.1f}亿元。冻结120广池/28深池，宁波建工与华联股份仅待综合观察；正式买点0只。",
        "body": body, "sources": sources, "report_type": "full_daily_research",
        "eligible_for_integrated_research": True, "analysis_completed": True, "status": "completed",
        "published_at": stamp, "recorded_at": stamp, "data_cutoff_at": stamp,
        "market_data_cutoff_at": f"{T}T15:00:00+08:00", "provenance": "contemporaneous_after_close_research",
        "research_rule_version": ev["research_rule_version"], "candidate_count": 2,
        "candidate_scope": "market_review_pending_integrated_review_not_final", "recommendation_ids": [],
        "research_shadow_codes": [r["code"] for r in pair], "research_shadow_candidates": shadow,
        "codes": [r["code"] for r in ev["deep_pool"]], "full_scan_count": scan["verified"],
        "broad_pool_count": 120, "broad_pool_verified_count": 120, "deep_pool_count": 28,
        "planned_entry_date": D, "earliest_legal_exit_date_if_bought": EXIT,
        "evidence_file": str(EVIDENCE.relative_to(ROOT)), "formal_buy_signal_count": 0,
        "source_failures_preserved": list(ev["blocked"].values()),
    })
    research["items"].append({
        "id": HIST_RID, "date": "2026-11-11", "market_date": "2026-11-11", "task_id": "market_review", "track": "market_review",
        "run_id": HIST_RUN, "title": "11月11日市场事件生态历史补证（不升级原partial）",
        "summary": "补得11月11日涨停84、炸板19、封板率82%、最高4板和晋级分母，并与11月12日反馈对照；原完整研究资格不变。",
        "body": hist_body, "sources": [str(HIST.relative_to(ROOT)), "https://www.kanpanba.com/limit/2026-11-11", str(EVIDENCE.relative_to(ROOT))],
        "report_type": "historical_evidence_supplement", "eligible_for_integrated_research": False,
        "analysis_completed": False, "status": "partial", "published_at": stamp, "recorded_at": stamp,
        "data_cutoff_at": stamp, "provenance": "cross_day_historical_evidence_supplement",
        "original_report_ids_unchanged": ["manual-recovery-20261111-market_review-v1"],
    })
    runs["items"].append({
        "id": RECEIPT, "run_id": RUN_ID, "task_id": "market_review", "date": T, "trigger": "scheduled",
        "started_at": started, "completed_at": stamp, "recorded_at": stamp, "status": "completed",
        "summary": f"完整完成T={T}沪深{scan['verified']}只市场复盘、120广池、28深筛、情绪/主线/公告/三情景及2只待综合观察；报告{RID}。",
        "report_ids": [RID], "recommendation_ids": [], "analysis_completed": True,
        "eligible_for_integrated_research": True, "trade_executed": False,
        "delivery_status": "repository_prepared_not_yet_verified", "sources": sources,
    })
    runs["items"].append({
        "id": HIST_RUN + "-receipt", "run_id": HIST_RUN, "task_id": "market_review", "date": "2026-11-11", "trigger": "manual",
        "started_at": started, "completed_at": stamp, "recorded_at": stamp, "status": "partial",
        "summary": "实质补得11月11日事件生态和次日反馈；原同日报告仍非完整前置，不改写历史状态。",
        "report_ids": [HIST_RID], "recommendation_ids": [], "analysis_completed": False,
        "eligible_for_integrated_research": False, "trade_executed": False,
        "delivery_status": "repository_prepared_not_yet_verified",
        "sources": [str(HIST.relative_to(ROOT)), "https://www.kanpanba.com/limit/2026-11-11"],
    })
    atomic_json(RESEARCH, research)
    atomic_json(RUNS, runs)
    print(json.dumps({"report_id": RID, "receipt_id": RECEIPT, "historical_supplement": HIST_RID, "published_at": stamp}, ensure_ascii=False))


if __name__ == "__main__":
    main()
