#!/usr/bin/env python3
"""Complete the 2026-10-22 research set and learning review from archived evidence.

This is an append-only publication helper.  It reuses the immutable full-market
snapshot, independently recomputes the volume/low-position views, preserves raw
daily observations, and never turns a quote observation into a trade fill.
"""

from collections import Counter
from datetime import date, datetime, timezone
import json
import statistics
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backend/data"
T = "2026-10-22"
D = "2026-10-23"
EXIT = "2026-10-26"
MARKET_ID = "market-review-20261022-close-v1"
EVIDENCE_FILE = "docs/research/completion-2026-10-22-evidence.json"
REPORT_IDS = {
    "volume_price": "volume-price-20261022-close-v1",
    "low_position": "low-position-20261022-close-v1",
    "dragon_tiger": "dragon-tiger-20261022-close-v1",
    "combined_pair": "combined-pair-20261022-close-v1",
    "learning_review": "learning-review-20261022-forward-v1",
}


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def save(path, value):
    (ROOT / path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def symbol(code):
    return ("sh" if code.startswith(("5", "6", "9")) else "sz") + code


def fetch_daily(code):
    url = (
        "https://quotes.sina.cn/cn/api/json_v2.php/"
        "CN_MarketDataService.getKLineData?symbol=" + symbol(code) + "&scale=240&ma=no&datalen=180"
    )
    if code.startswith(("5", "6", "9")):
        url = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param=" + symbol(code) + ",day,,,180"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raw = [{"day": row[0], "open": row[1], "close": row[2], "high": row[3],
                "low": row[4], "volume": row[5]}
               for row in payload["data"][symbol(code)]["day"]]
    else:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urlopen(req, timeout=20) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except Exception:
            url = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param=" + symbol(code) + ",day,,,180"
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            raw = [{"day": row[0], "open": row[1], "close": row[2], "high": row[3],
                    "low": row[4], "volume": row[5]}
                   for row in payload["data"][symbol(code)]["day"]]
    rows = []
    for row in raw:
        day = row.get("day") or row.get("date")
        if not day or day > T:
            continue
        rows.append({
            "date": day,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        })
    if not rows or rows[-1]["date"] != T:
        raise RuntimeError(f"missing {T} daily bar for {code}")
    return url, rows


def pct(value, reference):
    return round((value / reference - 1) * 100, 3)


def mean(values):
    return round(statistics.mean(values), 3) if values else None


def median(values):
    return round(statistics.median(values), 3) if values else None


def table(headers, rows):
    return "\n".join([
        "|" + "|".join(headers) + "|",
        "|" + "|".join(["---"] * len(headers)) + "|",
        *["|" + "|".join(str(cell) for cell in row) + "|" for row in rows],
    ])


def derived_snapshot(code, name, bars, reported=None):
    current = bars[-1]
    previous = bars[-2]
    closes = [row["close"] for row in bars]
    volumes = [row["volume"] for row in bars]
    def avg(n):
        return statistics.mean(closes[-n:]) if len(closes) >= n else None
    def rvol(n):
        return current["volume"] / statistics.mean(volumes[-n-1:-1]) if len(volumes) > n else None
    def position(n):
        if len(bars) < n:
            return None
        low = min(row["low"] for row in bars[-n:])
        high = max(row["high"] for row in bars[-n:])
        return round((current["close"] - low) / (high - low) * 100, 3) if high > low else None
    clv = ((current["close"] - current["low"]) /
           (current["high"] - current["low"])) if current["high"] > current["low"] else None
    ma20 = avg(20)
    return {
        "code": code,
        "name": name,
        "date": T,
        **current,
        "previous_close": previous["close"],
        "daily_change_pct": pct(current["close"], previous["close"]),
        "rvol": {str(n): round(rvol(n), 6) if rvol(n) is not None else None for n in (5, 10, 20)},
        "ma": {str(n): round(avg(n), 6) if avg(n) is not None else None for n in (5, 10, 20, 60)},
        "range_position_pct": {str(n): position(n) for n in (20, 60, 120)},
        "clv": round(clv, 6) if clv is not None else None,
        "distance_ma20_pct": pct(current["close"], ma20) if ma20 else None,
        "reported_proxy": reported,
        "evidence_status": "same_day_closed_daily_recomputed_from_sina",
        "missing": ["auction", "minute_OHLC", "order_book", "ticks", "verified_fill"],
    }


INSTITUTION = [
    ("301563", "云汉芯城", 16.16, 11.02, 2630.64), ("002696", "百洋股份", -6.75, 39.36, 2136.20),
    ("920157", "宇特光电", 1.58, 42.16, 2008.92), ("920296", "文峰光电", -8.73, 68.16, 1290.38),
    ("300839", "博汇股份", 20.00, 14.53, 1001.37), ("002343", "慈文传媒", -6.16, 32.95, 877.97),
    ("301227", "森鹰窗业", -20.00, 12.53, 515.42), ("920229", "世纪数码", 3.69, 29.06, 346.85),
    ("920096", "嘉晨智能", -5.69, 38.21, 275.91), ("301569", "联亚药业", -12.76, 41.03, 237.06),
    ("301023", "奕帆传动", 19.99, 20.67, 163.54), ("301686", "中塑股份", 7.93, 44.30, -79.20),
    ("301052", "果麦文化", -13.75, 34.53, -230.60), ("920196", "南方乳业", -4.69, 29.54, -288.09),
    ("000011", "深物业A", -9.96, 13.73, -882.19), ("600202", "哈空调", 10.05, 28.46, -1212.90),
    ("000678", "襄阳轴承", 9.96, 15.95, -1352.68), ("301502", "华阳智能", 20.00, 14.04, -1482.71),
    ("000530", "冰山冷热", 9.97, 45.41, -1770.39), ("002815", "崇达技术", -10.00, 12.17, -2497.47),
    ("301591", "肯特股份", 6.83, 48.74, -2676.93), ("002647", "仁东控股", -8.96, 4.05, -3235.64),
    ("002307", "北新路桥", 10.06, 12.66, -3742.74), ("301313", "凡拓数创", -1.92, 35.65, -4719.58),
    ("002181", "粤传媒", -9.96, 16.72, -5549.01), ("002388", "新亚制程", -10.00, 20.18, -6134.36),
    ("002085", "万丰奥威", -10.01, 6.86, -6973.85), ("002912", "中新赛克", -6.85, 14.69, -7154.55),
    ("002980", "华盛昌", -10.00, 12.80, -10461.89),
]

STOCK_CONNECT = [
    ("002815", "崇达技术", 11551.13, -10.00, 12.17), ("002724", "海洋王", 2637.54, 10.01, 20.18),
    ("002181", "粤传媒", 1831.61, -9.96, 16.72), ("601811", "新华文轩", 612.55, -5.53, 8.15),
    ("301563", "云汉芯城", 155.35, 16.16, 11.02), ("000678", "襄阳轴承", 151.70, 9.96, 15.95),
    ("600178", "东安动力", -95.82, -9.96, 22.40), ("000032", "深桑达A", -218.36, -10.00, 7.66),
    ("601566", "九牧王", -513.84, -6.35, 10.52), ("000011", "深物业A", -638.63, -9.96, 13.73),
    ("603767", "中马传动", -773.43, -9.50, 8.56), ("603155", "新亚强", -895.27, -10.02, 7.56),
    ("603105", "芯能科技", -1173.80, -10.02, 7.82), ("002647", "仁东控股", -1557.39, -8.96, 4.05),
    ("002085", "万丰奥威", -2175.13, -10.01, 6.86), ("600127", "金健米业", -5006.91, -9.99, 26.85),
    ("002980", "华盛昌", -7126.31, -10.00, 12.80),
]


def build():
    research = load("backend/data/research.json")
    runs = load("backend/data/task_runs.json")
    learning = load("backend/data/learning.json")
    volume = load("backend/data/volume_price_samples.json")
    low = load("backend/data/low_position_samples.json")
    market = load("docs/research/market-review-2026-10-22-evidence.json")
    if any(row["id"] == REPORT_IDS["learning_review"] for row in research["items"]):
        print("already published")
        return
    report_index = {row["id"]: row for row in research["items"]}
    assert report_index[MARKET_ID]["eligible_for_integrated_research"] is True
    assert any(row["status"] == "completed" and MARKET_ID in row.get("report_ids", []) for row in runs["items"])

    started = datetime.now(timezone.utc)
    stamp_cn = started.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    stamp_utc = started.isoformat(timespec="seconds")

    low_codes = {row["code"]: row for row in low["items"]}
    proxy_names = {"600900": "长江电力", "000420": "吉林化纤", "601288": "农业银行", "002520": "日发精机"}
    all_codes = sorted(set(low_codes) | set(proxy_names))
    raw_histories, fetch_errors = {}, {}
    for code in all_codes:
        try:
            url, bars = fetch_daily(code)
            raw_histories[code] = {"source": url, "bars": bars}
        except Exception as exc:
            fetch_errors[code] = type(exc).__name__ + ": " + str(exc)
    if fetch_errors:
        raise RuntimeError("daily fetch incomplete: " + json.dumps(fetch_errors, ensure_ascii=False))

    low_validations = []
    for code, sample in low_codes.items():
        bars = raw_histories[code]["bars"]
        current = bars[-1]
        path = [row for row in bars if sample["date"] < row["date"] <= T]
        reference = float(sample["day0_close"])
        prior_obs = sample.setdefault("observations", [])
        closes = [row["close"] for row in path]
        peaks, max_dd = [], 0.0
        for close in closes:
            peaks.append(close if not peaks else max(peaks[-1], close))
            max_dd = min(max_dd, close / peaks[-1] - 1)
        row = {
            "id": sample["id"] + "-close-20261022",
            "code": code, "name": sample["name"], "date": T,
            "reference_date": sample["date"], "reference_close": reference,
            "origin_cohort_id": sample["id"], "report_ids": [REPORT_IDS["low_position"]],
            "observation_type": "price_observation", "evidence_status": "single_provider_closed_daily_with_full_path",
            "full_validation_completed": True, "eligible_for_model_statistics": bool(sample.get("eligible_for_model_statistics")),
            "executed_trade": False, "executable_net_return_pct": None,
            "price_observation": current, "close_return_pct": pct(current["close"], reference),
            "path_mfe_pct": pct(max(x["high"] for x in path), reference) if path else None,
            "path_mae_pct": pct(min(x["low"] for x in path), reference) if path else None,
            "max_close_to_close_drawdown_pct": round(max_dd * 100, 3),
            "elapsed_natural_days": (date.fromisoformat(T) - date.fromisoformat(sample["date"])).days,
            "elapsed_trading_sessions": len(path),
            "thirty_natural_days_matured": (date.fromisoformat(T) - date.fromisoformat(sample["date"])).days >= 30,
            "observed_close_below_original_invalid": current["close"] < float(sample["invalid_close_below"]),
            "source_urls": [raw_histories[code]["source"]], "recorded_at": stamp_cn,
            "missing": ["independent_daily_crosscheck", "historical_minute_OHLC", "auction", "fill", "legal_exit"],
        }
        if not any(x.get("id") == row["id"] for x in prior_obs):
            prior_obs.append(row)
        low_validations.append(row)

    proxy_reported = {
        "600900": {"change_pct": 0.85, "rvol20": 1.84, "clv": 0.75, "distance_ma20_pct": 3.14, "distance_low60_pct": 8.40},
        "000420": {"change_pct": 3.11, "rvol20": 2.05, "clv": 0.80, "distance_ma20_pct": 8.91, "distance_low60_pct": 17.40},
        "601288": {"change_pct": 1.51, "rvol20": 1.50, "clv": 0.875, "distance_ma20_pct": 6.22, "distance_low60_pct": 18.78},
        "002520": {"change_pct": 7.77, "rvol20": 4.36, "clv": 0.768, "distance_ma20_pct": 1.06, "distance_low60_pct": 19.61},
    }
    new_low = []
    for code, name in proxy_names.items():
        snapshot = derived_snapshot(code, name, raw_histories[code]["bars"], proxy_reported[code])
        new_low.append(snapshot)
        sid = "low-position-proxy-20261022-" + code
        if not any(x["id"] == sid for x in low["items"]):
            low["items"].append({
                "id": sid, "date": T, "recorded_at": stamp_cn, "code": code, "name": name,
                "sector": "低位形态代理待分类", "primary_model": "low_position_shape_proxy_v1",
                "day0_close": snapshot["close"], "invalid_close_below": snapshot["low"],
                "initial_invalidation_basis": "收盘跌破信号日低点；不后移",
                "original_snapshot_provenance": "contemporaneous_research_pool_proxy_recomputed_daily",
                "original_snapshot_verified": True, "eligible_for_model_statistics": True,
                "day0_rvol20": snapshot["rvol"]["20"], "day0_turnover_pct": None,
                "day0_amount_yi": None, "day0_clv": snapshot["clv"],
                "day0_range_position_pct": snapshot["range_position_pct"],
                "day0_moving_averages": snapshot["ma"], "snapshot": snapshot,
                "report_ids": [REPORT_IDS["low_position"]], "observations": [],
                "sources": [EVIDENCE_FILE, raw_histories[code]["source"]],
            })
    low["updated_at"] = stamp_cn

    prior_cohort = next(x for x in volume["items"] if x.get("id") == "volume-price-20261020-close-v1-cohort")
    prior_codes = [x["code"] for x in prior_cohort["samples"]]
    prior_map = {x["code"]: x for x in market["previous_partial_pool_validation"]}
    prior_validation = [prior_map[code] for code in prior_codes]
    prior_stats = {
        "count": len(prior_validation),
        "positive_close_count": sum(x["close_pct"] > 0 for x in prior_validation),
        "mean_close_pct": mean([x["close_pct"] for x in prior_validation]),
        "median_close_pct": median([x["close_pct"] for x in prior_validation]),
        "mean_mfe_pct": mean([x["mfe_pct"] for x in prior_validation]),
        "mean_mae_pct": mean([x["mae_pct"] for x in prior_validation]),
        "mae_le_minus5_count": sum(x["mae_pct"] <= -5 for x in prior_validation),
    }
    volume_validation_id = "volume-price-20261020-validation-20261022-v1"
    if not any(x.get("id") == volume_validation_id for x in volume["items"]):
        volume["items"].append({
            "id": volume_validation_id, "date": T, "recorded_at": stamp_cn, "task_id": "volume_price",
            "kind": "full_forward_price_validation", "origin_cohort_id": prior_cohort["id"],
            "origin_report_ids": prior_cohort["report_ids"], "report_ids": [REPORT_IDS["volume_price"]],
            "rule_version": "volume_price_close_v4", "full_validation_completed": True,
            "full_pool_summary": prior_stats, "full_pool_validations": prior_validation,
            "executable_sample_count": 0, "eligible_for_model_statistics": True,
        })
    cohort_id = "volume-price-20261022-close-v1-cohort"
    if not any(x.get("id") == cohort_id for x in volume["items"]):
        volume["items"].append({
            "id": cohort_id, "date": T, "task_id": "volume_price", "frozen_at": stamp_cn,
            "report_ids": [REPORT_IDS["volume_price"]], "rule_version": "volume_price_close_v4",
            "data_cutoff_at": T + "T15:00:00+08:00", "broad_pool_count": 120,
            "broad_pool_verified_count": 120, "deep_screen_count": 28,
            "deep_adjusted_history_verified_count": 28, "eligible_for_model_statistics": True,
            "provenance": "contemporaneous_full_market_research_reanalysis",
            "samples": market["deep_pool"],
        })

    learning_run = next(x for x in learning["runs"] if x["id"] == "forward-learning-2026-10-22")
    horizon_stats = {}
    for h in (1, 2, 5, 10):
        rows = [next((y for y in x.get("horizons", []) if y["h"] == h and y["status"] == "observed"), None)
                for x in learning_run["evaluations"]]
        rows = [x for x in rows if x]
        values = [x["close_pct"] for x in rows]
        horizon_stats[str(h)] = {
            "observed": len(rows), "pending": sum(any(y["h"] == h and y["status"] == "pending" for y in x.get("horizons", [])) for x in learning_run["evaluations"]),
            "mean_close_pct": mean(values), "median_close_pct": median(values),
            "positive": sum(x > 0 for x in values), "nonpositive": sum(x <= 0 for x in values),
            "min_close_pct": round(min(values), 3) if values else None,
            "max_close_pct": round(max(values), 3) if values else None,
            "min_mae_pct": round(min(x["mae_pct"] for x in rows), 3) if rows else None,
        }
    attributions = Counter(a for x in learning_run["evaluations"] for a in x.get("attribution", []))
    provider_errors = Counter(a for x in learning_run["evaluations"] for a in x.get("provider_errors", []))

    evidence = {
        "market_date": T, "recorded_at": stamp_cn, "retrieved_at_utc": stamp_utc,
        "market_evidence_file": "docs/research/market-review-2026-10-22-evidence.json",
        "market_evidence_scope": market["coverage"],
        "volume_price": {"previous_cohort_id": prior_cohort["id"], "previous_validation": prior_validation,
                         "previous_statistics": prior_stats, "new_deep_pool": market["deep_pool"]},
        "low_position": {"existing_count": len(low_codes), "existing_validations": low_validations,
                         "new_proxy_samples": new_low,
                         "raw_histories": {
                             code: {"source": value["source"],
                                    "bars": [bar for bar in value["bars"]
                                             if bar["date"] >= (low_codes[code]["date"] if code in low_codes else T)]}
                             for code, value in raw_histories.items()}},
        "dragon_tiger": {
            "institution_rows": [{"code": c, "name": n, "change_pct": p, "turnover_pct": t, "institution_net_buy_wan": v} for c, n, p, t, v in INSTITUTION],
            "stock_connect_rows": [{"code": c, "name": n, "stock_connect_net_buy_wan": v, "change_pct": p, "turnover_pct": t} for c, n, v, p, t in STOCK_CONNECT],
            "institution_appearance_count": 29, "institution_total_net_buy_yi": -4.90,
            "source": "https://finance.ifeng.com/c/8xREqNxTt6v",
        },
        "learning_review": {"snapshot_id": learning_run["id"], "sample_count": learning_run["sample_count"],
                            "status_counts": learning_run["status_counts"], "provider_count": learning_run["provider_count"],
                            "horizon_statistics": horizon_stats, "validation": learning_run["validation"],
                            "attribution_counts": dict(attributions), "provider_error_counts": dict(provider_errors),
                            "low_position_evaluation_count": len(learning_run.get("low_position_evaluations", []))},
        "limitations": ["no verified trade fills", "no Level-2/order-book data", "daily OHLC cannot prove intraday order", "dragon-tiger seat labels do not identify final holders"],
    }
    save(EVIDENCE_FILE, evidence)

    low_sorted = sorted(low_validations, key=lambda x: x["close_return_pct"])
    low_summary = {
        "count": len(low_validations), "mature_30d": sum(x["thirty_natural_days_matured"] for x in low_validations),
        "mean_close_pct": mean([x["close_return_pct"] for x in low_validations if x["eligible_for_model_statistics"]]),
        "median_close_pct": median([x["close_return_pct"] for x in low_validations if x["eligible_for_model_statistics"]]),
        "below_original_invalid": sum(x["observed_close_below_original_invalid"] for x in low_validations),
    }
    sources = [EVIDENCE_FILE, "docs/research/market-review-2026-10-22-evidence.json"]
    dragon_sources = ["https://finance.ifeng.com/c/8xREqNxTt6v", "https://data.eastmoney.com/stock/lhb.html", "https://www.sse.com.cn/disclosure/diclosure/public/"]

    volume_body = f"""一、范围和独立复算

T={T}，行情截止北京时间15:00。本报告复用同日market_review的全A有效5571只入口、120只广泛池和28只深筛原始快照，但量价阈值、上一批验证和结论独立计算，不把市场复盘正文当量价报告。28只均保存收盘、涨跌、换手、RVOL5/10/20、CLV、MA20距离和14点后价格变化；无9:25竞价、完整分钟OHLC、逐笔和盘口，因此只形成价格观察，不形成真实成交。

二、上一批28只完整验证

10月20日冻结的28只全部取得10月22日日线：收涨{prior_stats['positive_close_count']}/28，收盘均值{prior_stats['mean_close_pct']:+.3f}%、中位{prior_stats['median_close_pct']:+.3f}%，平均MFE {prior_stats['mean_mfe_pct']:+.3f}%、平均MAE {prior_stats['mean_mae_pct']:+.3f}%，MAE≤-5%的有{prior_stats['mae_le_minus5_count']}只。市场当日535涨、4998跌，批量负反馈与整体风险扩散一致；这不是按触发成交后的策略收益，交易样本N=0。

最弱收盘观察：{', '.join(x['code']+' '+x['name']+f" {x['close_pct']:+.2f}%" for x in sorted(prior_validation, key=lambda r:r['close_pct'])[:5])}。最强收盘观察：{', '.join(x['code']+' '+x['name']+f" {x['close_pct']:+.2f}%" for x in sorted(prior_validation, key=lambda r:r['close_pct'], reverse=True)[:5])}。盈利样本没有抵消28只整体中位数为负与尾部回撤。

三、当日28只深筛与量价分层

日发精机002520收6.10、+7.77%，RVOL20=4.36、CLV=0.768、距MA20约+1.09%，是“近均线放量但未封板”的主要观察；英思特301622收35.62、+8.04%，RVOL20=4.52、CLV=0.757、距MA20约+1.32%，但属于20%制度，隔夜尾部风险更高。智能自控002877虽放量，CLV仅0.597且14点后约-3.91%，价格推进失败。冰山冷热、海洋王、大业股份距MA20分别约+59.7%、+50.1%、+45.1%，高乖离封板不等于次日普通成交可执行。

研究池中普通主板代理30只封板、65只触板、35只触板未封，代理炸板率53.8%；指数和宽度同步恶化且放量下跌。H5继续作为影子假设：极弱日中，只有距MA20≤3%、RVOL20>3、CLV>0.70且未封板的逆势样本，在D日先出现市场宽度与板块同步修复，再完成回踩—重新站回关键位，才允许继续观察。今日只冻结假设，不改现行规则，不给胜率或涨停概率。

四、结论

量价证据支持“少数近均线逆势样本优于高乖离排队板”作为待检验方向，但上一批28只的负中位和深MAE说明退出环境恶劣。没有真实委托、成交、费用和合法退出证据，可执行净收益、胜率、盈亏比均N/A。"""

    low_rows = [[x["code"]+" "+x["name"], f"{x['close_return_pct']:+.2f}%", f"{x['path_mfe_pct']:+.2f}%/{x['path_mae_pct']:+.2f}%", str(x['elapsed_natural_days'])+"/"+str(x['elapsed_trading_sessions']), "是" if x["observed_close_below_original_invalid"] else "否"] for x in low_sorted]
    low_body = f"""一、样本范围与当日复核

T={T}。复用同日全A5571只入口和120只广泛池作为候选来源，并对既有35只低位台账逐只重取截至T的日线；35/35取得同日收盘和信号后完整日线。另将自动扫描提出的4只形态代理用同源日线重新计算，保存为前推影子样本，而不是把原eligible=false报告改名为完整研究。

既有35只中，符合统计资格者的相对原参考收盘均值{low_summary['mean_close_pct']:+.3f}%、中位{low_summary['median_close_pct']:+.3f}%；当前收盘低于原始失效位{low_summary['below_original_invalid']}只。30自然日成熟0只，不能计算30日胜率。完整逐股复核如下（MFE/MAE均从信号日之后算起，不是交易收益）：

{table(['代码/名称','当前相对参考','路径MFE/MAE','自然日/交易日','当前收破原失效'], low_rows)}

二、新增4只影子样本

长江电力600900：+0.85%，RVOL20约1.84、CLV0.75、距MA20约+3.14%、距60日低点约+8.40%；农业银行601288：+1.51%，RVOL20约1.50、CLV0.875、距MA20约+6.22%、距60日低点约+18.78%。两者防御属性较强，量价温和，不能由此推断短线主升。

吉林化纤000420：+3.11%，RVOL20约2.05、CLV0.80、距MA20约+8.91%、距60日低点约+17.40%；日发精机002520：+7.77%，RVOL20约4.36、CLV0.768、距MA20约+1.06%、距60日低点约+19.61%。后二者价格弹性更高，但日发尾盘回落且吉林仍须板块和后续量能确认。四只T+1/T+2/T+5/T+10/T+30在学习快照中均尚未成熟；不把0个成熟样本写成0%或100%胜率。

三、失败归因和下一假设

最早9月23日样本截至T仍只有29自然日，30日终点未到。当前较弱样本包括{', '.join(x['code']+' '+x['name']+f" {x['close_return_pct']:+.2f}%" for x in low_sorted[:5])}；保留失效和深回撤，不做幸存者筛选。影子假设L2：低位代理必须同时检查相对MA20、距60日低点、RVOL、CLV和次日承接；银行/公用事业低波动组与制造业高弹性组分层，不混算。未完成样本外验证，不修改现行选股规则或权重。"""

    dragon_body = f"""一、榜单范围和市场背景

T={T}。公开盘后汇总显示机构专用席位出现在29只个股，净买11只、净卖18只，合计净卖4.90亿元；深沪股通席位出现在17只。市场同期535涨、4998跌，属于风险扩散环境。席位名称只是公开交易通道，不等于具体账户身份、最终持仓或锁仓。

二、机构和股通结构

机构净买前三为云汉芯城+2630.64万元、百洋股份+2136.20万元、宇特光电+2008.92万元；净卖前三为华盛昌-10461.89万元、中新赛克-7154.55万元、万丰奥威-6973.85万元。净买并不等价于价格强：百洋股份当日-6.75%，宇特光电仅+1.58%；净卖也与高波动共振，显示退潮日席位信号分歧很大。

股通净买前三为崇达技术+11551.13万元、海洋王+2637.54万元、粤传媒+1831.61万元；其中崇达技术和粤传媒当日均接近跌停，形成资金与价格背离。股通净卖前三为华盛昌-7126.31万元、金健米业-5006.91万元、万丰奥威-2175.13万元。

三、与全市场深筛交叉

同日28只深筛中，哈空调机构净卖1212.90万元、襄阳轴承净卖1352.68万元、冰山冷热净卖1770.39万元、北新路桥净卖3742.74万元，尽管价格涨停或接近涨停，机构通道并未同向；海洋王股通净买2637.54万元，但距MA20约+50.1%、已5连板，属于高乖离高标。云汉芯城机构净买且上涨16.16%，但新股/高波动制度与普通主板不能混算。

四、结论与影子假设

龙虎榜当日更支持“价格强不代表机构净买、净买不保证价格强”的反例框架。候选需同时满足非高乖离、量价承接、席位不过度集中、板块同步和次日普通成交证据；本日没有对象同时通过。冻结D={D}空仓，不发布龙虎榜单股条件推荐。机构29只和股通17只只是一个交易日样本，不能形成稳定胜率或自动权重。"""

    combined_body = f"""T={T}盘后综合决策已完成。依赖报告均为同一已收盘交易日且有completed回执：{MARKET_ID}、{REPORT_IDS['volume_price']}、{REPORT_IDS['low_position']}、{REPORT_IDS['dragon_tiger']}。quant_research已取消，不是前置；自动扫描和eligible=false报告没有被用作替代。

市场事实：5571只有效股票中535涨、4998跌；上证-1.48%、深成指-2.96%、创业板-4.37%，普通非ST主板代理炸板率53.8%，风险扩散。量价方面，上一批28只收盘中位为{prior_stats['median_close_pct']:+.3f}%且{prior_stats['mae_le_minus5_count']}只MAE≤-5%；低位35只尚无30日成熟样本；龙虎榜机构席位合计净卖4.90亿元，强价与机构净买多处背离。

比较结果：日发精机虽近MA20且放量，但属于单一逆势样本，14点后回落且D日市场修复尚未发生；英思特为20%制度，隔夜尾部更高；海洋王、大业股份、冰山冷热高乖离；云汉芯城为高波动品种；崇达技术虽股通净买却收跌停。没有两只、也没有一只同时满足市场宽度修复、板块同步、低乖离、非排队成交和龙虎榜不过度分歧。

因此计划交易日D={D}的综合结论为现金/0只，不硬凑双标，不生成推荐记录，不存在买入、持仓或已实现收益。若D日盘中后来发生变化，也不能用盘后信息倒填本报告；新的盘中观察必须另立时间戳和证据。若当日真实买入，A股最早可于{EXIT}卖出，但本报告未授权任何买入，退出计划未激活。APP仅展示归档与统计，不内置大模型或自动训练权重。"""

    hs = horizon_stats
    learning_body = f"""一、新快照和样本成熟度

本轮读取最新快照forward-learning-2026-10-22，记录时间{learning_run['recorded_at']}。共有31条评估：observed 21、ineligible_retrospective 9、pending 1；行情提供方成功计数23。所有收益字段均以信号日未复权收盘为代理基准，不是买入成交，executed_trade=false、可执行净收益N/A。

T+1：{hs['1']['observed']}条，均值{hs['1']['mean_close_pct']:+.3f}%、中位{hs['1']['median_close_pct']:+.3f}%，正/非正{hs['1']['positive']}/{hs['1']['nonpositive']}；T+2：{hs['2']['observed']}条，均值{hs['2']['mean_close_pct']:+.3f}%、中位{hs['2']['median_close_pct']:+.3f}%，正/非正{hs['2']['positive']}/{hs['2']['nonpositive']}；T+5：{hs['5']['observed']}条，均值{hs['5']['mean_close_pct']:+.3f}%、中位{hs['5']['median_close_pct']:+.3f}%，正/非正{hs['5']['positive']}/{hs['5']['nonpositive']}；T+10仅{hs['10']['observed']}条，均值{hs['10']['mean_close_pct']:+.3f}%、中位{hs['10']['median_close_pct']:+.3f}%，不能视为稳定长期结论。

二、失败归因和风险

T+2收盘代理亏损超过2%的标记{attributions.get('T2_price_proxy_loss_over_2pct',0)}条，T+2路径MAE超过5%的标记{attributions.get('T2_intraday_adverse_excursion_over_5pct',0)}条；另有{attributions.get('positive_close_but_deep_interim_drawdown',0)}条“收盘为正但中途深回撤”。ConnectionError与HTTPError各{provider_errors.get('ConnectionError',0)}条，错误按样本留存，没有填零或删除失败。

T+2具特征成熟样本21条、仅6个独立日期；晋级门槛为至少36条和20个日期，promotion_authorized=false、strategy_active_rules_changed=false。不存在训练/留出样本充分的依据，也没有独立样本外留出集。低位形态新增4条，但T+1/T+2/T+5/T+10/T+30全部pending；龙虎榜未形成独立学习评估。因此不能把31条总记录、21条成熟代理或6个日期描述成已验证策略。

三、下一轮影子假设

H5继续：极弱市场中，近MA20、RVOL>3、CLV>0.70、未封板的逆势样本，只在次日宽度和板块先修复、再完成回踩重站时观察；与高乖离封板组分层。L2新增：低位四样本按防御低波动（600900/601288）和制造高弹性（000420/002520）分层，先等各自T+2和至少5个独立日期，不混算。龙虎榜R1：机构净买、股通净买和价格强弱必须三维交叉，资金—价格背离单列反例。

以上均为未经样本外验证的影子假设，不自动修改规则、阈值或权重。APP没有内置大模型，不会自行推理，也不会因使用次数增加而自然提高胜率。"""

    reports = [
        {"id": REPORT_IDS["volume_price"], "date": T, "market_date": T, "task_id": "volume_price", "track": "volume_price", "title": "量价完整研究｜10月22日28只深筛与上一批28只验证", "summary": f"复用全A5571只入口，独立复算120只广泛池/28只深筛；上一批28/28验证，收盘中位{prior_stats['median_close_pct']:+.3f}%，可执行成交N=0。", "body": volume_body, "sources": sources, "report_type": "full_daily_research", "eligible_for_integrated_research": True, "published_at": stamp_cn, "recorded_at": stamp_cn, "data_cutoff_at": stamp_cn, "run_id": "volume-price-20261022-manual-completion-v1", "evidence_file": EVIDENCE_FILE, "provenance": "contemporaneous_close_research", "broad_pool_count": 120, "deep_pool_count": 28, "previous_pool_verified_count": 28, "codes": [x["code"] for x in market["deep_pool"]]},
        {"id": REPORT_IDS["low_position"], "date": T, "market_date": T, "task_id": "low_position", "track": "low_position", "title": "低位启动30天研究｜10月22日35只全量复核与4只影子样本", "summary": f"既有35/35重取日线，30日成熟0；新增4只同日影子样本，均未到T+1，现行规则不变。", "body": low_body, "sources": sources + [raw_histories[code]["source"] for code in proxy_names], "report_type": "full_daily_research", "eligible_for_integrated_research": True, "published_at": stamp_cn, "recorded_at": stamp_cn, "data_cutoff_at": stamp_cn, "run_id": "low-position-20261022-manual-completion-v1", "evidence_file": EVIDENCE_FILE, "provenance": "contemporaneous_close_research", "existing_sample_count": 35, "new_sample_count": 4, "mature_30d_count": 0, "sample_ids": ["low-position-proxy-20261022-"+code for code in proxy_names]},
        {"id": REPORT_IDS["dragon_tiger"], "date": T, "market_date": T, "task_id": "dragon_tiger", "track": "dragon_tiger", "title": "龙虎榜完整研究｜10月22日机构净卖、资金价格背离与空仓结论", "summary": "机构席位29股合计净卖4.90亿元，股通现身17股；强价与净买多处背离，D日不发布单股条件候选。", "body": dragon_body, "sources": dragon_sources + [EVIDENCE_FILE], "report_type": "full_daily_research", "eligible_for_integrated_research": True, "published_at": stamp_cn, "recorded_at": stamp_cn, "data_cutoff_at": stamp_cn, "run_id": "dragon-tiger-20261022-manual-completion-v1", "evidence_file": EVIDENCE_FILE, "provenance": "contemporaneous_post_close_public_disclosure", "institution_appearance_count": 29, "stock_connect_appearance_count": 17, "candidate_count": 0},
        {"id": REPORT_IDS["combined_pair"], "date": T, "market_date": T, "task_id": "combined_pair", "track": "market_review", "title": "盘后综合决策｜10月22日四项齐备后空仓，不硬凑双标", "summary": "四份同T完整研究及回执齐备；宽度、量价尾部和龙虎榜分歧共同否决，10月23日综合候选0只。", "body": combined_body, "sources": sources + dragon_sources, "report_type": "full_trading_research", "eligible_for_integrated_research": True, "published_at": stamp_cn, "recorded_at": stamp_cn, "data_cutoff_at": stamp_cn, "run_id": "combined-pair-20261022-manual-completion-v1", "evidence_file": EVIDENCE_FILE, "provenance": "contemporaneous_pre_market_cash_decision", "dependency_report_ids": [MARKET_ID, REPORT_IDS["volume_price"], REPORT_IDS["low_position"], REPORT_IDS["dragon_tiger"]], "planned_entry_date": D, "earliest_legal_exit_date_if_bought": EXIT, "candidate_count": 0, "recommendation_ids": [], "decision": "cash_no_qualified_candidate"},
        {"id": REPORT_IDS["learning_review"], "date": T, "market_date": T, "task_id": "learning_review", "track": "market_review", "title": "每日学习复核｜10月22日31条代理评估、成熟度缺口与三项影子假设", "summary": "最新快照31条；T+2成熟特征样本21条/6日期，低于36条/20日期门槛；不晋级、不改规则或权重。", "body": learning_body, "sources": ["https://robin-stock-api-production.up.railway.app/api/learning", "backend/data/learning.json", EVIDENCE_FILE], "report_type": "learning_review", "eligible_for_integrated_research": False, "published_at": stamp_cn, "recorded_at": stamp_cn, "data_cutoff_at": stamp_cn, "run_id": "learning-review-20261022-scheduled-v1", "evidence_file": EVIDENCE_FILE, "provenance": "forward_snapshot_review", "learning_snapshot_id": learning_run["id"], "sample_count": 31, "mature_t2_featured": 21, "unique_cohort_dates": 6, "promotion_authorized": False, "strategy_active_rules_changed": False},
    ]
    research["items"].extend(reports)
    completed = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for report in reports:
        trigger = "scheduled" if report["task_id"] == "learning_review" else "manual_backfill"
        runs["items"].append({
            "id": report["run_id"] + "-completed", "run_id": report["run_id"], "task_id": report["task_id"],
            "date": T, "trigger": trigger, "started_at": stamp_utc, "recorded_at": completed, "completed_at": completed,
            "status": "completed", "summary": report["summary"], "report_ids": [report["id"]],
            "recommendation_ids": report.get("recommendation_ids", []), "analysis_completed": True,
            "eligible_for_integrated_research": report.get("eligible_for_integrated_research", False),
            "delivery_status": "repository_prepared_not_yet_verified", "sources": [EVIDENCE_FILE],
        })

    save("backend/data/research.json", research)
    save("backend/data/task_runs.json", runs)
    save("backend/data/volume_price_samples.json", volume)
    save("backend/data/low_position_samples.json", low)
    for report in reports:
        save("docs/research/" + report["id"] + ".json", report)
    manifest = {"market_date": T, "recorded_at": completed, "report_ids": [x["id"] for x in reports],
                "reused_report_ids": [MARKET_ID], "recommendation_ids": [], "candidate_count": 0,
                "delivery_status": "not_yet_CI_or_production_verified"}
    save("docs/research/completion-2026-10-22-publication-manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
