#!/usr/bin/env python3
"""Collect bounded, reproducible evidence for the 2026-11-12 market review.

BaoStock is intentionally not called here: its single permitted login attempt
is already preserved in ``market_source_status/baostock-2026-11-12.json``.
This collector uses the verified Sina SH/SZ snapshots, Sina daily K lines,
Tencent indices, and one bounded attempt per Eastmoney endpoint.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import importlib.util
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
T, PREV, PREV2 = "2026-11-12", "2026-11-11", "2026-11-10"
CN = ZoneInfo("Asia/Shanghai")
OUT = ROOT / "docs/research/market-review-20261112-evidence.json"

spec = importlib.util.spec_from_file_location(
    "vp_helpers", ROOT / "scripts/publish_volume_price_20261104.py"
)
vp = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(vp)
vp.T = T


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def curl(url: str, timeout: int = 18, encoding: str = "utf-8") -> dict:
    p = subprocess.run(
        ["curl", "-fsS", "--max-time", str(timeout), "-H", "User-Agent: Mozilla/5.0", url],
        capture_output=True,
        timeout=timeout + 4,
        check=True,
    )
    return {
        "url": url,
        "retrieved_at": now_utc(),
        "body": p.stdout.decode(encoding, errors="replace"),
    }


def bounded_json(label: str, url: str, timeout: int = 18) -> dict:
    try:
        d = curl(url, timeout=timeout)
        d["payload"] = json.loads(d.pop("body"))
        d["status"] = "http_success_payload_recorded"
        return d
    except Exception as exc:
        return {
            "url": url,
            "retrieved_at": now_utc(),
            "status": "failed",
            "error": f"{type(exc).__name__}:{str(exc)[:220]}",
            "label": label,
        }


def parse_indices(raw: str) -> list[dict]:
    rows = []
    for block in raw.split(";"):
        m = re.search(r'v_([a-z0-9]+)="([^"]+)"', block)
        if not m:
            continue
        f = m.group(2).split("~")
        if len(f) < 36:
            continue
        rows.append({
            "symbol": m.group(1), "name": f[1], "code": f[2],
            "close": float(f[3]), "previous_close": float(f[4]),
            "change": float(f[31]), "change_pct": float(f[32]),
            "high": float(f[33]), "low": float(f[34]), "quote_time": f[30],
        })
    return rows


def limit_rate(row: dict) -> Decimal | None:
    name = str(row.get("name") or "").upper()
    code = row["code"].split(".")[-1]
    if name.startswith(("N", "C", "U")):
        return None
    if "ST" in name:
        return Decimal("0.05")
    if code.startswith(("300", "301", "688", "689")):
        return Decimal("0.20")
    return Decimal("0.10")


def rounded_price(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def proxy(row: dict) -> dict | None:
    rate = limit_rate(row)
    if rate is None or row.get("preclose", 0) <= 0:
        return None
    pc = Decimal(str(row["preclose"]))
    up = rounded_price(float(pc * (Decimal(1) + rate)))
    down = rounded_price(float(pc * (Decimal(1) - rate)))
    return {
        "code": row["code"].split(".")[-1], "name": row.get("name"),
        "limit_rate": float(rate), "upper_price": up, "lower_price": down,
        "sealed_up": row["close"] >= up - 0.001,
        "touched_up": row["high"] >= up - 0.001,
        "sealed_down": row["close"] <= down + 0.001,
    }


def proxy_summary(snapshot: dict) -> dict:
    rows = [p for r in snapshot["rows"] if (p := proxy(r))]
    sealed = [r for r in rows if r["sealed_up"]]
    touched = [r for r in rows if r["touched_up"]]
    down = [r for r in rows if r["sealed_down"]]
    return {
        "eligible_rows": len(rows), "sealed_up": len(sealed),
        "touched_up": len(touched), "broken_after_touch": len(touched) - len(sealed),
        "sealed_down": len(down), "sealed_up_rows": sealed,
        "sealed_down_rows": down,
        "definition": "按代码板块、ST名称和前收盘以0.01元四舍五入复算的收盘代理；排除N/C/U名称，非交易所官方事件表。",
    }


def main() -> None:
    started = now_utc()
    snaps = {}
    for d in (PREV2, PREV, T):
        path = ROOT / f"backend/data/sina_daily_full/{d}.json"
        snaps[d] = json.loads(path.read_text(encoding="utf-8"))
        if snaps[d].get("trade_date") != d or snaps[d]["coverage"]["coverage_ratio"] < .90:
            raise ValueError(f"invalid_snapshot:{d}")

    current, previous = snaps[T]["rows"], snaps[PREV]["rows"]
    previous_map = {r["code"].split(".")[-1]: r for r in previous}
    current_map = {r["code"].split(".")[-1]: r for r in current}
    names = {r["code"].split(".")[-1] for r in current if r.get("name")}
    broad_seed, market_rows = vp.freeze_broad(current, previous_map, names)

    histories, history_errors = {}, {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        jobs = {ex.submit(vp.fetch_history, r["code6"]): r["code6"] for r in broad_seed}
        for future in as_completed(jobs):
            code = jobs[future]
            try:
                histories[code] = future.result()
            except Exception as exc:
                history_errors[code] = f"{type(exc).__name__}:{str(exc)[:160]}"
    broad = []
    for seed in broad_seed:
        code = seed["code6"]
        if code not in histories:
            continue
        item = vp.metrics(histories[code], current_map[code])
        item.update({"name": current_map[code]["name"], "amount_yuan": current_map[code]["amount"]})
        if "ST" in item["name"].upper():
            item["tags"] = ["ST风险对照"]
        broad.append(item)
    deep = vp.select_deep(broad)
    relative = [
        r for r in deep
        if "ST" not in r["name"].upper()
        and -3 <= r["pct"] <= 8
        and (r["rvol20"] or 0) >= 1.15
        and (r["clv"] or 0) >= .62
        and (r["position120"] or 1) <= .78
        and r["amount_yuan"] >= 100_000_000
    ]
    relative.sort(key=lambda r: (
        2 * (r["clv"] or 0) + min(r["rvol20"] or 0, 3)
        + (1 - (r["position120"] or 1)) - max(r["pct"] - 5, 0) / 5
    ), reverse=True)

    idx_url = "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688"
    try:
        idx_raw = curl(idx_url, encoding="gb18030")
        indices = {"url": idx_url, "retrieved_at": idx_raw["retrieved_at"], "status": "verified", "items": parse_indices(idx_raw["body"])}
    except Exception as exc:
        indices = {"url": idx_url, "retrieved_at": now_utc(), "status": "failed", "error": f"{type(exc).__name__}:{exc}"}

    base = "https://push2ex.eastmoney.com"
    ut = "7eea3edcaed734bea9cbfc24409ed9893"
    pools = {}
    for d in (PREV, T):
        pools[d] = {}
        for kind, sort in (("ZT", "fbt:asc"), ("ZB", "fbt:asc"), ("DT", "fund:asc")):
            u = f"{base}/getTopic{kind}Pool?ut={ut}&dpt=wz.ztzt&Pageindex=0&pagesize=1000&sort={sort}&date={d.replace('-', '')}"
            pools[d][kind] = bounded_json(f"eastmoney_{kind}_{d}", u, timeout=9)

    sector_url = (
        "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&fs=m%3A90%2Bt%3A2&fltt=2&"
        "fields=f12%2Cf14%2Cf2%2Cf3%2Cf6%2Cf104%2Cf105%2Cf124&fid=f3&po=1"
    )
    sectors = bounded_json("eastmoney_sector_top100", sector_url, timeout=14)

    proxies = {d: proxy_summary(snaps[d]) for d in (PREV2, PREV, T)}
    sets = {d: {r["code"] for r in proxies[d]["sealed_up_rows"]} for d in proxies}
    current_streaks = []
    for row in proxies[T]["sealed_up_rows"]:
        code = row["code"]
        streak = 1 + int(code in sets[PREV]) + int(code in sets[PREV] and code in sets[PREV2])
        current_streaks.append({"code": code, "name": row["name"], "three_day_streak_lower_bound": streak})
    max_streak = max((r["three_day_streak_lower_bound"] for r in current_streaks), default=0)

    advances = sum(r["pctChg"] > 0 for r in current)
    declines = sum(r["pctChg"] < 0 for r in current)
    flat = len(current) - advances - declines
    amount = sum(r["amount"] for r in current)
    prev_amount = sum(r["amount"] for r in previous)
    evidence = {
        "schema_version": 1, "market_date": T, "started_at": started, "completed_at": now_utc(),
        "exchange_scope": "Shanghai+Shenzhen stocks only; Beijing excluded",
        "snapshots": {d: {"path": f"backend/data/sina_daily_full/{d}.json", "provider": snaps[d]["provider"], "coverage": snaps[d]["coverage"], "collected_at": snaps[d]["collected_at"]} for d in snaps},
        "source_attempts": [
            {"provider": "BaoStock", "status": "failed", "date": T, "evidence": "backend/data/market_source_status/baostock-2026-11-12.json"},
            {"provider": "Sina close snapshot", "status": "verified", "date": T, "coverage": snaps[T]["coverage"], "type": "post-close historical observation"},
            {"provider": "Sina unadjusted daily K", "status": "verified_partial_pool", "date": T, "requested": len(broad_seed), "verified": len(broad), "errors": history_errors, "type": "historical daily"},
            {"provider": "Tencent index quote", "status": indices["status"], "date": T, "type": "timestamped close quote"},
            {"provider": "Eastmoney event pools", "status": "responses_recorded_not_assumed_valid", "date": T, "type": "event pool"},
            {"provider": "Eastmoney sector ranking", "status": sectors["status"], "date": T, "type": "sector snapshot"},
        ],
        "indices": indices,
        "market_scan": {
            "verified": len(current), "checked": snaps[T]["coverage"]["checked"], "advances": advances,
            "declines": declines, "flat": flat, "median_change_pct": statistics.median(r["pctChg"] for r in current),
            "amount_yuan": amount, "previous_amount_yuan": prev_amount,
            "amount_change_pct": (amount / prev_amount - 1) * 100,
        },
        "broad_pool": broad, "deep_pool": deep, "relative_research_pair": relative[:2],
        "history_fetch": {"frozen": len(broad_seed), "verified": len(broad), "errors": history_errors},
        "eastmoney_event_pool_attempts": pools, "eastmoney_sector_attempt": sectors,
        "limit_proxy": proxies,
        "three_day_proxy": {
            "current_streaks": current_streaks, "max_streak_lower_bound": max_streak,
            "previous_sealed_count": len(sets[PREV]), "previous_sealed_still_sealed": len(sets[PREV] & sets[T]),
            "retention_pct": (len(sets[PREV] & sets[T]) / len(sets[PREV]) * 100) if sets[PREV] else None,
            "warning": "仅3日收盘代理；不等于媒体首板/二板晋级分母，不能替代完整封板过程。",
        },
        "external_close_crosscheck": {
            "current": "https://www.kanpanba.com/limit/2026-11-12",
            "previous": "https://www.kanpanba.com/limit/2026-11-11",
            "current_counts_observed": {"limit_up": 37, "broken": 35, "seal_rate_pct": 51, "highest_board": 5, "one_to_two": "5/61", "two_to_three": "2/12", "higher": "4/7"},
            "previous_counts_observed": {"limit_up": 84, "broken": 19, "seal_rate_pct": 82, "highest_board": 4, "one_to_two": "9/62", "two_to_three": "5/15", "higher": "2/5"},
            "sector_continuity": "机器人仍为最大事件主题但封板显著分化；光通信/PCB由11日扩散转为12日较多炸板；股权重组、东方/羊字辈、消费保持局部高度。",
            "source_type": "independent public market recap; not exchange official event table",
        },
        "announcement_risk": [
            {"code": "603366", "name": "日出东方", "fact": "上交所检索显示2026-09-23董事及高级管理人员减持股份计划公告；当前5板仅作高位风险背景。", "source": "https://www.sse.com.cn/home/search/?webswd=603366"},
            {"code": "605255", "name": "天普股份", "fact": "上交所检索显示2026-10-30股票交易风险提示公告称市净率显著高于行业；证监会此前对异常波动公告涉嫌重大遗漏立案调查。", "source": "https://www.sse.com.cn/home/search/index.shtml?webswd=%E5%B8%82%E5%87%80%E7%8E%87"},
        ],
        "blocked": {
            "official_limit_event_table": "交易所官方完整涨停/炸板/跌停事件表未取得；东财三类池HTTP200但rc=205/data=null。",
            "full_sector_membership": "东财行业Top100接口本轮超时或响应受限；板块持续性采用独立公开复盘页交叉，不称全行业成员扫描。",
            "minute_sequence": "本报告为盘后市场复盘，没有为28只深池补造分钟触发顺序或成交。",
        },
        "research_rule_version": "market_review_close_v8_shsz_sina_tencent_external_event_crosscheck",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "market_date": T, "coverage": snaps[T]["coverage"], "indices": indices.get("items"),
        "market_scan": evidence["market_scan"], "history_fetch": evidence["history_fetch"],
        "limit_proxy": {d: {k: v for k, v in proxies[d].items() if not k.endswith("_rows")} for d in proxies},
        "relative_pair": relative[:2], "output": str(OUT.relative_to(ROOT)),
    }, ensure_ascii=False))


if __name__ == "__main__":
    if "--repair-indices" in sys.argv:
        evidence = json.loads(OUT.read_text(encoding="utf-8"))
        idx_url = "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688"
        idx_raw = curl(idx_url, encoding="gb18030")
        items = parse_indices(idx_raw["body"])
        if len(items) != 4 or any(x["quote_time"][:8] != "20261112" for x in items):
            raise ValueError("four_current_index_quotes_required")
        evidence["indices"] = {"url": idx_url, "retrieved_at": idx_raw["retrieved_at"], "status": "verified", "items": items}
        for row in evidence["source_attempts"]:
            if row["provider"] == "Tencent index quote":
                row["status"] = "verified"
                row["parser_repaired_at"] = now_utc()
        OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(items, ensure_ascii=False))
    else:
        main()
