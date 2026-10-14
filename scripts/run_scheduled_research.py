#!/usr/bin/env python3
"""Auditable after-close partial research for previously unwired APP task tracks.

This is NOT an LLM, an entire A-share market scanner, or a backtested trading
strategy. It records reproducible observations and explicit missing evidence.
Every GitHub Action attempt is an immutable event. No orders or retrospective
recommendations are synthesized, including on a retry.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from daily_providers import tencent_daily
from quote_providers import tencent_quotes
from research_archive import load_document, validate_document, verify_append_only
from task_center import validate_runs
from trading_calendar import session_state, completed_bars

CN = ZoneInfo("Asia/Shanghai")
INDEXES = ("sh000001", "sz399001", "sz399006", "sh000688")
TASKS = ("market_review", "volume_price", "limitup_single", "combined_pair", "low_position")
DAILY_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
QUOTE_URL = "https://qt.gtimg.cn/"
MIN_SAMPLE = 12


def eligible(now):
    """Only the present completed session; never convert a missed day into a live signal."""
    state = session_state(now)
    return state["code"] == "after_close" and (now.hour, now.minute) >= (15, 15)


def candidates():
    """Pre-existing research universe, NOT an independent market-wide screener."""
    pool = []
    for filename in ("research_stocks.json", "recommendations.json"):
        try:
            records = load_document(filename)["items"]
        except (OSError, ValueError, KeyError):
            continue
        for row in records:
            code = str(row.get("code") or "")
            if len(code) == 6 and code.isdigit() and code.startswith(("00", "30", "60", "68")):
                pool.append(code)
    return list(dict.fromkeys(pool))[:90]


def analyze_one(code, now, provider=tencent_daily):
    bars = completed_bars(provider(code, limit=125, adjust="1"), now)
    if len(bars) < 26 or bars[-1]["date"] != now.date().isoformat():
        raise ValueError("insufficient_same_day_history")
    recent = bars[-1]
    prev = bars[-2]
    vol = sum(x["volume"] for x in bars[-21:-1]) / 20
    if not vol or prev["close"] <= 0:
        raise ValueError("invalid_volume_or_prior_close")
    day_range = recent["high"] - recent["low"]
    ma20 = sum(x["close"] for x in bars[-20:]) / 20
    return {
        "code": code, "date": recent["date"], "close": round(recent["close"], 3),
        "day_pct_proxy": round((recent["close"] / prev["close"] - 1) * 100, 2),
        "relative_volume20": round(recent["volume"] / vol, 2),
        "close_location": round((recent["close"] - recent["low"]) / day_range, 3) if day_range > 0 else None,
        "distance_ma20_pct": round((recent["close"] / ma20 - 1) * 100, 2),
        "distance_60d_low_pct": round((recent["close"] / min(b["low"] for b in bars[-60:]) - 1) * 100, 2),
        "distance_60d_high_pct": round((recent["close"] / max(b["high"] for b in bars[-60:]) - 1) * 100, 2),
        "adjustment": "qfq", "provider": "tencent_daily",
    }


def collect(now, pool=None, day_provider=None, quote_provider=None, workers=6):
    if not eligible(now):
        return {"eligible": False, "day": now.date().isoformat(), "reason": session_state(now)["code"]}
    pool = list(dict.fromkeys(candidates() if pool is None else pool))[:90]
    day_provider = day_provider or tencent_daily
    quote_provider = quote_provider or tencent_quotes
    errors = Counter()
    indexes = []
    try:
        quotes = quote_provider(INDEXES)
        for quote in quotes:
            observed = datetime.fromisoformat(quote["as_of"])
            if (observed.tzinfo and observed.astimezone(CN).date() == now.date()
                    and observed.astimezone(CN).time() >= time(14, 55)):
                indexes.append({k: quote.get(k) for k in ("code", "name", "price", "pct", "as_of", "source")})
        if len(indexes) != len(INDEXES):
            errors["missing_or_stale_index_quote"] += len(INDEXES) - len(indexes)
    except Exception as exc:
        errors["index_quote_" + type(exc).__name__] += 1
    observations = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as executor:
        jobs = {executor.submit(analyze_one, code, now, day_provider): code for code in pool}
        for job in as_completed(jobs):
            try:
                observations.append(job.result())
            except Exception as exc:
                errors["daily_" + type(exc).__name__] += 1
    observations.sort(key=lambda x: x["code"])
    return {
        "eligible": True, "day": now.date().isoformat(), "indexes": indexes,
        "checked": len(pool), "fresh": len(observations), "observations": observations,
        "errors": dict(errors), "universe": "existing_watchlist_and_archived_recommendations_only",
        "full_a_share_coverage": False, "minute_orderflow_verified": False,
        "limit_up_board_verified": False, "strategy_validated": False,
    }


def build_reports(snapshot, now):
    """A partially successful computation remains 'partial', not 'completed'."""
    stamp = now.isoformat(timespec="seconds")
    day = snapshot["day"]
    fresh = snapshot["fresh"]
    rows = snapshot["observations"]
    sources = [QUOTE_URL, DAILY_URL]
    meta = (f"证据日期（北京时间）：{day}；实际扫描已关注研究池{snapshot['checked']}只；"
            f"同日有效日线{fresh}只；并非全A扫描。数据错误：{snapshot['errors']}。"
            "样本范围、存活偏差与供应商不可用均可能影响判断。")
    ix = "；".join(f"{r['name'] or r['code']} {r['price']}（{r['pct']:+.2f}%）" for r in snapshot["indexes"])
    strong = [r for r in rows if r["relative_volume20"] >= 1.5 and
              r["close_location"] is not None and r["close_location"] >= .75 and
              0 <= r["distance_ma20_pct"] <= 15]
    weak = [r for r in rows if r["close_location"] is not None and r["close_location"] <= .25]
    low_launch = [r for r in rows if 0 <= r.get("distance_60d_low_pct", 999) <= 25
                  and 1.5 <= r["relative_volume20"] <= 5
                  and 0 <= r["distance_ma20_pct"] <= 15
                  and r["close_location"] is not None and r["close_location"] >= .7]
    low_launch.sort(key=lambda x: (x["distance_60d_low_pct"], -x["relative_volume20"], x["code"]))
    strong.sort(key=lambda x: (-x["relative_volume20"], x["code"]))
    weak.sort(key=lambda x: (x["close_location"], x["code"]))
    fmt = lambda x: f"{x['code']} 日变动{x['day_pct_proxy']:+.2f}% 量比{x['relative_volume20']:.2f} 收盘位置{x['close_location']} 距MA20{x['distance_ma20_pct']:+.2f}%"
    def pack(task, track, title, summary, body, sufficient=True):
        status = "partial" if sufficient else "blocked"
        return {"task_id": task, "track": track, "title": title, "summary": summary,
                "body": f"【当天自动取证｜{status}，不是已完成全市场研究】\n采集时间：{stamp}\n" + body,
                "sources": sources, "execution_scope": "partial_research_universe",
                "provenance": "contemporaneous_observation_not_recommendation",
                "validation_status": "partial_not_tradeable", "run_status": status,
                "analysis_completed": False, "eligible_for_integrated_research": False}
    result = [
        pack("market_review", "market_review", f"{day} 盘后指数与样本广度研究",
             f"同日指数{len(snapshot['indexes'])}/4，股票{fresh}/{snapshot['checked']}只，暂未完成全市场复盘。",
             meta + "\n核验指数：" + (ix or "缺少当天可核验指数")
             + f"\n研究池上涨{sum(r['day_pct_proxy']>0 for r in rows)}只、下跌{sum(r['day_pct_proxy']<0 for r in rows)}只（非全市场涨跌家数）。"
             + "\n未取得全市场行业广度、题材情绪、高度板与龙虎榜，不能生成完整次日方向判断。",
             len(snapshot["indexes"]) >= 3 and fresh >= MIN_SAMPLE),
        pack("volume_price", "volume_price", f"{day} 量价样本独立观察",
             f"完成{fresh}只有效样本量价核验；强量价形态{len(strong)}只、弱承接{len(weak)}只。",
             meta + "\n条件型放量收盘强势样本（前复权日线，仅研究）：\n"
             + ("\n".join(map(fmt, strong[:10])) or "无")
             + "\n高位承接偏弱样本：\n"
             + ("\n".join(map(fmt, weak[:10])) or "无")
             + "\n强弱阈值未经历史样本外验证。缺完整盘口、资金身份与可成交性，禁止把名单转换成自动买入指令。",
             fresh >= MIN_SAMPLE),
        pack("limitup_single", "market_review", f"{day} 打板生态取证状态",
             "已有局部收盘涨幅代理；全市场涨停高度、封板时间、炸板率和可成交证据缺失，本轮不发布打板单股。",
             meta + "\n研究池收盘涨幅超过9.7%的代理样本数="
             + str(sum(x["day_pct_proxy"] >= 9.7 for x in rows))
             + "。不同板块涨跌停幅度、ST与新股规则不同，前复权收益率不等于交易所核验的涨停；"
             + "代理样本不得被称为实际涨停。无法检查空间板、进阶板、封单与炸板，正式打板候选=0，策略成功率未知。",
             fresh >= MIN_SAMPLE),
        pack("low_position", "low_position", f"{day} 低位启动30日跟踪：当日样本筛查",
             f"已有研究池{fresh}只同日有效日线中，满足低位放量形态代理{len(low_launch)}只。尚未完成全市场低位启动扫描。",
             meta + "\n筛选条件（仅供待检验样本观察）：距离近60根日线最低点0%~25%、日量比1.5~5、"
             + "高于MA20 0%~15%、收盘落当日区间上30%；不代表主力吸筹事实、已成交或有效预测。"
             + "\n满足代理条件的观察名单：\n"
             + ("\n".join(fmt(x) + f" 距60日最低点{x['distance_60d_low_pct']:+.2f}%" for x in low_launch[:10]) or "无")
             + "\n30个交易日跟踪尚未完整接通；T+1/T+2/T+5/T+10真实结果、除权及停牌验证需按信号冻结时间逐日取证。"
             + "代理样本不能作为新荐股，亦不能从研究池推广至全A胜率。",
             fresh >= MIN_SAMPLE),
        {"task_id": "combined_pair", "track": "market_review",
         "title": f"{day} 综合双标前置审核",
         "summary": "盘后自动核对显示全市场复盘与打板微观证据不齐；当日新综合双标0只。",
         "body": "【当天自动执行的前置审核，不是荐股】\n采集时间：" + stamp + "\n" + meta
         + "\n当前只有研究池局部量价与指数快照，前置研究未达到完整交付标准；"
         + "综合输出0只，不能事后强行选2只，也不意味着建议买入。",
         "sources": sources, "execution_scope": "dependency_audit_only",
         "provenance": "contemporaneous_observation_not_recommendation",
         "validation_status": "blocked_by_incomplete_dependencies", "run_status": "waiting",
         "analysis_completed": False, "eligible_for_integrated_research": False},
    ]
    return result


def stage(reports, runs, registry, snapshot, gh_run_id, now):
    """Append-only staged files; each run ID creates separately auditable attempts."""
    if not str(gh_run_id).isdigit():
        raise ValueError("github_run_id_required")
    if not snapshot["eligible"]:
        return reports, runs, {"changed_reports": False, "changed_runs": False,
                               "date": snapshot["day"], "status": "skipped"}
    before_reps, before_runs = reports, runs
    new_reps = {**reports, "items": list(reports["items"])}
    new_runs = {**runs, "items": list(runs["items"])}
    taken_reports = {x["id"] for x in new_reps["items"]}
    taken_runs = {x["id"] for x in new_runs["items"]}
    stamp = now.isoformat(timespec="seconds")
    statuses = {}
    for row in build_reports(snapshot, now):
        key = f"scheduled-research-{snapshot['day'].replace('-', '')}-{gh_run_id}-{row['task_id']}"
        report_id = key + "-report"
        receipt_id = key + "-receipt"
        status = row.pop("run_status")
        statuses[row["task_id"]] = status
        if report_id not in taken_reports:
            new_reps["items"].append({**row, "id": report_id, "date": snapshot["day"],
                                      "published_at": stamp, "run_id": str(gh_run_id)})
        if receipt_id not in taken_runs:
            new_runs["items"].append({
                "id": receipt_id, "run_id": "github-actions-" + str(gh_run_id),
                "task_id": row["task_id"], "date": snapshot["day"],
                "trigger": "scheduled", "started_at": stamp, "recorded_at": stamp,
                "completed_at": stamp, "status": status,
                "summary": row["summary"] + ("【范围受限，未完成全部研究】" if status == "partial" else ""),
                "report_ids": [report_id], "recommendation_ids": [],
                "analysis_completed": False, "eligible_for_integrated_research": False,
                "research_coverage": "historical_universe_partial",
            })
    validate_document(new_reps, "research")
    validate_runs(new_runs, registry)
    verify_append_only(before_reps, new_reps, "research")
    verify_append_only(before_runs, new_runs, "task_runs")
    return new_reps, new_runs, {
        "changed_reports": len(new_reps["items"]) != len(before_reps["items"]),
        "changed_runs": len(new_runs["items"]) != len(before_runs["items"]),
        "date": snapshot["day"], "statuses": statuses,
        "sample_size": snapshot["checked"], "fresh_daily": snapshot["fresh"],
        "index_count": len(snapshot["indexes"]), "errors": snapshot["errors"],
        "status": "partial_or_blocked",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--result", default="scheduled_research_status.json")
    args = parser.parse_args()
    now = datetime.now(CN)
    snapshot = collect(now)
    reports = load_document("research.json", "ROBIN_RESEARCH_FILE")
    runs = load_document("task_runs.json", "ROBIN_TASK_RUNS_FILE")
    tasks = load_document("tasks.json", "ROBIN_TASKS_FILE")
    updated_reports, updated_runs, info = stage(reports, runs, tasks, snapshot, args.run_id, now)
    if info["changed_reports"]:
        (ROOT / "backend/data/research.json").write_text(
            json.dumps(updated_reports, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if info["changed_runs"]:
        (ROOT / "backend/data/task_runs.json").write_text(
            json.dumps(updated_runs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(args.result).write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info, ensure_ascii=False))
    return 0 if info["status"] == "skipped" or snapshot.get("fresh", 0) >= MIN_SAMPLE else 2


if __name__ == "__main__":
    raise SystemExit(main())
