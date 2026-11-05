#!/usr/bin/env python3
"""Publish the source-bounded 2026-11-05 volume/price close study."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
T = "2026-11-05"
PREV = "2026-11-04"
CN = ZoneInfo("Asia/Shanghai")
ISSUE = "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/25"
SNAP = ROOT / f"backend/data/baostock/{T}.json"
PREV_SNAP = ROOT / f"backend/data/baostock/{PREV}.json"
PRIOR_EVIDENCE = ROOT / "docs/research/volume-price-20261104-evidence.json"
EVIDENCE = ROOT / "docs/research/volume-price-20261105-evidence.json"
REPORT = ROOT / "docs/research/volume-price-20261105-partial-v1.md"

spec = importlib.util.spec_from_file_location(
    "vp_prev", ROOT / "scripts/publish_volume_price_20261104.py"
)
vp = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(vp)
vp.T = T


def now_pair():
    utc = datetime.now(timezone.utc)
    return (
        utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
        utc.astimezone(CN).isoformat(timespec="seconds"),
    )


def code6(row):
    return row["code"].split(".")[1]


def fmt(value, digits=3):
    return "N/A" if value is None else f"{value:.{digits}f}"


def prior_validation(prior_deep, current):
    rows = []
    for sample in prior_deep:
        code = sample["code"]
        bar = current.get(code)
        if not bar:
            rows.append({
                "code": code,
                "name": sample.get("name"),
                "base_date": PREV,
                "validation_date": T,
                "status": "missing_or_suspended",
                "executed_trade": False,
                "executable_net_return_pct": None,
            })
            continue
        base = float(sample["close"])
        rows.append({
            "code": code,
            "name": sample.get("name"),
            "base_date": PREV,
            "validation_date": T,
            "base_close": base,
            "daily": {k: bar[k] for k in ("date", "open", "high", "low", "close", "volume", "amount")},
            "open_pct": (bar["open"] / base - 1) * 100,
            "close_pct": (bar["close"] / base - 1) * 100,
            "mfe_pct": (bar["high"] / base - 1) * 100,
            "mae_pct": (bar["low"] / base - 1) * 100,
            "status": "daily_price_observed",
            "executed_trade": False,
            "executable_net_return_pct": None,
            "note": "T+1日线价格观察；缺分钟触发顺序和成交证据。",
        })
    return rows


def main():
    started_utc, started_cn = now_pair()
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    previous = json.loads(PREV_SNAP.read_text(encoding="utf-8"))
    prior = json.loads(PRIOR_EVIDENCE.read_text(encoding="utf-8"))
    if snap.get("provider") != "baostock" or snap.get("trade_date") != T:
        raise ValueError("invalid_current_snapshot")
    if snap["coverage"]["coverage_ratio"] < 0.90:
        raise ValueError("coverage_below_90_percent")

    current_map = {code6(row): row for row in snap["rows"]}
    previous_map = {code6(row): row for row in previous["rows"]}
    names = vp.names_from_archive()
    broad_seed, market_rows = vp.freeze_broad(snap["rows"], previous_map, set(names))

    histories, history_errors = {}, {}
    with ThreadPoolExecutor(max_workers=16) as executor:
        jobs = {executor.submit(vp.fetch_history, row["code6"]): row["code6"] for row in broad_seed}
        for future in as_completed(jobs):
            code = jobs[future]
            try:
                histories[code] = future.result()
            except Exception as exc:
                history_errors[code] = str(exc)[:180]

    broad = []
    for row in broad_seed:
        code = row["code6"]
        if code not in histories:
            continue
        item = vp.metrics(histories[code], current_map[code])
        item["name"] = names.get(code, "名称未从冻结档案取得")
        raw_turn = current_map[code].get("turn")
        item["turnover_pct"] = float(raw_turn) if raw_turn not in (None, "") else None
        item["amount_yuan"] = current_map[code].get("amount")
        item["volume_unit"] = current_map[code].get("volume_unit", "shares")
        if "ST" in item["name"].upper():
            item["tags"] = ["ST风险对照"]
        broad.append(item)

    deep = vp.select_deep(broad)
    validations = prior_validation(prior["deep_pool"], current_map)
    observed = [row for row in validations if row["status"] == "daily_price_observed"]
    advances = sum(row["close"] > previous_map[code6(row)]["close"] for row in snap["rows"] if code6(row) in previous_map)
    declines = sum(row["close"] < previous_map[code6(row)]["close"] for row in snap["rows"] if code6(row) in previous_map)
    matched = sum(code6(row) in previous_map for row in snap["rows"])
    unchanged = matched - advances - declines
    completed_utc, completed_cn = now_pair()

    blocked = {
        "market_scope": "BaoStock同日快照只覆盖沪深，北交所不在范围；293条代码缺失/停牌/无效保持原错误。",
        "sector_sync": "没有归档T日点时板块成员、板块OHLCV与成员同步强度。",
        "intraday_sequence": "没有覆盖28只深筛的T日竞价、分钟OHLCV、逐笔或订单队列；日线CLV不能证明分歧转一致顺序。",
        "executable_strategy": "正式候选与已核实成交均为0，成本、滑点、涨跌停可成交性和T+1退出质量不可计算。",
    }
    evidence = {
        "schema_version": 1,
        "market_date": T,
        "started_at": started_utc,
        "completed_at": completed_utc,
        "providers": [
            {"provider": "BaoStock", "file": str(SNAP.relative_to(ROOT)), "date": T, "adjustment": "none", "scope": snap["exchange_scope"], "coverage": snap["coverage"], "volume_unit": "shares"},
            {"provider": "Sina", "date_required": T, "adjustment": "none", "purpose": "frozen 120-name broad-pool historical bars", "url_template": "https://quotes.sina.cn/cn/api/jsonp_v2.php/CN_MarketDataService.getKLineData"},
        ],
        "market_scan": {
            "checked": snap["coverage"]["checked"],
            "verified": snap["coverage"]["verified"],
            "errors": snap["errors"],
            "matched_previous": matched,
            "advanced": advances,
            "declined": declines,
            "unchanged": unchanged,
            "frozen_name_mapped_stock_rows": len(market_rows),
            "amount_sum_yuan": sum(row["amount"] for row in market_rows),
            "broad_pool_count": len(broad_seed),
        },
        "history_fetch": {
            "requested": len(broad_seed),
            "verified": len(broad),
            "errors": history_errors,
            "close_crosscheck_within_0_03": sum(row["ohlc_close_crosscheck_abs"] <= 0.03 for row in broad),
        },
        "broad_pool": broad,
        "deep_pool": deep,
        "prior_20261104_deep_validation": validations,
        "blocked": blocked,
        "formal_candidates": [],
        "verified_fills": 0,
        "analysis_completed": False,
        "eligible_for_integrated_research": False,
        "rule_version": "volume_price_close_v5_partial_source_bounded",
    }
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    tag_counts = {}
    for row in deep:
        for tag in row["tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    supportive = [row for row in deep if any(tag in row["tags"] for tag in ("低位首次放量/推进代理", "放量突破", "日线分歧转强代理")) and "ST风险对照" not in row["tags"]]
    risky = [row for row in deep if any(tag in row["tags"] for tag in ("高位爆量滞涨/长上影风险", "放量下跌"))]
    typical = (supportive[:3] + risky[:2])[:5]
    close_values = [row["close_pct"] for row in observed]
    mfe_values = [row["mfe_pct"] for row in observed]
    mae_values = [row["mae_pct"] for row in observed]

    table = []
    for row in deep:
        table.append(
            f"|{row['code']} {row['name']}|{'、'.join(row['tags'])}|{fmt(row['close'],2)}/{fmt(row['pct'])}|"
            f"{fmt(row['turnover_pct'])}|{fmt(row['rvol5'])}/{fmt(row['rvol10'])}/{fmt(row['rvol20'])}|"
            f"{fmt((row['position20'] or 0)*100,1)}/{fmt((row['position60'] or 0)*100,1)}/{fmt((row['position120'] or 0)*100,1)}|"
            f"{fmt(row['clv'])}/{fmt(row['upper_shadow_pct'])}/{fmt(row['lower_shadow_pct'])}|"
        )

    typical_lines = []
    for row in typical:
        typical_lines.append(
            f"- **{row['code']} {row['name']}**：{'、'.join(row['tags'])}；换手{fmt(row['turnover_pct'])}%、"
            f"RVOL20={fmt(row['rvol20'])}、120日位置={fmt((row['position120'] or 0)*100,1)}%、CLV={fmt(row['clv'])}。"
            "这是日线级证据，未核分钟顺序，不能直接称为真正分歧转一致或买点。"
        )

    body = f"""已完成交易日 **T={T}**。BaoStock单连接批量档案取得同日沪深OHLCV {snap['coverage']['verified']}/{snap['coverage']['checked']} 条，覆盖率 {snap['coverage']['coverage_ratio']:.2%}；经10月30日冻结名称映射得到 {len(market_rows)} 只股票日线。独立新浪未复权日线补齐冻结广泛池 {len(broad)}/{len(broad_seed)} 只历史，形成28只深筛，并验证11月4日28只深筛的11月5日日线结果。北交所、点时板块同步与全深筛分钟顺序仍缺，因此本报告是实质研究的 **partial/blocked**，不满足综合研究前置；正式候选0、成交0。

## 1. 数据与市场扫描

- 数据截止：{T} 15:00:00+08:00；研究完成：{completed_cn}。
- 沪深快照与前一交易日可匹配 {matched} 条：上涨 {advances}、下跌 {declines}、平盘 {unchanged}。冻结股票映射口径成交额简单加总 {sum(row['amount'] for row in market_rows)/1e8:.1f} 亿元；不把它冒充含北交所的全A成交额。
- 广泛池按成交额、相对前一日量、涨跌、振幅与CLV固定组合冻结120只；新浪历史核验 {len(broad)}/120，收盘与BaoStock差值不超过0.03元 {sum(row['ohlc_close_crosscheck_abs'] <= 0.03 for row in broad)}/{len(broad)}。RVOL5/10/20分母均为T以前完成交易日，不含T；换手读取BaoStock同日字段，不反推自由流通股。
- CLV=(收盘-最低)/(最高-最低)。它只说明收盘在日内区间的位置；没有分钟序列时，不能从下影线或阳线反推“杀跌放量→跌不动→回踩缩量→再突破”。

## 2. 上一批28只的T+1日线验证

11月4日冻结深筛取得11月5日有效日线 {len(observed)}/28。相对11月4日收盘，11月5日收盘观察均值 {fmt(statistics.mean(close_values) if close_values else None)}%、中位 {fmt(statistics.median(close_values) if close_values else None)}%；日线MFE均值 {fmt(statistics.mean(mfe_values) if mfe_values else None)}%，MAE均值 {fmt(statistics.mean(mae_values) if mae_values else None)}%。这些是价格观察，不是9:50/14:40成交或策略净收益。原正式候选0，所以胜率、盈亏比、成本后收益与退出质量仍为N/A。

## 3. 当日28只深筛完整留档

|代码/名称|量价阶段标签|收盘/涨跌%|换手%|RVOL5/10/20|20/60/120日位置%|CLV/上影%/下影%|
|---|---|---|---|---|---|---|
{chr(10).join(table)}

标签计数：{json.dumps(tag_counts, ensure_ascii=False)}。同股多标签仅算一个样本，不能横向相加。

## 4. 典型样本、有效结构与风险结构

{chr(10).join(typical_lines)}

- **支持证据**：本轮只把放量后价格推进、CLV较高且不在120日极高位的结构列为次日影子观察条件；仍需11月6日9:25竞价、板块同步和开盘承接二次过滤。
- **假转强/兑现风险**：高位放量但CLV偏低、上影较长，或放量下跌，说明充分交换后价格未能推进；缩量上涨只作弱证据。
- **筛选反馈**：28只均为研究样本，不是正式两只指令。缺竞价/板块/分钟顺序时不自动升级；不满足承接条件直接淘汰，不事后用日最高价补造触发。

## 5. 下一交易日待证伪假设

1. 低/中位、RVOL20≥1.5且CLV≥0.70的日线推进组，在11月6日收盘观察上优于高位爆量低CLV组；只验证本次冻结样本，不换股挑赢家。
2. 20日突破样本若竞价与开盘不能守住T日收盘附近，后续MFE/MAE与退出质量弱于有板块同步样本；板块证据补齐前只记未知。
3. 缩量上涨组若11月6日量能仍不足并跌破T日中枢，记为假转强反例，不因收红进入正式候选。

## 6. 明确受阻与T+1边界

- 北交所未覆盖；BaoStock原始293条缺失/停牌/无效代码不补造。
- 缺T日点时板块成员、板块OHLCV和同步强度；缺28只深筛的竞价、完整分钟OHLCV、逐笔和订单队列。
- 因此不建立9:50/14:40买入、触发顺序、实际成交或可执行净收益。T盘后信号若T+1入场，最早T+2卖出。
- 规则版本 `volume_price_close_v5_partial_source_bounded`；阶段样本不足，不宣称稳定规律，不保证收益。
"""
    REPORT.write_text("# 量价研究与每日验证｜2026-11-05（实质执行，部分受阻）\n\n" + body + "\n", encoding="utf-8")

    research_path = ROOT / "backend/data/research.json"
    runs_path = ROOT / "backend/data/task_runs.json"
    samples_path = ROOT / "backend/data/volume_price_samples.json"
    research = json.loads(research_path.read_text(encoding="utf-8"))
    runs = json.loads(runs_path.read_text(encoding="utf-8"))
    samples = json.loads(samples_path.read_text(encoding="utf-8"))
    report_id = "volume-price-20261105-partial-v1"
    receipt_id = "volume-price-20261105-scheduled-close-v1-partial"
    if any(row.get("id") == report_id for row in research["items"]):
        raise ValueError("duplicate_report_id")
    if any(row.get("id") == receipt_id for row in runs["items"]):
        raise ValueError("duplicate_receipt_id")

    sources = [str(SNAP.relative_to(ROOT)), str(PREV_SNAP.relative_to(ROOT)), str(EVIDENCE.relative_to(ROOT)), "https://quotes.sina.cn/cn/api/jsonp_v2.php/CN_MarketDataService.getKLineData", ISSUE]
    research["items"].append({
        "id": report_id,
        "date": T,
        "market_date": T,
        "task_id": "volume_price",
        "track": "volume_price",
        "run_id": "volume-price-20261105-scheduled-close-v1",
        "title": f"量价研究｜11月5日{len(market_rows)}只冻结股票映射、120广泛池与28深筛（部分受阻）",
        "summary": f"BaoStock同日{snap['coverage']['verified']}/{snap['coverage']['checked']}，冻结股票映射{len(market_rows)}只、120广泛池、{len(broad)}只历史核验、28深筛并完成上一批28只日线验证；北交所、板块与分钟证据缺失，正式候选0。",
        "body": body,
        "sources": sources,
        "report_type": "substantive_daily_research_partial",
        "eligible_for_integrated_research": False,
        "analysis_completed": False,
        "status": "partial",
        "published_at": completed_cn,
        "recorded_at": completed_cn,
        "market_data_cutoff_at": T + "T15:00:00+08:00",
        "data_cutoff_at": completed_cn,
        "planned_entry_date": "2026-11-06",
        "earliest_legal_exit_date_if_bought": "2026-11-09",
        "research_rule_version": evidence["rule_version"],
        "candidate_count": 0,
        "recommendation_ids": [],
        "evidence_file": str(EVIDENCE.relative_to(ROOT)),
        "full_scan_count": len(market_rows),
        "raw_snapshot_verified_count": snap["coverage"]["verified"],
        "broad_pool_count": len(broad_seed),
        "broad_pool_verified_count": len(broad),
        "deep_pool_count": len(deep),
        "previous_pool_verified_count": len(observed),
        "codes": [row["code"] for row in deep],
        "blocked_modules": list(blocked),
        "verified_fill_count": 0,
    })
    runs["items"].append({
        "id": receipt_id,
        "run_id": "volume-price-20261105-scheduled-close-v1",
        "task_id": "volume_price",
        "date": T,
        "trigger": "scheduled",
        "started_at": started_cn,
        "recorded_at": completed_cn,
        "completed_at": completed_cn,
        "status": "blocked",
        "summary": f"已实质完成11月5日BaoStock {snap['coverage']['verified']}/{snap['coverage']['checked']}、{len(market_rows)}只冻结股票映射扫描、120广泛池、28深筛及上一批{len(observed)}/28日线验证；北交所、板块与分钟顺序缺失，故不标completed。",
        "report_ids": [report_id],
        "recommendation_ids": [],
        "analysis_completed": False,
        "eligible_for_integrated_research": False,
        "sources": sources,
        "blocked_modules": list(blocked),
        "verified_fill_count": 0,
    })
    samples["items"].append({
        "id": "volume-price-20261104-validation-20261105-v1",
        "date": T,
        "task_id": "volume_price",
        "recorded_at": completed_cn,
        "report_ids": [report_id],
        "origin_cohort_id": "volume-price-20261104-partial-v1-cohort",
        "rule_version": "volume_price_close_v5_partial_source_bounded",
        "full_validation_completed": len(validations) == 28,
        "full_pool_summary": {
            "n": len(observed),
            "mean_pct": round(statistics.mean(close_values), 3) if close_values else None,
            "median_pct": round(statistics.median(close_values), 3) if close_values else None,
            "positive_n": sum(value > 0 for value in close_values),
            "mean_mfe_pct": round(statistics.mean(mfe_values), 3) if mfe_values else None,
            "mean_mae_pct": round(statistics.mean(mae_values), 3) if mae_values else None,
            "executed_trade_count": 0,
            "return_basis": "T11/4 close to T11/5 daily price observation; not entry P/L",
        },
        "full_pool_validations": validations,
        "executed_trade_count": 0,
        "eligible_for_model_statistics": False,
    })
    samples["items"].append({
        "id": "volume-price-20261105-partial-v1-cohort",
        "date": T,
        "task_id": "volume_price",
        "frozen_at": completed_cn,
        "report_ids": [report_id],
        "rule_version": evidence["rule_version"],
        "data_cutoff_at": T + "T15:00:00+08:00",
        "broad_pool_count": len(broad_seed),
        "broad_pool_verified_count": len(broad),
        "deep_screen_count": len(deep),
        "eligible_for_model_statistics": False,
        "statistical_scope": "future daily price observation; no fill-based profitability",
        "provenance": "source-bounded after-close research",
        "samples": deep,
        "missing": list(blocked),
    })
    research_path.write_text(json.dumps(research, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    runs_path.write_text(json.dumps(runs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    samples_path.write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report_id": report_id,
        "receipt_id": receipt_id,
        "snapshot_coverage": snap["coverage"],
        "mapped_stock_rows": len(market_rows),
        "broad_verified": len(broad),
        "deep": len(deep),
        "prior_verified": len(observed),
        "completed_at": completed_cn,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
