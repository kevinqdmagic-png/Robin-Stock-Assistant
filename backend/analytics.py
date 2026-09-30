"""Transparent daily studies, separate from live intraday signal validation."""
import math
from statistics import mean, median

MODEL_VERSION = "daily_breakout_v1"
HORIZONS = (1, 3, 5, 10, 20, 30)


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def clean_bars(bars):
    rows = []
    seen = set()
    for bar in sorted(bars, key=lambda b: b.get("date", "")):
        day = str(bar.get("date", ""))
        values = {k: number(bar.get(k)) for k in ("open", "high", "low", "close", "volume")}
        if (len(day) != 10 or day in seen or
                any(values[k] is None or values[k] <= 0 for k in ("open", "high", "low", "close")) or
                values["high"] < max(values["open"], values["close"]) or
                values["low"] > min(values["open"], values["close"])):
            raise ValueError("invalid_or_duplicate_daily_bar")
        seen.add(day)
        rows.append({**bar, **values, "date": day})
    return rows


def breakout_signals(bars, days=30):
    """At close i, use only the previous 20 candles and the completed candle i."""
    rows = clean_bars(bars)
    output = []
    for i in range(max(20, len(rows) - days), len(rows)):
        prior = rows[i - 20:i]
        avg_volume = mean(b["volume"] or 0 for b in prior)
        row = rows[i]
        relative_volume = row["volume"] / avg_volume if row["volume"] is not None and avg_volume > 0 else 0
        clv = (row["close"] - row["low"]) / (row["high"] - row["low"]) if row["high"] > row["low"] else 0.5
        if row["close"] > max(b["high"] for b in prior) and relative_volume >= 1.5 and clv >= 0.7:
            output.append({"index": i, "date": row["date"], "rvol20": round(relative_volume, 3),
                           "clv": round(clv, 3), "signal_close": row["close"]})
    return rows, output


def limit_fraction(code):
    if code.startswith(("300", "301", "688", "689")):
        return 0.20
    if code.startswith(("4", "8", "92")):
        return 0.30
    return 0.10


def blocked_open(rows, index, code, buy):
    row = rows[index]
    if not row["volume"] or row["volume"] <= 0:
        return True
    if index == 0:
        return False
    previous = rows[index - 1]["close"]
    rate = limit_fraction(code)
    # Conservative: skip an opening limit-up buy; defer an opening limit-down sell.
    boundary = round(previous * (1 + rate if buy else 1 - rate), 2)
    return row["open"] >= boundary - 0.005 if buy else row["open"] <= boundary + 0.005


def drawdown(path, entry_price):
    peak = entry_price
    worst = 0.0
    for row in path:
        # OHLC does not reveal intraday order. Use prior-day peak at today's low.
        worst = min(worst, row["low"] / peak - 1)
        peak = max(peak, row["high"])
    return round(worst * 100, 3)


def backtest_daily(bars, code, days=30, holding=3, cost_bps=20):
    days = max(5, min(60, int(days)))
    holding = max(1, min(20, int(holding)))
    cost_bps = max(0, min(200, float(cost_bps)))
    rows, signals = breakout_signals(bars, days)
    trades = []
    for signal in signals:
        entry_i = signal["index"] + 1
        record = {k: v for k, v in signal.items() if k != "index"}
        record["status"] = "pending_entry"
        if entry_i >= len(rows):
            trades.append(record)
            continue
        record["entry_date"] = rows[entry_i]["date"]
        if blocked_open(rows, entry_i, code, True):
            record["status"] = "entry_unavailable"
            trades.append(record)
            continue
        entry_price = rows[entry_i]["open"]
        record["entry_price"] = entry_price
        # holding=1 sells at the next trading-session open after the purchase session.
        exit_i = entry_i + holding
        delayed = 0
        while exit_i < len(rows) and blocked_open(rows, exit_i, code, False):
            exit_i += 1
            delayed += 1
        record["delayed_exit_sessions"] = delayed
        if exit_i >= len(rows):
            record["status"] = "pending_exit"
            trades.append(record)
            continue
        exit_price = rows[exit_i]["open"]
        # Exit at open; exclude exit day's later high/low from MFE/MAE.
        path = rows[entry_i:exit_i]
        high = max([entry_price, exit_price] + [b["high"] for b in path])
        low = min([entry_price, exit_price] + [b["low"] for b in path])
        record.update(status="completed", exit_date=rows[exit_i]["date"], exit_price=exit_price,
                      gross_pct=round((exit_price / entry_price - 1) * 100, 3),
                      net_pct=round((exit_price / entry_price - 1 - cost_bps / 10000) * 100, 3),
                      mfe_pct=round((high / entry_price - 1) * 100, 3),
                      mae_pct=round((low / entry_price - 1) * 100, 3),
                      drawdown_daily_pct=drawdown(path, entry_price))
        trades.append(record)
    completed = [t for t in trades if t["status"] == "completed"]
    values = [t["net_pct"] for t in completed]
    return {
        "ok": bool(rows), "model": MODEL_VERSION, "validation": "daily_proxy_only",
        "window_start": rows[-days]["date"] if len(rows) >= days else (rows[0]["date"] if rows else None),
        "window_end": rows[-1]["date"] if rows else None, "daily_bars": len(rows),
        "warmup_bars": 20, "holding_sessions": holding, "cost_bps": cost_bps,
        "signal_count": len(signals), "completed_count": len(completed),
        "pending_count": sum(t["status"].startswith("pending") for t in trades),
        "unavailable_count": sum(t["status"] == "entry_unavailable" for t in trades),
        "stats": {"win_rate_pct": round(sum(v > 0 for v in values) / len(values) * 100, 2) if values else None,
                  "mean_net_pct": round(mean(values), 3) if values else None,
                  "median_net_pct": round(median(values), 3) if values else None,
                  "worst_mae_pct": min((t["mae_pct"] for t in completed), default=None)},
        "trades": trades,
        "notes": [
            "单只股票最近30个有效交易日的日线代理研究，不等于全A回测或分时三模型验证。",
            "每个信号独立观察，样本可能重叠；汇总不是组合净值或组合最大回撤。",
            "信号收盘确认，下一交易日开盘研究买入，最早再下一交易日开盘退出；不使用信号日收盘成交。",
            "前复权研究价格；综合成本默认20基点为假设，未模拟最小佣金、交易股数和真实滑点。",
            "保守跳过涨停开盘买入，跌停开盘延后退出；不处理ST、IPO初期和特殊涨跌幅规则，运行前须核验股票状态。",
            "未成熟及无法成交样本保留。小样本不证明模型有效。",
        ],
    }


def recommendation_performance(record, bars):
    reference = number(record.get("reference_price"))
    if (reference is None or reference <= 0 or not record.get("published_at") or
            record.get("provenance") != "contemporaneous"):
        return {"status": "needs_evidence", "points": [],
                "note": "缺少推荐当时的时间或价格；保留记录，不补编收益。"}
    rows = clean_bars(bars)
    day = str(record.get("date") or "")
    anchor = next((i for i, b in enumerate(rows) if b["date"] == day), None)
    if anchor is None:
        return {"status": "anchor_missing", "points": []}
    future = rows[anchor + 1:]
    # Raw recommendation price cannot safely span corporate actions without factors.
    previous = rows[anchor]["close"]
    for row in future:
        change = number(row.get("pct"))
        if change is not None and abs((row["close"] / previous - 1) * 100 - change) > 1.0:
            return {"status": "corporate_action_review", "points": [],
                    "note": "发现除权/数据口径差异，需核对复权因子后计算。"}
        previous = row["close"]
    points = []
    for horizon in HORIZONS:
        if len(future) < horizon:
            points.append({"horizon": horizon, "status": "pending"})
            continue
        path = future[:horizon]
        points.append({"horizon": horizon, "status": "observed", "date": path[-1]["date"],
                       "close_pct": round((path[-1]["close"] / reference - 1) * 100, 3),
                       "mfe_pct": round((max(b["high"] for b in path) / reference - 1) * 100, 3),
                       "mae_pct": round((min(b["low"] for b in path) / reference - 1) * 100, 3)})
    return {"status": "price_observation", "points": points,
            "note": "推荐参考价后的价格观察；未验证买点触发或真实成交，非可执行策略收益。"}
