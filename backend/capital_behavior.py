"""Exploratory accumulation / breakout / distribution proxies from completed daily bars.

Not a participant-identity or position estimate; the model is uncalibrated and
has no proven predictive power. Use observations available at the signal close.
"""
from statistics import mean
from analytics import clean_bars, number

VERSION = "capital_behavior_daily_v1"


def _clv(bar):
    span = bar["high"] - bar["low"]
    return (bar["close"] - bar["low"]) / span if span > 0 else 0.5


def _range_pct(bar):
    return (bar["high"] - bar["low"]) / bar["close"]


def classify(bars):
    rows = clean_bars(bars)
    if len(rows) < 61:
        raise ValueError("at_least_61_completed_sessions_required")
    # End-point slices use no information after the evaluation date.
    now = rows[-1]
    before = rows[-21:-1]
    recent = rows[-10:]
    older = rows[-20:-10]
    sixty = rows[-61:]
    ma20 = mean(row["close"] for row in before)
    volume20 = mean(row["volume"] or 0 for row in before)
    if volume20 <= 0 or any(row["volume"] is None or row["volume"] <= 0 for row in sixty):
        raise ValueError("verified_volume_required")
    rvol = now["volume"] / volume20
    clv = _clv(now)
    highest20 = max(row["high"] for row in before)
    lowest20 = min(row["low"] for row in before)
    highest60 = max(row["high"] for row in sixty)
    lowest60 = min(row["low"] for row in sixty)
    location60 = (now["close"] - lowest60) / (highest60 - lowest60) if highest60 > lowest60 else 0.5
    ret20 = now["close"] / rows[-21]["close"] - 1
    ret60 = now["close"] / rows[-61]["close"] - 1
    recent10_ret = now["close"] / rows[-11]["close"] - 1
    width_ratio = mean(_range_pct(b) for b in recent) / max(1e-8, mean(_range_pct(b) for b in older))
    low_volume_ratio = mean(b["volume"] for b in rows[-5:]) / max(
        1, mean(b["volume"] for b in rows[-20:-5]))
    support_touches = sum(
        1 for b in before if b["low"] <= lowest20 * 1.03 and _clv(b) >= 0.55
    )
    heavy_weak = sum(
        1 for b in recent if b["volume"] >= volume20 * 1.35 and _clv(b) < 0.35
    )
    breakout = now["close"] > highest20 and rvol >= 1.4 and clv >= 0.65
    distribution = (
        (ret60 >= 0.22 and recent10_ret < -0.035 and heavy_weak >= 2)
        or (location60 >= 0.72 and now["close"] < ma20 * 0.96 and heavy_weak >= 2)
    )
    score = 0
    evidence = []
    if 0.12 <= location60 <= 0.72:
        score += 18
        evidence.append("位置：仍处于近60日价格区间的中低部")
    if abs(ret20) <= 0.10:
        score += 15
        evidence.append("整理：近20日涨跌幅相对有限")
    if width_ratio <= 0.82:
        score += 19
        evidence.append("波动：近10日平均日内波幅相对上一组10日收窄")
    elif width_ratio <= 0.95:
        score += 9
    if support_touches >= 2:
        score += 16
        evidence.append("承接代理：历史20日内多次低位收回（不能确认买方身份）")
    if low_volume_ratio <= 0.85:
        score += 12
        evidence.append("供给代理：最近5日平均成交量下降")
    if now["close"] >= highest20 * 0.965:
        score += 10
        evidence.append("价格：临近20日区间高点")
    if clv >= 0.7:
        score += 10
        evidence.append("当日：收盘位于日内区间上部")
    score = min(100, score)
    risks = []
    if heavy_weak >= 2:
        risks.append("近10日多次出现放量弱收盘，需排除派发与流动性变化")
    if distribution:
        stage = "distribution_risk"
        title = "疑似派发风险"
        risks.append("价格位置及放量弱收盘组合提示风险，不能确认账户减仓")
    elif breakout:
        stage = "breakout_observed"
        title = "已出现放量突破"
        evidence.append("突破：收盘高于前20日最高价、相对放量且收盘位置较强")
    elif score >= 68:
        stage = "late_accumulation_candidate"
        title = "疑似整理尾声（待验证）"
    elif score >= 48:
        stage = "accumulation_candidate"
        title = "疑似吸筹形态（待验证）"
    else:
        stage = "unconfirmed"
        title = "未形成可靠形态"
    if now["close"] < ma20:
        risks.append("收盘低于过去20日均价，须警惕弱势反弹")
    risks.append("日线供需代理不等于真实主力买卖；分数未经过样本外胜率校准")
    return {
        "ok": True, "version": VERSION, "as_of": now["date"], "daily_bars": len(rows),
        "stage": stage, "stage_title": title, "exploratory_score": score,
        "prediction_probability": None, "identity_verified": False,
        "evidence": evidence, "risks": risks,
        "observations": {
            "relative_volume20": round(rvol, 3),
            "close_location": round(clv, 3),
            "price_location60": round(location60, 3),
            "return20_pct": round(ret20 * 100, 2),
            "return60_pct": round(ret60 * 100, 2),
            "intraday_range_ratio10": round(width_ratio, 3),
            "last5_volume_ratio": round(low_volume_ratio, 3),
            "heavy_weak_sessions10": heavy_weak,
            "support_recoveries20": support_touches,
            "prior20_high": round(highest20, 3),
            "prior20_low": round(lowest20, 3),
        },
        "next_step": ("突破后等待回踩承接与次日可成交性验证" if breakout
                      else "观察后续是否放量突破20日高点，跌破近20日低点需重新评估"),
        "validation": "uncalibrated_hypothesis_not_a_trading_signal",
    }


def archive_context():
    """Read the existing repository knowledge; no automatic fitting is claimed."""
    from research_archive import load_document
    reports = load_document("research.json", "ROBIN_RESEARCH_FILE")["items"]
    counts = {}
    for row in reports:
        key = row.get("track")
        if key:
            counts[key] = counts.get(key, 0) + 1
    samples = {}
    for file, key in (
        ("low_position_samples.json", "low_position"),
        ("quant_research_samples.json", "quant_research"),
        ("volume_price_samples.json", "volume_price"),
    ):
        rows = load_document(file)["items"]
        samples[key] = {
            "total": len(rows),
            "eligible_for_model_statistics": sum(item.get("eligible_for_model_statistics") is True for item in rows),
        }
    return {
        "ok": True, "archive_report_counts": counts, "sample_counts": samples,
        "research_history_available": True,
        "automatically_trained_on_archive": False,
        "capital_model_uses_historical_results_to_fit": False,
        "description": "历史研究资料已经保存，但尚未用可信样本结果自动拟合模型或完成样本外验证。",
        "capital_model_version": VERSION,
    }
