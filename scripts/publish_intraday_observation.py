#!/usr/bin/env python3
"""Append a timestamped, explicitly non-actionable intraday watch report.

This produces no stock recommendation records. Reports are immutable archives
and must be committed before a task receipt may reference them.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from research_archive import validate_document, verify_append_only


def append_observation(archive, outcome, run_id):
    snapshot = outcome.get("snapshot")
    if not snapshot or outcome.get("reason") != "screened_watch_not_validated_strategy":
        return archive, None, False
    day = outcome["market_date"]
    slot = outcome["task_id"]
    if slot not in ("early_pair", "late_pair"):
        raise ValueError("invalid_observation_task")
    observation_id = "intraday-watch-" + day.replace("-", "") + "-" + slot + "-gh" + str(run_id)
    if any(row["id"] == observation_id for row in archive["items"]):
        return archive, observation_id, False
    candidates = outcome.get("candidate_watch", [])
    checked_at = outcome["checked_at"]
    titles = {"early_pair": "09:50", "late_pair": "14:40"}
    lines = [
        "【非荐股／不可直接交易】北京时间 " + checked_at + " 的盘中部分股票池观察。",
        "覆盖：" + str(snapshot.get("quote_count")) + "只当时有效报价，"
        + str(snapshot.get("requested_count")) + "只请求；仅既有研究池、东方财富及新浪可访问的成交活跃股票，不是A股全市场扫描。",
        "数据源：" + str(snapshot.get("source")) + "；有效性仅检验源格式、报价时间、昨收、成交量和成交额。",
        "报价源分布：" + str(snapshot.get("provider_quote_counts", {}))
        + "；两家源同时点复核" + str(snapshot.get("corroborated_count", 0))
        + "只；冲突剔除" + str(snapshot.get("provider_disagreements", 0))
        + "只；采集覆盖率" + str(snapshot.get("fresh_coverage_pct", 0)) + "%。",
        "筛选逻辑：排除ST/BJ；一定涨幅区间、成交额≥0.8亿元、换手2%至35%；仅为启发式排序，"
        "尚未验证龙虎榜、板块同步、盘口承接、封板概率、隔日溢价或T+1可行性。",
    ]
    if candidates:
        for i, row in enumerate(candidates, 1):
            lines.append(
                str(i) + ". " + row["name"] + "（" + row["code"] + "）"
                + "，当时价" + str(row["price"]) + "元，涨幅" + str(row["pct"])
                + "%，成交额" + str(row["amount_yi"]) + "亿元，换手"
                + str(row["turnover_ratio"]) + "%，观察分" + str(row["heuristic_score"])
                + "；行情时间 " + row["as_of"] + "。仅作复核候选，未形成买入信号。"
            )
    else:
        lines.append("筛选通过0只；不以缺失数据强行推荐股票。")
    lines.append("重要：未完成历史回测和样本外验证；本结果不能升级为成功荐股或投资建议。")
    item = {
        "id": observation_id, "date": day,
        "task_id": slot, "track": "market_review",
        "title": titles[slot] + "真实行情观察（非交易推荐）",
        "published_at": checked_at,
        "source_cutoff_at": snapshot.get("as_of"),
        "evidence_status": "partial_quote_verified_strategy_unverified",
        "report_type": "intraday_screening_observation",
        "body": "\n".join(lines),
        "sources": sorted(set([snapshot["source"]] + [r["source"] for r in candidates])),
        "candidate_count": len(candidates), "universe_count": snapshot["quote_count"],
    }
    after = dict(archive)
    after["items"] = archive["items"] + [item]
    validate_document(after, "research")
    verify_append_only(archive, after, "research")
    return after, observation_id, True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--outcome", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--archive", default=str(ROOT / "backend/data/research.json"))
    args = p.parse_args()
    outcome_path = Path(args.outcome)
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    path = Path(args.archive)
    archive = json.loads(path.read_text(encoding="utf-8"))
    new, report_id, changed = append_observation(archive, outcome, args.run_id)
    if changed:
        path.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report_id:
        outcome["observation_report_id"] = report_id
        outcome_path.write_text(json.dumps(outcome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"changed": changed, "report_id": report_id}, ensure_ascii=False))


if __name__ == "__main__":
    main()
