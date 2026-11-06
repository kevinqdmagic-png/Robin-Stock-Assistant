#!/usr/bin/env python3
"""Publish the source-bounded 2026-11-06 volume/price close study."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
T = "2026-11-06"
CN = ZoneInfo("Asia/Shanghai")
REPORT_ID = "volume-price-20261106-partial-v1"
RUN_ID = "volume-price-20261106-scheduled-close-v1"
RECEIPT_ID = RUN_ID + "-partial"
MR_EVIDENCE = ROOT / "docs/research/market-review-20261106-evidence.json"
EVIDENCE = ROOT / "docs/research/volume-price-20261106-evidence.json"
REPORT = ROOT / "docs/research/volume-price-20261106-partial-v1.md"
EM_STATUS = ROOT / "backend/data/market_source_status/eastmoney-market-2026-11-06.json"
ISSUE = "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/25"


def now_pair() -> tuple[str, str]:
    utc = datetime.now(timezone.utc)
    return utc.isoformat(timespec="seconds").replace("+00:00", "Z"), utc.astimezone(CN).isoformat(timespec="seconds")


def mean(values):
    return round(statistics.mean(values), 3) if values else None


def median(values):
    return round(statistics.median(values), 3) if values else None


def fmt(value, digits=2):
    return "N/A" if value is None else f"{value:.{digits}f}"


def intraday_summary(code: str, raw: dict) -> dict:
    bars = raw[code]["bars"]
    parsed = []
    for bar in bars:
        parsed.append({
            "time": bar["day"],
            "open": float(bar["open"]),
            "high": float(bar["high"]),
            "low": float(bar["low"]),
            "close": float(bar["close"]),
            "volume": float(bar["volume"]),
            "amount": float(bar["amount"]),
        })
    low_bar = min(parsed, key=lambda row: row["low"])
    high_bar = max(parsed, key=lambda row: row["high"])
    at_1440 = next((row for row in parsed if row["time"].endswith("14:40:00")), None)
    tail = [row for row in parsed if row["time"] >= T + " 14:40:00"]
    before_tail = [row for row in parsed if row["time"] < T + " 14:40:00"]
    tail_avg_volume = statistics.mean(row["volume"] for row in tail) if tail else None
    prior_avg_volume = statistics.mean(row["volume"] for row in before_tail) if before_tail else None
    return {
        "code": code,
        "provider": "Sina 5-minute historical K-line",
        "url": raw[code]["url"],
        "bar_count": len(parsed),
        "first_bar_time": parsed[0]["time"],
        "last_bar_time": parsed[-1]["time"],
        "day_low": low_bar["low"],
        "day_low_bar_time": low_bar["time"],
        "day_high": high_bar["high"],
        "day_high_bar_time": high_bar["time"],
        "close": parsed[-1]["close"],
        "recovery_from_low_to_close_pct": round((parsed[-1]["close"] / low_bar["low"] - 1) * 100, 3),
        "close_vs_1440_pct": round((parsed[-1]["close"] / at_1440["close"] - 1) * 100, 3) if at_1440 else None,
        "tail_5m_volume_vs_prior_avg": round(tail_avg_volume / prior_avg_volume, 3) if tail_avg_volume and prior_avg_volume else None,
        "historical_only": True,
        "executed_trade": False,
        "note": "收盘后取得的历史5分钟OHLCV，只用于复盘顺序；不是原时点报价或成交证明。",
    }


def main() -> None:
    started_utc, started_cn = now_pair()
    mr = json.loads(MR_EVIDENCE.read_text(encoding="utf-8"))
    em_raw = json.loads(Path("/tmp/em_pages.json").read_text(encoding="utf-8"))
    minute_raw = json.loads(Path("/tmp/vp_5m.json").read_text(encoding="utf-8"))
    if mr["market_date"] != T or len(mr["broad_pool"]) != 120 or len(mr["deep_pool"]) != 28:
        raise ValueError("invalid_market_review_evidence")

    em_map = {row.get("f12"): row for row in em_raw["rows"] if row.get("f12")}
    deep = []
    for raw in mr["deep_pool"]:
        row = dict(raw)
        em = em_map.get(row["code"])
        row["turnover_pct"] = em.get("f8") if em else None
        row["eastmoney_volume_ratio"] = em.get("f10") if em else None
        row["industry"] = em.get("f100") if em else None
        row["eastmoney_close"] = em.get("f2") if em else None
        row["eastmoney_close_crosscheck_abs"] = round(abs(float(em["f2"]) - float(row["close"])), 4) if em and em.get("f2") not in (None, "-") else None
        row["turnover_note"] = "东方财富收盘行情字段；按T日收盘价与新浪交叉核对" if em else "东方财富分页缺失，未反推"
        deep.append(row)

    minute_codes = ["600644", "603706", "600744", "002529", "002309"]
    minute = [intraday_summary(code, minute_raw) for code in minute_codes]
    minute_map = {row["code"]: row for row in minute}
    names = {row["code"]: row["name"] for row in deep}
    prior = mr["prior_20261105_pool_validation"]
    observed = [row for row in prior if row.get("status") == "daily_price_observed"]
    close_values = [row["close_pct"] for row in observed]
    mfe_values = [row["mfe_pct"] for row in observed]
    mae_values = [row["mae_pct"] for row in observed]
    positive_n = sum(v > 0 for v in close_values)

    em_deep_verified = sum(row["turnover_pct"] is not None and row["eastmoney_close_crosscheck_abs"] <= 0.03 for row in deep)
    EM_STATUS.write_text(json.dumps({
        "provider": "Eastmoney close market list HTTPS",
        "trade_date": T,
        "attempted_at": started_utc,
        "scope": "Shanghai+Shenzhen; Beijing excluded",
        "pages_requested": 56,
        "pages_verified": 56 - len(em_raw["errors"]),
        "page_errors": em_raw["errors"],
        "rows_received": len(em_raw["rows"]),
        "unique_codes": len(em_map),
        "deep_pool_requested": 28,
        "deep_pool_turnover_verified": em_deep_verified,
        "deep_pool_close_crosscheck_tolerance": 0.03,
        "fields": ["close", "pct", "volume", "amount", "turnover", "volume_ratio", "OHLC", "industry"],
        "status": "partial_full_list_one_page_timeout_deep_pool_complete",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    close_pair = []
    triggers = {
        "600744": ("11月9日竞价不过度高开，开盘回踩不破11月6日中枢且电力板块同步，再观察放量站回6.19", "跌破11月6日低点5.55，或板块同步转弱、放量冲高回落"),
        "603706": ("11月9日竞价承接、回踩不破17.94前高且燃气同类同步，再观察18.75上方有效成交", "跌破16.99，或突破前高后量价背离、板块无同步"),
    }
    for raw in mr["close_relative_research_pair"]:
        close_pair.append({
            "code": raw["code"], "name": raw["name"], "reference_close": raw["close"],
            "freeze_time": mr["completed_at"], "candidate_type": "after_close_relative_research_shadow",
            "formal_buy_signal": False, "buy_order_allowed": False,
            "trigger": triggers[raw["code"]][0], "invalid": triggers[raw["code"]][1],
            "earliest_legal_exit_if_entered_2026_11_09": "2026-11-10",
        })

    tag_counts = {}
    for row in deep:
        for tag in row["tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    completed_utc, completed_cn = now_pair()
    blocked = {
        "deep_pool_intraday_completeness": "仅5只典型样本取得完整48根历史5分钟OHLCV；其余23只不能确认分歧、承接、再转强的分钟顺序。",
        "point_in_time_sector_sync": "东方财富取得28只行业标签，但没有冻结T日逐时板块成员OHLCV与全成员同步率。",
        "executable_strategy": "盘后研究影子不等于正式买点；无实际成交、排队和T+1退出证据，净收益、胜率、盈亏比与成本后退出质量为N/A。",
    }
    evidence = {
        "schema_version": 1,
        "market_date": T,
        "started_at": started_utc,
        "completed_at": completed_utc,
        "market_scope": "Shanghai+Shenzhen; Beijing excluded by current contract",
        "providers": mr["provider_attempts"] + [
            {"provider": "Eastmoney close market list HTTPS", "date": T, "status_file": str(EM_STATUS.relative_to(ROOT)), "rows_received": len(em_raw["rows"]), "deep_verified": em_deep_verified, "page_errors": em_raw["errors"]},
            {"provider": "Sina 5-minute historical K-line", "date": T, "requested": 5, "verified": len(minute), "bars_each": 48, "historical_only": True},
        ],
        "market_scan": mr["market_scan"],
        "broad_pool": mr["broad_pool"],
        "deep_pool": deep,
        "prior_20261105_pool_validation": prior,
        "prior_pool_summary": {
            "n": len(observed), "positive_n": positive_n, "mean_close_pct": mean(close_values),
            "median_close_pct": median(close_values), "mean_mfe_pct": mean(mfe_values), "mean_mae_pct": mean(mae_values),
            "executed_trade_count": 0, "return_basis": "2026-11-05 close to 2026-11-06 daily observation; not strategy P/L",
        },
        "typical_intraday_history": minute,
        "production_intraday_frozen_original": mr["production_intraday_frozen"],
        "after_close_relative_research_pair": close_pair,
        "tag_counts": tag_counts,
        "blocked": blocked,
        "formal_candidates": [],
        "verified_fills": 0,
        "analysis_completed": False,
        "eligible_for_integrated_research": False,
        "rule_version": "volume_price_close_v6_shsz_source_bounded",
    }
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    table = []
    for row in deep:
        table.append(
            f"|{row['code']} {row['name']}|{row.get('industry') or '未知'}|{'、'.join(row['tags'])}|{fmt(row['close'])}/{fmt(row['pct'])}%|"
            f"{fmt(row['turnover_pct'])}%/{fmt(row['rvol5'])}/{fmt(row['rvol10'])}/{fmt(row['rvol20'])}|"
            f"{fmt(row['position120']*100,1)}%/{fmt(row['clv'],3)}|{fmt(row['upper_shadow_pct'])}%/{fmt(row['lower_shadow_pct'])}%|"
        )
    intraday_lines = []
    for code in minute_codes:
        row = minute_map[code]
        direction = "收盘自日低明显修复" if row["recovery_from_low_to_close_pct"] >= 5 else "收盘修复有限"
        intraday_lines.append(
            f"- **{code} {names[code]}**：48根历史5分钟；低点{fmt(row['day_low'])}出现在{row['day_low_bar_time'][11:16]}，"
            f"收盘{fmt(row['close'])}，低点至收盘{row['recovery_from_low_to_close_pct']:+.2f}%，14:40至收盘{row['close_vs_1440_pct']:+.2f}%，"
            f"尾段单根均量/此前均量={row['tail_5m_volume_vs_prior_avg']:.2f}；{direction}。这是盘后历史分钟复盘，不是原时点买点。"
        )

    body = f"""研究交易日 **T={T}**，范围严格为沪深股票，北交所按最新契约排除，不列为缺口。新浪收盘快照取得沪深 {mr['snapshot']['coverage']['verified']}/{mr['snapshot']['coverage']['checked']} 只有效OHLCV，覆盖率 {mr['snapshot']['coverage']['coverage_ratio']:.4%}；冻结广泛池120只、深筛28只。东方财富免费HTTPS分页取得 {len(em_raw['rows'])} 个唯一代码，56页中55页成功、1页超时，但深筛28/28的换手、量比和行业字段均与收盘价交叉核验。5只典型样本另取得每只48根历史5分钟OHLCV。其余23只分钟顺序与点时板块同步仍缺，故状态为 **partial/blocked**，但已完成实质研究并冻结2只盘后相对优选影子；正式买点仍为0。

## 1. 市场与来源

- 数据截止：{T} 15:00:00+08:00；研究完成：{completed_cn}。
- 沪深上涨716、下跌4431、平盘71；成交额简单加总16576.0亿元，较前一交易日缩量21.73%。弱市广度下，放量上涨需更严格验证板块与次日承接。
- 新浪收盘快照：5218/5224；6只缺失或停牌/陈旧未补造。BaoStock登录失败 `10002007: 网络接收错误`；东方财富日线两只样本复核成功。
- 东方财富收盘行情：分页55/56成功，5463个唯一代码；深筛28/28取得换手、量比、行业和OHLC字段，收盘与新浪误差≤0.03元。
- 新浪历史5分钟：5/5取得、每只48根；严格标为盘后历史分钟，不能冒充09:50/14:40实时行情。

## 2. 上一批28只前推验证

2026-11-05冻结池在11月6日取得日线观察 {len(observed)}/28：收涨 {positive_n} 只，收盘变化均值 {mean(close_values):+.3f}%、中位 {median(close_values):+.3f}%，日线MFE均值 {mean(mfe_values):+.3f}%、MAE均值 {mean(mae_values):+.3f}%。这些均以11月5日收盘为基准，仅是价格观察；没有原触发分钟、成交和T+1退出证据，不能解释为策略收益或胜率。

## 3. 11月6日深筛28只

|代码/名称|行业|阶段标签|收盘/涨跌|换手/RVOL5/10/20|120日位置/CLV|上影/下影|
|---|---|---|---|---|---|---|
{chr(10).join(table)}

标签计数：{json.dumps(tag_counts, ensure_ascii=False)}。同一股票可有多个结构标签，标签计数不能相加成独立样本。

## 4. 典型5只历史分钟复盘

{chr(10).join(intraday_lines)}

支持样本中，乐山电力、东方环宇、华银电力均具备低/中位置、RVOL20显著放大和较高CLV；其中东方环宇完成20日突破。风险对照海源复材、中利集团成交显著放大但CLV分别约0.16、0.08，说明筹码交换后价格未向上推进。5分钟序列仅支持描述已发生路径，不能确认资金身份；单笔拉升、假突破和真实分歧转一致仍需次日原时点证据验证。

## 5. 对筛选的具体反馈与非空研究候选

- 盘后量价因子相对优选影子为 **600744 华银电力**、**603706 东方环宇**。它们来自冻结120→28池，不是事后按次日赢家挑选；参考价只采用11月6日收盘6.01元、18.35元。
- 华银电力：11月9日竞价不过度高开、回踩不破11月6日中枢且电力板块同步后，才观察放量站回6.19；跌破5.55或冲高量价背离即失效。
- 东方环宇：竞价承接、回踩不破17.94前高且燃气同类同步后，才观察18.75上方有效成交；跌破16.99或板块无同步即失效。
- 两只均为 `research_shadow`，`formal_buy_signal=false`、`buy_order_allowed=false`。若11月9日实际入场，按A股T+1最早11月10日卖出。
- 生产原冻结09:50候选乾照光电、亿纬锂能，14:40候选中粮糖业、嘉友国际均原样关联；本报告不依据收盘结果改选或改写其原报价。

## 6. 有效/风险结构与待证伪假设

1. **待验证H1**：低/中位、RVOL20≥1.5且CLV≥0.70组，在11月9日的MAE与收盘表现优于高位爆量低CLV组；固定本次样本，不换股挑赢家。
2. **待验证H2**：20日突破若次日竞价与开盘不能守住突破位，后续退出质量弱于有板块同步的回踩承接样本；缺点时板块数据时记未知。
3. **待验证H3**：放量下跌且CLV<0.20样本次日即使高开，也需先重回T日中枢；否则作为假转强/兑现风险，不因反弹高点入选。

现有样本不足以宣称稳定胜率，没有实际成交则净收益、盈亏比、成本、滑点和可执行退出质量均为N/A。APP不内置大模型，也不自行训练权重。

## 7. 未完成项

- 23只深筛缺完整历史分钟；无法验证全部样本的杀跌放量、低点抬高、回踩缩量和再突破顺序。
- 只有行业标签，没有T日逐时板块成员OHLCV和全成员同步率。
- 没有逐笔、订单队列、真实成交或T+1退出；正式买点为0，不把研究影子冒充交易推荐。
"""
    REPORT.write_text("# 量价研究与每日验证｜2026-11-06（沪深实质执行，部分受阻）\n\n" + body + "\n", encoding="utf-8")

    research_path = ROOT / "backend/data/research.json"
    runs_path = ROOT / "backend/data/task_runs.json"
    samples_path = ROOT / "backend/data/volume_price_samples.json"
    research = json.loads(research_path.read_text(encoding="utf-8"))
    runs = json.loads(runs_path.read_text(encoding="utf-8"))
    samples = json.loads(samples_path.read_text(encoding="utf-8"))
    if any(row.get("id") == REPORT_ID for row in research["items"]):
        raise ValueError("duplicate_report_id")
    if any(row.get("id") == RECEIPT_ID for row in runs["items"]):
        raise ValueError("duplicate_receipt_id")
    sources = [
        str(MR_EVIDENCE.relative_to(ROOT)), str(EVIDENCE.relative_to(ROOT)),
        "backend/data/sina_daily_full/2026-11-06.json", str(EM_STATUS.relative_to(ROOT)),
        "https://quotes.sina.cn/cn/api/jsonp_v2.php/CN_MarketDataService.getKLineData",
        "https://push2.eastmoney.com/api/qt/clist/get", ISSUE,
    ]
    research["items"].append({
        "id": REPORT_ID, "date": T, "market_date": T, "task_id": "volume_price", "track": "volume_price",
        "run_id": RUN_ID, "title": "量价研究｜11月6日沪深5218只、120广池、28深筛与5只分钟复盘（部分受阻）",
        "summary": "沪深5218/5224只收盘OHLCV、120广池、28深筛及上一批28/28日线验证；东方财富补齐28/28换手/行业，5只完整历史5分钟。冻结华银电力、东方环宇两只盘后研究影子；缺其余23只分钟与点时板块，保持partial。",
        "body": body, "sources": sources, "report_type": "substantive_daily_research_partial",
        "eligible_for_integrated_research": False, "analysis_completed": False, "status": "partial",
        "published_at": completed_cn, "recorded_at": completed_cn, "market_data_cutoff_at": T + "T15:00:00+08:00",
        "data_cutoff_at": completed_cn, "planned_entry_date": "2026-11-09", "earliest_legal_exit_date_if_bought": "2026-11-10",
        "research_rule_version": evidence["rule_version"], "candidate_count": 2, "candidate_scope": "after_close_relative_research_shadow",
        "research_shadow_candidates": close_pair, "formal_candidate_count": 0, "recommendation_ids": [],
        "evidence_file": str(EVIDENCE.relative_to(ROOT)), "full_scan_count": mr["snapshot"]["coverage"]["verified"],
        "broad_pool_count": 120, "broad_pool_verified_count": 120, "deep_pool_count": 28,
        "previous_pool_verified_count": len(observed), "minute_verified_count": len(minute),
        "codes": [row["code"] for row in deep], "blocked_modules": list(blocked), "verified_fill_count": 0,
    })
    runs["items"].append({
        "id": RECEIPT_ID, "run_id": RUN_ID, "task_id": "volume_price", "date": T, "trigger": "scheduled",
        "started_at": started_cn, "recorded_at": completed_cn, "completed_at": completed_cn, "status": "blocked",
        "summary": "已实质完成11月6日沪深5218/5224收盘扫描、120广池、28深筛、上一批28/28日线验证、28/28换手/行业交叉核验及5只历史分钟复盘；冻结2只盘后研究影子。其余23只分钟和点时板块同步缺失，故不标completed。",
        "report_ids": [REPORT_ID], "recommendation_ids": [], "research_shadow_candidates": close_pair,
        "analysis_completed": False, "eligible_for_integrated_research": False, "sources": sources,
        "blocked_modules": list(blocked), "verified_fill_count": 0,
    })
    samples["items"].append({
        "id": "volume-price-20261105-validation-20261106-v1", "date": T, "task_id": "volume_price",
        "recorded_at": completed_cn, "report_ids": [REPORT_ID], "origin_cohort_id": "volume-price-20261105-partial-v1-cohort",
        "rule_version": evidence["rule_version"], "full_validation_completed": len(prior) == 28,
        "full_pool_summary": evidence["prior_pool_summary"], "full_pool_validations": prior,
        "executed_trade_count": 0, "eligible_for_model_statistics": False,
    })
    samples["items"].append({
        "id": "volume-price-20261106-partial-v1-cohort", "date": T, "task_id": "volume_price",
        "frozen_at": completed_cn, "report_ids": [REPORT_ID], "rule_version": evidence["rule_version"],
        "data_cutoff_at": T + "T15:00:00+08:00", "market_scope": evidence["market_scope"],
        "full_scan_count": mr["snapshot"]["coverage"]["verified"], "broad_pool_count": 120,
        "deep_screen_count": 28, "minute_verified_count": 5, "research_shadow_candidates": close_pair,
        "eligible_for_model_statistics": False, "statistical_scope": "future daily price observation; no fill-based profitability",
        "provenance": "source-bounded after-close research", "samples": deep, "typical_intraday_history": minute,
        "missing": list(blocked),
    })
    research_path.write_text(json.dumps(research, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    runs_path.write_text(json.dumps(runs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    samples_path.write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report_id": REPORT_ID, "receipt_id": RECEIPT_ID, "completed_at": completed_cn,
                      "full_scan": mr["snapshot"]["coverage"], "broad": 120, "deep": 28,
                      "prior_verified": len(observed), "em_deep_verified": em_deep_verified,
                      "minute_verified": len(minute), "research_shadow_candidates": [r["code"] for r in close_pair]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
