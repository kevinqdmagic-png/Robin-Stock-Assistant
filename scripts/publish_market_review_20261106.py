#!/usr/bin/env python3
"""Publish the source-bounded 2026-11-06 market review.

This consumes the independently verified Sina SH/SZ close snapshot, freezes a
120-name broad pool before requesting history, and preserves the production
09:50/14:40 observations exactly as recorded.  Missing full-sector membership
and minute sequences remain explicit, so the report cannot satisfy the full
integrated-research gate.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
T = "2026-11-06"
PREV = "2026-11-05"
CN = ZoneInfo("Asia/Shanghai")
SNAP = ROOT / f"backend/data/sina_daily_full/{T}.json"
PREV_SNAP = ROOT / f"backend/data/sina_daily_full/{PREV}.json"
EVIDENCE = ROOT / "docs/research/market-review-20261106-evidence.json"
REPORT = ROOT / "docs/research/market-review-20261106-partial-v1.md"
ISSUE = "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/25"
PROD = "https://robin-stock-api-production.up.railway.app"

spec = importlib.util.spec_from_file_location(
    "vp_helpers", ROOT / "scripts/publish_volume_price_20261104.py"
)
vp = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(vp)
vp.T = T


def now_cn() -> str:
    return datetime.now(timezone.utc).astimezone(CN).isoformat(timespec="seconds")


def curl_json(url: str) -> dict:
    proc = subprocess.run(
        ["curl", "-fsS", "--max-time", "25", "-H", "User-Agent: Mozilla/5.0", url],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(proc.stdout)


def eastmoney_pool(kind: str) -> dict:
    url = (
        f"https://push2ex.eastmoney.com/getTopic{kind}Pool?"
        "ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt&"
        "Pageindex=0&pagesize=100&sort=fbt:asc&date=20261106"
    )
    payload = curl_json(url)
    return {"url": url, "payload": payload}


def fmt(v, n=2):
    return "N/A" if v is None else f"{v:.{n}f}"


def main() -> None:
    started_at = now_cn()
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    prev = json.loads(PREV_SNAP.read_text(encoding="utf-8"))
    if snap.get("trade_date") != T or snap["coverage"]["coverage_ratio"] < 0.90:
        raise ValueError("verified_sina_snapshot_required")

    rows = snap["rows"]
    current = {r["code"].split(".")[1]: r for r in rows}
    previous = {r["code"].split(".")[1]: r for r in prev["rows"]}
    names = {r["code"].split(".")[1]: r["name"] for r in rows if r.get("name")}
    broad_seed, market_rows = vp.freeze_broad(rows, previous, set(names))

    histories, history_errors = {}, {}
    with ThreadPoolExecutor(max_workers=20) as executor:
        jobs = {executor.submit(vp.fetch_history, r["code6"]): r["code6"] for r in broad_seed}
        for future in as_completed(jobs):
            code = jobs[future]
            try:
                histories[code] = future.result()
            except Exception as exc:
                history_errors[code] = f"{type(exc).__name__}:{str(exc)[:120]}"

    broad = []
    for seed in broad_seed:
        code = seed["code6"]
        if code not in histories:
            continue
        item = vp.metrics(histories[code], current[code])
        item.update({
            "name": names[code],
            "amount_yuan": current[code]["amount"],
            "turnover_pct": None,
            "turnover_note": "新浪收盘批量源未提供自由流通换手，未反推",
        })
        if "ST" in item["name"].upper():
            item["tags"] = ["ST风险对照"]
        broad.append(item)
    deep = vp.select_deep(broad)

    relative = [
        r for r in deep
        if "ST" not in r["name"].upper()
        and -3.0 <= r["pct"] <= 8.0
        and (r["rvol20"] or 0) >= 1.2
        and (r["clv"] or 0) >= 0.65
        and (r["position120"] or 1) <= 0.75
        and r["amount_yuan"] >= 100_000_000
    ]
    relative.sort(
        key=lambda r: (
            2.0 * (r["clv"] or 0)
            + min(r["rvol20"] or 0, 3.0)
            + (1.0 - (r["position120"] or 1.0))
            - max(r["pct"] - 5.0, 0) / 5.0
        ),
        reverse=True,
    )
    close_pair = relative[:2]

    pools, pool_errors = {}, {}
    for kind in ("ZT", "ZB", "DT"):
        try:
            pools[kind] = eastmoney_pool(kind)
        except Exception as exc:
            pool_errors[kind] = f"{type(exc).__name__}:{str(exc)[:160]}"
    early = curl_json(f"{PROD}/api/intraday-live?slot=early_pair")["latest"]
    late = curl_json(f"{PROD}/api/intraday-live?slot=late_pair")["latest"]

    advances = sum(r["pctChg"] > 0 for r in rows)
    declines = sum(r["pctChg"] < 0 for r in rows)
    unchanged = len(rows) - advances - declines
    amount = sum(r["amount"] for r in rows)
    prev_amount = sum(r["amount"] for r in prev["rows"])
    zt_data = pools.get("ZT", {}).get("payload", {}).get("data") or {}
    zb_data = pools.get("ZB", {}).get("payload", {}).get("data") or {}
    dt_data = pools.get("DT", {}).get("payload", {}).get("data") or {}
    zt_pool = zt_data.get("pool") or []
    sector_counts = {}
    for item in zt_pool:
        sector = item.get("hybk") or "未分类"
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
    max_board = max((int(x.get("lbc") or 0) for x in zt_pool), default=0)
    height_names = [x.get("n") for x in zt_pool if int(x.get("lbc") or 0) == max_board]

    prior_report = next(
        x for x in json.loads((ROOT / "backend/data/research.json").read_text(encoding="utf-8"))["items"]
        if x.get("id") == "market-review-20261105-source-bounded-v1"
    )
    prior_validation = []
    for code in prior_report.get("codes", []):
        row = current.get(code)
        base = previous.get(code)
        if not row or not base:
            prior_validation.append({"code": code, "status": "missing_or_suspended"})
            continue
        prior_validation.append({
            "code": code,
            "name": row["name"],
            "status": "daily_price_observed",
            "base_close": base["close"],
            "open_pct": (row["open"] / base["close"] - 1) * 100,
            "close_pct": (row["close"] / base["close"] - 1) * 100,
            "mfe_pct": (row["high"] / base["close"] - 1) * 100,
            "mae_pct": (row["low"] / base["close"] - 1) * 100,
            "executed_trade": False,
            "note": "日线价格观察；没有原触发分钟顺序或成交证明。",
        })

    completed_at = now_cn()
    evidence = {
        "schema_version": 1,
        "market_date": T,
        "started_at": started_at,
        "completed_at": completed_at,
        "snapshot": {
            "file": str(SNAP.relative_to(ROOT)),
            "provider": snap["provider"],
            "exchange_scope": snap["exchange_scope"],
            "coverage": snap["coverage"],
            "errors": snap["errors"],
        },
        "provider_attempts": [
            {"provider": "Sina close snapshot", "status": "verified", "coverage": snap["coverage"], "date": T, "as_of": "post_close"},
            {"provider": "BaoStock", "status": "failed", "error": "10002007:网络接收错误", "date": T},
            {"provider": "Eastmoney HTTPS daily", "status": "two_symbol_smoke_verified", "file": "backend/data/https_daily_smoke/2026-11-06.json", "date": T},
            {"provider": "Eastmoney limit-event pools", "status": "verified_with_source_specific_counts", "errors": pool_errors, "date": T},
        ],
        "indices": {
            "source": "https://hq.sinajs.cn/list=s_sh000001,s_sz399001,s_sz399006,s_sh000688",
            "as_of": "2026-11-06 close",
            "items": [
                {"code": "000001", "name": "上证指数", "close": 3649.1774, "pct": -1.10},
                {"code": "399001", "name": "深证成指", "close": 11175.78, "pct": -2.57},
                {"code": "399006", "name": "创业板指", "close": 2465.23, "pct": -3.96},
                {"code": "000688", "name": "科创50", "close": 1253.1957, "pct": -2.60},
            ],
        },
        "market_scan": {
            "verified": len(rows), "advances": advances, "declines": declines, "unchanged": unchanged,
            "amount_yuan": amount, "previous_amount_yuan": prev_amount,
            "amount_change_pct": (amount / prev_amount - 1) * 100,
            "median_change_pct": statistics.median(r["pctChg"] for r in rows),
        },
        "event_pools": pools,
        "event_summary": {
            "limit_up_source_count": zt_data.get("tc"),
            "broken_board_source_count": zb_data.get("tc"),
            "limit_down_source_count": dt_data.get("tc"),
            "highest_consecutive_board": max_board,
            "height_names": height_names,
            "limit_up_sector_counts": sector_counts,
        },
        "history_fetch": {"requested": len(broad_seed), "verified": len(broad), "errors": history_errors},
        "broad_pool": broad,
        "deep_pool": deep,
        "close_relative_research_pair": close_pair,
        "production_intraday_frozen": {"early_pair": early, "late_pair": late},
        "prior_20261105_pool_validation": prior_validation,
        "blocked": {
            "sector_full_membership": "没有同一来源全行业成员及板块OHLCV，涨停池行业只作事件侧证据。",
            "deep_pool_minute_sequence": "没有28只深筛完整分钟序列，不能从日线高低反推触发顺序。",
            "turnover": "新浪批量收盘源未提供自由流通换手率，未反推。",
            "formal_signal": "收盘两只仅相对研究样本；未通过11月9日竞价、板块和承接门槛。",
        },
        "analysis_completed": False,
        "eligible_for_integrated_research": False,
        "rule_version": "market_review_close_v7_shsz_backup_verified_partial",
    }
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def candidate_line(row):
        return (
            f"- **{row['code']} {row['name']}**：收{fmt(row['close'])}，涨跌{fmt(row['pct'])}%，"
            f"RVOL20={fmt(row['rvol20'])}、CLV={fmt(row['clv'])}、120日位置{fmt((row['position120'] or 0)*100,1)}%；"
            "仅为收盘相对优选研究样本。11月9日须另核竞价、板块同步和回踩承接；不满足即淘汰，绝非买入许可。"
        )

    deep_rows = "\n".join(
        f"|{r['code']} {r['name']}|{'、'.join(r['tags'])}|{fmt(r['close'])}|{fmt(r['pct'])}|{fmt(r['rvol5'])}/{fmt(r['rvol10'])}/{fmt(r['rvol20'])}|{fmt((r['position120'] or 0)*100,1)}|{fmt(r['clv'])}|"
        for r in deep
    )
    prior_obs = [r for r in prior_validation if r["status"] == "daily_price_observed"]
    prior_close = [r["close_pct"] for r in prior_obs]
    intraday_lines = []
    for label, item in (("09:50", early), ("14:40", late)):
        cs = "、".join(f"{x['code']} {x['name']}@{x['price']}" for x in item["candidates"])
        intraday_lines.append(
            f"- **{label} 原时点冻结**：{cs}；{item['fresh_quotes']}/{item['scanned']} 新鲜报价，"
            f"状态 `{item['status']}`，均为 relative-shadow，`buy_order_allowed=false`。"
        )

    body = f"""# 每日复盘｜2026-11-06 普涨后全面回撤与高标收缩（来源受限实质版）

交易日 **T={T}**，计划观察日 **D=2026-11-09**。本轮用新浪独立沪深收盘快照核验 {len(rows)}/{snap['coverage']['checked']} 只（{snap['coverage']['coverage_ratio']:.2%}），北交所按最新范围排除。BaoStock同日登录失败后没有停止，而是完成备用源验证、120只广池历史补证、28只深筛、11月5日旧池验证及09:50/14:40生产冻结读回。因缺全行业成员同步、深池完整分钟顺序和自由流通换手，本报告为 **partial**，不冒充四份综合前置中的完整 `market_review`。

## 一、收盘事实与情绪

- 上证 **3649.18/-1.10%**、深成指 **11175.78/-2.57%**、创业板 **2465.23/-3.96%**、科创50 **1253.20/-2.60%**。
- 沪深个股快照：上涨 **{advances}**、下跌 **{declines}**、平盘 **{unchanged}**；中位涨跌 **{statistics.median(r['pctChg'] for r in rows):.2f}%**。
- 成交额简单加总 **{amount/1e8:.1f}亿元**，较11月5日 **{(amount/prev_amount-1)*100:.2f}%**。这是沪深股票快照口径，不含北交所。
- 东方财富事件池口径：涨停 **{zt_data.get('tc','N/A')}**、炸板 **{zb_data.get('tc','N/A')}**、跌停 **{dt_data.get('tc','N/A')}**；最高 **{max_board}板**（{'、'.join(height_names) or '未取到名称'}）。涨停行业计数靠前：{json.dumps(sorted(sector_counts.items(), key=lambda x:x[1], reverse=True)[:6], ensure_ascii=False)}。事件池为第三方源，不等同交易所官方全表。

判断：11月5日普涨后的筹码交换在11月6日转为全面回撤，深市与成长指数显著弱于上证；成交缩减但仍处高位，说明不是单纯无量阴跌。涨停高度仍存，但上涨宽度仅约13.7%，情绪属于强分歧/退潮验证阶段。

## 二、冻结广池、深池与上一池验证

- 全沪深扫描 {len(rows)} 只；活动广池固定120只后再请求历史，成功 {len(broad)}/120，不因结果换样本。
- 形成28只深筛；RVOL5/10/20分母只用T以前交易日，CLV只说明收盘在日内区间的位置，不证明分钟先后。
- 11月5日事件深池取得11月6日日线验证 {len(prior_obs)}/{len(prior_validation)}；收盘观察均值 **{fmt(statistics.mean(prior_close) if prior_close else None)}%**、中位 **{fmt(statistics.median(prior_close) if prior_close else None)}%**。这是日线观察，不是成交收益，MFE/MAE也不能替代可执行退出。

|代码/名称|结构标签|收盘|涨跌%|RVOL5/10/20|120日位置%|CLV|
|---|---|---:|---:|---:|---:|---:|
{deep_rows}

## 三、三个时段的两只相对研究候选

{chr(10).join(intraday_lines)}

**收盘相对研究二只（供后续综合研究，不是正式买点）：**

{chr(10).join(candidate_line(r) for r in close_pair) if close_pair else '- 数据规则未得到两只；不得补造。'}

正式门槛独立：09:50/14:40两组是生产端原时点腾讯报价＋前一完成日线的相对影子样本；收盘二只是本次全沪深日线研究结果。三组均未验证成交、不得下单，不相互冒充。

## 四、D=2026-11-09 条件情景（事前冻结，无概率）

- **上行修复**：上证重新站上3675、深成指站上11300、创业板站上2510，沪深上涨超过3000只且成交不低于1.55万亿元；至少一条11月6日涨停行业扩散。若上涨不足2000或创业板再失2460，则失效。
- **震荡消化**：上证3625—3675、深成指11000—11300、创业板2410—2510，上涨约1800—3000只、成交1.35—1.70万亿元。若指数与宽度同时满足上行或下行条件，则失效。
- **下行延续**：上证跌破3625、深成指跌破11000或创业板跌破2410，同时下跌超过3800只、跌停事件池继续扩散。若上证收复3655且上涨超过2800只，则失效。

以上阈值只用于下次可证伪核验，没有校准概率。

## 五、缺口与边界

1. 缺全行业成员与板块OHLCV，行业同步只能用事件池侧证，故不能标完整研究。
2. 缺28只深筛的完整分钟序列和盘口，不能补造“分歧转一致”顺序、9:50/14:40成交或尾盘触发。
3. 新浪批量源未给自由流通换手，未反推；公开盘口也不能确认资金身份。
4. `quant_research` 已取消。APP不内置大模型、不会自动训练权重或自动下单。

## 来源

- `{SNAP.relative_to(ROOT)}`（新浪沪深收盘批量快照，99.89%覆盖）
- `{EVIDENCE.relative_to(ROOT)}`（广池、深池、事件池、生产原时点读回与失败记录）
- 新浪指数：https://hq.sinajs.cn/list=s_sh000001,s_sz399001,s_sz399006,s_sh000688
- 东方财富涨停/炸板/跌停事件池（原始URL存证于证据JSON）
- 生产原时点读回：{PROD}/api/intraday-live
"""
    REPORT.write_text(body + "\n", encoding="utf-8")

    research_path = ROOT / "backend/data/research.json"
    runs_path = ROOT / "backend/data/task_runs.json"
    research = json.loads(research_path.read_text(encoding="utf-8"))
    runs = json.loads(runs_path.read_text(encoding="utf-8"))
    report_id = "market-review-20261106-partial-v1"
    receipt_id = "market-review-20261106-scheduled-close-v1-partial"
    if any(x.get("id") == report_id for x in research["items"]):
        raise ValueError("duplicate_report")
    if any(x.get("id") == receipt_id for x in runs["items"]):
        raise ValueError("duplicate_receipt")
    sources = [
        str(REPORT.relative_to(ROOT)), str(EVIDENCE.relative_to(ROOT)), str(SNAP.relative_to(ROOT)),
        f"{PROD}/api/intraday-live?slot=early_pair", f"{PROD}/api/intraday-live?slot=late_pair", ISSUE,
    ]
    research["items"].append({
        "id": report_id, "date": T, "market_date": T, "task_id": "market_review", "track": "market_review",
        "run_id": "market-review-20261106-scheduled-close-v1",
        "title": "每日复盘｜11月6日普涨后全面回撤与高标收缩（来源受限实质版）",
        "summary": f"沪深{len(rows)}/{snap['coverage']['checked']}只、上涨{advances}/下跌{declines}、成交{amount/1e8:.1f}亿元；120广池、28深筛、上一池{len(prior_obs)}只验证，并读回09:50/14:40各2只原时点影子候选。缺板块全成员和分钟顺序，保持partial。",
        "body": body, "sources": sources, "report_type": "substantive_daily_research_partial",
        "eligible_for_integrated_research": False, "analysis_completed": False, "status": "partial",
        "published_at": completed_at, "recorded_at": completed_at, "data_cutoff_at": completed_at,
        "market_data_cutoff_at": f"{T}T15:00:00+08:00", "planned_entry_date": "2026-11-09",
        "earliest_legal_exit_date_if_bought": "2026-11-10",
        "research_rule_version": evidence["rule_version"], "candidate_count": len(close_pair),
        "candidate_scope": "relative_research_only_not_formal_signal", "recommendation_ids": [],
        "codes": [r["code"] for r in deep], "full_scan_count": len(rows), "broad_pool_count": len(broad_seed),
        "broad_pool_verified_count": len(broad), "deep_pool_count": len(deep),
        "previous_pool_verified_count": len(prior_obs), "evidence_file": str(EVIDENCE.relative_to(ROOT)),
        "blocked_modules": list(evidence["blocked"]), "verified_fill_count": 0,
    })
    runs["items"].append({
        "id": receipt_id, "run_id": "market-review-20261106-scheduled-close-v1", "task_id": "market_review",
        "date": T, "trigger": "scheduled", "started_at": started_at, "completed_at": completed_at,
        "recorded_at": completed_at, "status": "partial",
        "summary": f"实质完成T=11/06沪深{len(rows)}只扫描、120广池、28深筛、上一池验证与三时段候选核验；缺全行业成员及深池分钟顺序，不标completed。",
        "report_ids": [report_id], "recommendation_ids": [], "analysis_completed": False,
        "eligible_for_integrated_research": False, "trade_executed": False,
        "delivery_status": "repository_prepared_not_yet_verified", "sources": sources,
        "blocked_modules": list(evidence["blocked"]), "verified_fill_count": 0,
    })
    research_path.write_text(json.dumps(research, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    runs_path.write_text(json.dumps(runs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report_id": report_id, "receipt_id": receipt_id, "coverage": snap["coverage"],
        "broad_verified": len(broad), "deep": len(deep),
        "close_pair": [{"code": r["code"], "name": r["name"]} for r in close_pair],
        "completed_at": completed_at,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
