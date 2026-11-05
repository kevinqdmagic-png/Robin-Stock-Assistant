#!/usr/bin/env python3
"""Append seven substantive manual recovery reports, preserving strict gates.

No old report, freeze, recommendation or outcome is rewritten. This prepares
repository data; deployment and production readback remain separate operations.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import mean, median
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DAY, PLAN = "2026-11-05", "2026-11-06"
CN = ZoneInfo("Asia/Shanghai")
DOC = ROOT / "docs/research"
PREFIX = "recovery-20261105"
STARTED = "2026-11-05T16:32:00+00:00"
sys.path.insert(0, str(ROOT / "backend"))


def read(name):
    return json.loads((ROOT / name).read_text())


def write(name, value):
    (ROOT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fmt(value, digits=3):
    return "N/A" if value is None else f"{value:.{digits}f}"


def table(headers, rows):
    return "\n".join(["|"+"|".join(headers)+"|", "|"+"|".join(["---"]*len(headers))+"|"] +
                     ["|"+"|".join(str(x).replace("|", "/").replace("\n", " ") for x in row)+"|" for row in rows])


def cents(value):
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def upper_proxy(row):
    code = row["code"].split(".")[-1]
    if row.get("isST") not in ("0", 0):
        return None
    ratio = Decimal("1.20") if code.startswith(("30", "68")) else Decimal("1.10")
    return cents(Decimal(str(row["preclose"])) * ratio) if row.get("preclose") else None


def minutes_summary(item):
    if not item or not item.get("validation", {}).get("verified"):
        return {"verified": False, "reason": "missing_or_incomplete_session"}
    bars = item["bars"]
    at = {b["time"][11:16]: b for b in bars}
    vol = sum(b["volume"] for b in bars)
    amt = sum(b.get("amount", 0) for b in bars)
    close = bars[-1]["close"]
    tail = [b for b in bars if b["time"][11:16] > "14:30"]
    return {"verified": True, "count": 48, "last30_return_pct": (close / at["14:30"]["close"]-1)*100,
            "last60_return_pct": (close / at["14:00"]["close"]-1)*100,
            "vwap": amt/vol if vol else None,
            "close_vs_vwap_pct": (close/(amt/vol)-1)*100 if vol and amt else None,
            "last30_volume_share": sum(b["volume"] for b in tail)/vol if vol else None,
            "morning_low": min(b["low"] for b in bars[:24]),
            "afternoon_low": min(b["low"] for b in bars[24:]),
            "source": item["url"], "not_tick_sequence_or_fill": True}


def seat_summary(raw, main):
    trade_id = str(main["TRADE_ID"])
    parts = raw["seat_queries"][main["SECURITY_CODE"]]
    unique = {}
    buys, sells = [], []
    for side in ("BUY", "SELL"):
        for r in parts[side]["rows"]:
            if str(r.get("TRADE_ID")) != trade_id:
                continue
            key = (r.get("OPERATEDEPT_CODE"), r.get("OPERATEDEPT_NAME"), r.get("BUY"), r.get("SELL"))
            unique.setdefault(key, r)
            (buys if side == "BUY" else sells).append(r)
    institution = [r for r in unique.values() if r.get("OPERATEDEPT_NAME") == "机构专用"]
    connect = [r for r in unique.values() if "股通专用" in r.get("OPERATEDEPT_NAME", "")]
    top = max(buys, key=lambda r: float(r.get("BUY") or 0)) if buys else {}
    return {"trade_id": trade_id, "reason": main["EXPLANATION"],
            "interval": "multi_day" if "连续" in main["EXPLANATION"] else "daily",
            "listed_buy_yuan": main["BILLBOARD_BUY_AMT"], "listed_sell_yuan": main["BILLBOARD_SELL_AMT"],
            "listed_net_yuan": main["BILLBOARD_NET_AMT"],
            "institution_net_yuan": sum(float(r.get("NET") or 0) for r in institution),
            "connect_net_yuan": sum(float(r.get("NET") or 0) for r in connect),
            "top_buy_seat": top.get("OPERATEDEPT_NAME"),
            "top_buy_share": float(top.get("BUY") or 0)/main["BILLBOARD_BUY_AMT"] if main["BILLBOARD_BUY_AMT"] else None,
            "buy_rank_rows": buys, "sell_rank_rows": sells,
            "deduped_disclosed_rows": len(unique), "account_identity_known": False,
            "proprietary_vendor_success_probabilities_used": False}


def main():
    stamp = datetime.now(CN).isoformat(timespec="seconds")
    if datetime.now(CN) >= datetime.fromisoformat(PLAN+"T09:30:00+08:00"):
        raise ValueError("prospective_freeze_window_closed_do_not_publish_old_shadow")
    research = read("backend/data/research.json")
    runs = read("backend/data/task_runs.json")
    learning = read("backend/data/learning.json")
    if any(r["id"] == PREFIX+"-market_review-v1" for r in research["items"]):
        raise ValueError("immutable_recovery_already_published")
    raw = read("docs/research/recovery-20261105-bars.json")
    extra = read("docs/research/recovery-20261105-extra-minutes.json")
    minute = {**raw["five_minute"], **extra["five_minute"]}
    snap = read("backend/data/baostock/2026-11-05.json")
    previous = read("backend/data/baostock/2026-11-04.json")
    current = {r["code"].split(".")[-1]: r for r in snap["rows"]}
    prior = {r["code"].split(".")[-1]: r for r in previous["rows"]}
    vp = read("docs/research/volume-price-20261105-evidence.json")
    lhb = read("docs/research/recovery-20261105-lhb-raw.json")
    ann = read("docs/research/recovery-20261105-announcements.json")
    production = read("docs/research/recovery-20261105-production-before.json")
    indexes = read("docs/research/recovery-20261105-index-raw.json")

    spec = importlib.util.spec_from_file_location("vp_old", ROOT / "scripts/publish_volume_price_20261104.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    names = mod.names_from_archive()
    measures = {}
    daily_errors = {}
    for code, hist in raw["daily"].items():
        daybar = hist["bars"][-1]
        delta = max(abs(float(daybar[k])-float(current[code][k])) for k in ("open","high","low","close"))
        if delta > .011:
            daily_errors[code] = {"ohlc_max_difference": delta}
            continue
        r = mod.metrics({"code":code, "url":hist["url"], "bars":hist["bars"]}, current[code])
        r.update(name=names.get(code, code), turnover_pct=float(current[code]["turn"]),
                 amount_yuan=current[code]["amount"], is_st=current[code].get("isST") == "1",
                 crosschecked_all_ohlc=True, five_minute=minutes_summary(minute.get(code)))
        if "ST" in r["name"].upper() or r["is_st"]:
            r["tags"] = ["ST风险对照"]
        measures[code] = r

    # Denominators are stock symbols only; the original raw archive stays intact.
    index_errors = [r for r in snap["errors"] if r["code"].startswith("sz.399")]
    stock_errors = [r for r in snap["errors"] if not r["code"].startswith("sz.399")]
    assert len(current) == 5217 and len(stock_errors) == 7
    assert len(set(current)) == len(current)
    assert all(r["date"] == DAY and r.get("volume_unit") == "shares" and
               0 < r["low"] <= min(r["open"],r["close"]) <= max(r["open"],r["close"]) <= r["high"]
               for r in current.values())
    returns = [(r["close"]/float(r["preclose"])-1)*100 for r in current.values()]
    breadth = Counter("up" if x > .00001 else "down" if x < -.00001 else "flat" for x in returns)
    verified_minutes = {c:x for c,x in minute.items() if x.get("validation",{}).get("verified")}
    deep = [measures[r["code"]] for r in vp["deep_pool"] if r["code"] in measures]
    assert len(deep) == 28
    deep_minute_count = sum(r["five_minute"]["verified"] for r in deep)
    event_codes = ["002578","603381","301697","002529","002309","603212","002506","002487",
                   "002081","600641","600206","002409","002156","603657","003033","603955",
                   "000700","300709","000017","605339","000995","605188","002329","000603",
                   "600988","000426","002192","002240"]
    event_rows = []
    for c in event_codes:
        r=current[c]; upper=upper_proxy(r)
        state = "收盘触及计算上限" if upper and abs(r["close"]-upper)<.011 else "盘中触及计算上限后回落" if upper and abs(r["high"]-upper)<.011 else "未触及计算上限/待核制度"
        event_rows.append({"code":c,"name":names.get(c,c),"close":r["close"],"pct":float(r["pctChg"]),
                           "upper_calculated_not_official":upper,"observed_state":state,
                           "metric_available":c in measures,"five_minute_verified":c in verified_minutes})

    main_rows=lhb["main_list"]["rows"]
    assert all(r["TRADE_DATE"][:10] == DAY for r in main_rows)
    lhb_by_code=defaultdict(list)
    for r in main_rows:
        if r["SECURITY_CODE"].startswith(("200", "900")):
            continue  # Preserve raw B-share rows without mislabeling them A shares.
        lhb_by_code[r["SECURITY_CODE"]].append(r)
    seat_records={}
    for c, rows in lhb_by_code.items():
        # Prefer a day-only disclosure for the comparison; never add reasons together.
        rep=sorted(rows,key=lambda r:("连续" in r["EXPLANATION"],r["EXPLANATION"]))[0]
        seat_records[c]={"code":c,"name":rep["SECURITY_NAME_ABBR"],
                         "all_reasons":[r["EXPLANATION"] for r in rows], **seat_summary(lhb,rep)}

    groups={"光伏事件同伴":["002578","603381","301697","002529","002309","603212","002506"],
            "半导体事件同伴":["002081","600641","600206","002409","002156"],
            "机器人事件同伴":["603657","003033","603955","000700","300709"],
            "消费事件同伴":["000017","605339","000995","605188","002329"],
            "资源事件同伴":["000603","600988","000426","002192","002240"]}
    peer_rows=[]
    for name, codes in groups.items():
        values=[float(current[c]["pctChg"]) for c in codes]
        peer_rows.append({"group":name,"codes":codes,"n":len(codes),"median_pct":median(values),
                          "mean_pct":mean(values),"positive_count":sum(x>0 for x in values),
                          "scope":"selected_event_peers_not_point_in_time_sector_index"})

    # Only prospective, non-actionable observations; the formal recommendation archive is untouched.
    selected=[("combined_pair","002156","H1低位量能＋H2首次分歧修复", "45.25—45.70回踩后重新站稳；不追46.56以上。观察09:45—10:30和14:00—14:40。", "跌破44.35、开盘涨幅>3%、半导体同伴中位转负或无连续报价即放弃。", "前三季归母30.606亿元/扣非13.778亿元，归母增幅受非经常性损益影响；T日触板后回落、尾30分钟-0.330%，分歧尚未确认完成。"),
              ("combined_pair","002876","H1量能推进＋业绩催化对照", "30.02—30.32回踩后重新站稳；不追30.87以上。观察09:45—10:30和14:00—14:40。", "跌破29.42、开盘涨幅>3%、不能重新站上实时成交均价或源缺失即放弃。", "前三季营收+24.96%、归母+167.15%，但经营现金净额仅2355万元，远期外汇合约亏损和存货减值增加；T收盘低于全日VWAP。"),
              ("limitup_single","603699","H2低位换手首板后首次分歧", "D日09:35—10:30仅观察换手、第一次分歧和回封；D日涨停价必须另由当日报价核验，不能使用T日39.39作D涨停价。", "竞价不在0—5%、一字排队、两只预设同伴603278/002724不足+3%、高标跌停、60秒承接证据或当日上限无法核验即放弃。", "前三季归母仅+0.06%，Q3归母-20.14%、经营现金净额-58.91%；仅检验日线低位换手假设，不视为业绩加速或正式打板机会。")]
    shadow=[]
    for task,c,hyp,trigger,invalid,risk in selected:
        r=measures[c]
        assert r["crosschecked_all_ohlc"] and r["five_minute"]["verified"]
        assert ann[c]["ok"] and ann[c].get("has_more") is False
        shadow.append({"id":f"recovery-shadow-20261106-{task}-{c}-v1", "task_id":task,"code":c,"name":r["name"],
                       "research_date":DAY,"planned_observation_date":PLAN,"actual_frozen_at":stamp,
                       "reference_price":r["close"],"reference_as_of":DAY+"T15:00:00+08:00",
                       "reference_is_live_quote":False,"price_sources":["backend/data/baostock/2026-11-05.json",raw["daily"][c]["url"]],
                       "strategy_version":"manual_recovery_shadow_v1", "hypothesis":hyp,"trigger":trigger,"invalid":invalid,
                       "risk":risk,"main_board_regime":"ordinary_10pct_subject_to_D_security_status_verification",
                       "earliest_legal_exit_if_D_bought":"2026-11-09T09:30:00+08:00",
                       "exit_rule":"D+1实际交易日首个可核实可成交报价；无买盘/停牌保留敞口，不挑次日最高价。",
                       "next_validation_sessions":{"1":"2026-11-09","2":"2026-11-10","5":"2026-11-13","10":"2026-11-20"},
                       "forward_baseline":"D=2026-11-06收盘；仅D收盘后才冻结可比较基准，不将T11/05收盘代理当D买入价。",
                       "entry_fill":None,"executed_trade":False,"executable_net_return_pct":None,
                       "is_recommendation":False,"buy_order_allowed":False,"cohort":"research_shadow",
                       "not_reconstructed_20261105_intraday":True})
    shadow_doc={"schema_version":1,"created_at":stamp,"market_date":DAY,"planned_date":PLAN,
                "scope":"147只已交叉核验历史日线及公开资料初核的比较池；不声称全A最优或已校准排名。",
                "status":"prospective_research_observations_only","items":shadow,
                "controls":[{"code":"000159","reason":"同样放量低位、但前三季归母亏损1.160亿元和经营现金净流出2.680亿元；仅风险对照，不进入优选。"},
                            {"code":"002444","reason":"日线突破但归母与经营现金流下降、尾盘低于VWAP；未优于两只观察对象。"},
                            {"code":"002302","reason":"量价推进但前三季亏损4.545亿元、收入-25.98%；仅风险对照。"},
                            {"code":"002475","reason":"较低价格位置，但经营现金净流出64.344亿元、T收盘低于VWAP；保留为观察对照。"}],
                "H3_status":"仅有预选同伴组，缺全板块点时成员与板块K线；H3板块相对强度未验证，不编造完成。"}
    write("docs/research/recovery-20261105-shadow-manifest.json",shadow_doc)

    learn=next(r for r in learning["runs"] if r["date"]==DAY)
    unique={(r["code"],r["signal_date"]):r for r in learn["evaluations"] if r["status"]=="observed"}
    learning_stats=[]
    for h in (1,2,5,10):
        obs=[v for r in unique.values() for v in r["horizons"] if v["h"]==h and v["status"]=="observed"]
        learning_stats.append({"h":h,"n":len(obs),"mean_close_pct":mean(v["close_pct"] for v in obs),
                               "median_close_pct":median(v["close_pct"] for v in obs),
                               "worst_path_mae_pct":min(v["mae_pct"] for v in obs)})
    evidence={"schema_version":1,"market_date":DAY,"manual_started_at":STARTED,"actual_frozen_at":stamp,
              "coverage":{"stock_universe":5224,"stock_verified":5217,"stock_missing":7,"excluded_indices":len(index_errors),
                          "stock_coverage_ratio":5217/5224,"beijing_market_census_covered":False,
                          "daily_requested":len(raw["daily_requested"]),"daily_crosschecked":len(measures),
                          "minute_requested":len(minute),"minute_verified":len(verified_minutes),
                          "original_deep_count":28,"original_deep_minute_verified":deep_minute_count},
              "stock_errors":stock_errors,"daily_crosscheck_errors":daily_errors,"breadth":dict(breadth),
              "amount_sum_yuan":sum(r["amount"] for r in current.values()),"median_stock_return_pct":median(returns),
              "metrics":measures,"original_deep_codes":[r["code"] for r in deep],"event_reconciliation":event_rows,
              "selected_peer_groups":peer_rows,"lhb_representative_disclosures":seat_records,
              "prior_volume_pool_validation":vp["prior_20261104_deep_validation"],"learning_unique_statistics":learning_stats,
              "strict_full_delivery":False,"formal_candidates":[],"shadow_manifest":"docs/research/recovery-20261105-shadow-manifest.json",
              "remaining":["北交所逐股日线与完整证券状态未覆盖；7只沪深异常未判定停牌原因",
                           "没有全板块点时成员/板块OHLCV；同伴组合不是行业指数",
                           "交易所原始龙虎榜逐项核对仍受403/503限制；东财62只双侧明细是转载数据",
                           "五分钟K线不含竞价、60秒逐笔、排队或真实成交；不能验证打板v2全部条件",
                           "20个交易日全市场连续板高度与逐层晋级完整分母尚缺",
                           "11/05早尾盘原记录是no_signal；禁止以此次补做覆盖原冻结果"],
              "source_files":["docs/research/recovery-20261105-bars.json","docs/research/recovery-20261105-extra-minutes.json",
                              "docs/research/recovery-20261105-lhb-raw.json","docs/research/recovery-20261105-index-raw.json",
                              "docs/research/recovery-20261105-announcements.json","docs/research/recovery-20261105-learning-raw.json",
                              "docs/research/recovery-20261105-production-before.json"]}
    write("docs/research/recovery-20261105-evidence.json",evidence)

    standard=f"研究日T={DAY}；实际人工补做/冻结时间={stamp}。计划观察日D={PLAN}。本轮新材料不回填11/05的9:50、14:40信号，不更改既有报告、推荐和结果。沪深日线为历史收盘资料，北交所不在5224只分母中。正式交易许可为0；研究影子候选另列，不能当买入指令。若D买入，最早2026-11-09实际交易日可卖；没有交易及可成交证据时不计算净收益。\n\n"
    metrics_table=table(["代码/名称","收盘/涨跌%","换手%","RVOL5/10/20","20/60/120日位置%","CLV","尾30分钟%/距VWAP%"],
        [[r["code"]+" "+r["name"],fmt(r["close"],2)+" / "+fmt(r["pct"],2),fmt(r["turnover_pct"],2),
          "/".join(fmt(r[k],2) for k in ("rvol5","rvol10","rvol20")),
          "/".join(fmt(r[k]*100,1) if r[k] is not None else "N/A" for k in ("position20","position60","position120")),
          fmt(r["clv"]),fmt(r["five_minute"].get("last30_return_pct"))+" / "+fmt(r["five_minute"].get("close_vs_vwap_pct"))] for r in deep])
    event_table=table(["代码/名称","收盘/涨跌%","日线事件复核","历史指标/5分钟"],
        [[r["code"]+" "+r["name"],fmt(r["close"],2)+" / "+fmt(r["pct"],2),r["observed_state"],
          str(r["metric_available"])+" / "+str(r["five_minute_verified"])] for r in event_rows])
    prior_rows=vp["prior_20261104_deep_validation"]
    previous_table=table(["代码/名称","11/05开盘%","11/05收盘%","日线MFE%","日线MAE%"],
        [[r["code"]+" "+r["name"],fmt(r.get("open_pct")),fmt(r.get("close_pct")),fmt(r.get("mfe_pct")),fmt(r.get("mae_pct"))] for r in prior_rows])
    index_table=table(["指数","11/05收盘","相对11/04%"],
        [[c,fmt(float(x["bars"][-1]["close"]),3),fmt((float(x["bars"][-1]["close"])/float(x["bars"][-2]["close"])-1)*100)]
         for c,x in indexes.items() if x.get("bars")])
    peer_table=table(["预选事件组","N","上涨数","涨幅中位%","涨幅均值%"],
                     [[r["group"],r["n"],r["positive_count"],fmt(r["median_pct"]),fmt(r["mean_pct"])] for r in peer_rows])

    bodies={}
    bodies["market_review"]=standard+f"""## 补做结论和市场事实

同日5217只沪深股票OHLCV逐行核验通过，股票口径5217/5224={5217/5224:.3%}；7条异常保留，286个399指数从股票分母排除。相对各股档案preclose，上涨{breadth['up']}、下跌{breadth['down']}、平盘{breadth['flat']}；中位涨幅{median(returns):.3f}%。逐股成交额合计{evidence['amount_sum_yuan']/1e8:.2f}亿元，仅为本池沪深股票，不冒充含北交所的市场总量。指数用新浪原始日K独立复算：

{index_table}

结论是普涨修复与板内分歧并存。指数和大多数个股上涨，不能证明每只触板股票收盘稳定，也不推出次日交易必然获利。此前媒体总量口径作为历史来源保留，不与本池宽度拼接。

## 28只原事件深池逐股补证

{event_table}

**纠错：原复盘把002192融捷股份、002240盛新锂能记为首板封板。BaoStock与新浪日线显示收盘分别50.28/21.15，低于按preclose计算的52.03/21.93上限，属于触板后回落。** 原报告不改写，本报告追加纠正。计算上限不是D日权威报价；特殊制度/除权仍须另核。002529仅47根5分钟，即使汇总量额一致也不视为完整48根。301697上市历史不足121根，不计算完整120日位置。

## 同伴同步与上一批验证

{peer_table}

上述是事先列出的事件同伴组，含样本选择偏差，不能称全板块点时同步。上一轮11/04量价28只均取得11/05日线结果，均值/中位收盘观察{mean(r['close_pct'] for r in prior_rows):.3f}%/{median(r['close_pct'] for r in prior_rows):.3f}%；它不是上一轮市场复盘的正式推荐收益，不换组归功。完整路径在量价报告及evidence中。

## 下一日观察与反证

继续核验已冻结上行/震荡/下行情景，不改写原阈值：上行观察3700、宽度3500以上及成交约2.1万亿；若高标集体负反馈、指数与宽度背离则反证。两只新的综合影子观察已另按实际时间冻结，不能称11/05盘中曾推荐。

## 未达完整门槛

全A北交所普查、点时板块全成员、官方逐股涨跌停制度与全事件表未齐；因此是有实质数据和逐股分析的partial，未转full_daily_research。没有用“缺成交”作为禁止做研究的理由；有证据的部分已全部写入。
"""
    bodies["volume_price"]=standard+f"""## 本轮新增内容

在原120只量价广池之外补取事件与比较股，{len(raw['daily_requested'])}只请求中{len(measures)}只取得至少121根历史日线且当日四价与BaoStock差不超过0.011元；4只新股历史不足隔离。5分钟共{len(minute)}只去重请求、{len(verified_minutes)}只具备48个规范时点且汇总四价/量/额交叉核对通过，原量价28只深池全部28/28通过。量额容差上限1%，不把47根或价格点当成完整分钟OHLCV。

## 原28只深池完整量价/尾盘补证

{metrics_table}

RVOL5/10/20的分母均为T之前完成交易日均量；位置用含T的未复权20/60/120日区间，企业行为可能改变比较口径，不能当估值。CLV=(收盘-低)/(高-低)，尾30分钟为14:30五分钟收盘至15:00，不是14:40入场收益。VWAP为当日成交额/成交量。五分钟序列只能核验该粒度的价格和量，不能知道同一根内先破后拉的逐笔顺序。

## 上一批全28只验证（保留失败）

{previous_table}

收盘价格观察均值{mean(r['close_pct'] for r in prior_rows):.3f}%、中位{median(r['close_pct'] for r in prior_rows):.3f}%，日线MFE均值{mean(r['mfe_pct'] for r in prior_rows):.3f}%、MAE均值{mean(r['mae_pct'] for r in prior_rows):.3f}%。统一相对11/04收盘，不假设买入；最差、负收益和无法成交不能删掉。与本池市场中位{median(returns):.3f}%不同，且28只和5217只流动性不匹配，不能直接宣称超额收益。

## 发现、对选股与退出的影响

国际实业虽低位放量且尾盘回升，但三季报亏损和现金流恶化，转入风险对照。西部建设虽CLV高、尾盘推进，同样存在前三季亏损和收入下降，不以量价覆盖经营风险。三利谱、通富微电有量价与已披露业绩线索，但前者收盘低于VWAP、后者触板回落，故仅冻结条件观察；不能说承接已经确认。大连友谊/联合水务等放量下跌例子仍在原表，构成假转强反证。

未来固定检查：H1“低位量增+尾盘推进”是否优于高位量增；H2触板回落后的下一日是否真正修复；H3板块相对强度仍缺点时全成员，不填虚假分数。正式买点不放宽，价格观察、条件触发、可成交净收益分开。

## 仍缺

北交所、全板块点时同步和企业行为全量核验未齐；竞价和60秒回封未接入。原“28只分钟缺失”的阻塞已解除为28/28完整5分钟，但这些剩余项使完整综合前置仍不合格。
"""
    low_rows=[r for r in measures.values() if not r["is_st"] and "ST" not in r["name"].upper() and r["position120"] is not None and r["position120"]<=.35 and r["rvol20"]>=1.5 and r["pct"]>1 and r["clv"]>=.6]
    low_rows.sort(key=lambda r:(r["position120"],-r["rvol20"],r["code"]))
    low_table=table(["代码/名称","收盘","120日位置%","RVOL20","CLV","分钟尾盘%"],
                    [[r["code"]+" "+r["name"],fmt(r["close"],2),fmt(r["position120"]*100,1),fmt(r["rvol20"]),fmt(r["clv"]),fmt(r["five_minute"].get("last30_return_pct"))] for r in low_rows])
    bodies["low_position"]=standard+f"""## 独立低位筛查结果

5217只同日日线作发现底池，147只具备完整历史交叉核验。在这个明确的扩展子池，以120日价格位置≤35%、RVOL20≥1.5、涨幅>1%、CLV≥0.6且非ST为**形态研究假设**，得到{len(low_rows)}只结构样本。筛选结果不是主力身份、不是全A低位普查、不是每日推荐。

{low_table}

## 候选优劣与风险否决

- 通富微电：120日低位量能抬升，但触板后回落，尾30分钟小幅负值；需下一日回踩后再次推进，不预认“建仓完成”。前三季归母+255.68%与扣非+77.10%差别明显，金融资产公允价值贡献不能当主营持续增长。
- 国际实业：形态进入筛查，但前三季归母亏损1.1604亿元、经营现金净流出2.6805亿元，转风险对照，不入本次优选。
- 西部建设：形态进入，但前三季收入-25.98%、亏损4.5450亿元，不因低价或放量优先。
- 金刚光伏：20%涨停和大额合同不等于收入已兑现；原合同写明长期履约、资金投入与融资风险。只作事件研究，不以预估合同额当确定利润。
- 147只中ST名称与BaoStock状态任一提示ST都排除优选。未复权价格因除权/拆股可能形成假低位，位置不是基本面安全垫。

## 原低位样本长期跟踪

既有结构台账4只（000420、002520、600900、601288，原信号2026-10-22）已用未复权日线补至11/05，T+10全部成熟：平均收盘观察-1.623%、中位-1.919%、正收益1/4，保留全部失败。T+30应为2026-12-03，尚未成熟，不提前写30日结论。原始信号、初始条件及原失效位未更改，新结果在learning.json独立快照追加，不将本轮事后筛查倒填成10月22日信号。

本轮结构清单是11/06之前真实完成的历史研究资料；若做新的前推观察，以实际冻结时间和D日期单列。T+1短期与30交易日长期路径、假突破/反弹衰竭/放量下跌分组；同股多次重叠信号不能算多个独立成功。

## 状态

已交付独立低位报告和结构表、风险反例与老样本验证；北交所全市场历史、完整点时证券状态、所有原51只低位台账的30日成熟路径仍缺，因此保持partial。没有将原低位跟踪职责缩减为这4只结构实验；两者分母不同，51只老池未验完整部分仍列未完成。
"""
    lhb_table=table(["代码/名称","代表期间","榜买/榜卖/榜净 万元","机构净 万元","股通净 万元","买一集中%","原因（重复不相加）"],
        [[c+" "+r["name"],r["interval"],"/".join(fmt(r[k]/1e4,2) for k in ("listed_buy_yuan","listed_sell_yuan","listed_net_yuan")),
          fmt(r["institution_net_yuan"]/1e4,2),fmt(r["connect_net_yuan"]/1e4,2),fmt(r["top_buy_share"]*100,2) if r["top_buy_share"] is not None else "N/A","；".join(r["all_reasons"])]
         for c,r in sorted(seat_records.items(),key=lambda p:p[1]["listed_net_yuan"],reverse=True)])
    watch=["002565","002164","300709","002131","600261"]
    watch_lines=[]
    for c in watch:
        r=seat_records[c]
        watch_lines.append(f"- **{c} {r['name']}**：本次代表榜净{r['listed_net_yuan']/1e4:.2f}万元、机构匿名席位行净{r['institution_net_yuan']/1e4:.2f}万元。D仅在非一字、竞价不过热、09:45—10:30回踩站稳实时均价且同伴有承接时观察；高开>5%、跌破T低点、放量不涨或源缺失则放弃。")
    bodies["dragon_tiger"]=standard+f"""## 名单、双侧席位与口径

东财数据中心同日原始69条原因记录，含1条B股记录，剔除后为A股68条原因、去重62只，62/62均取得买卖双侧前五明细；沪深京披露均可能存在，但这不等于北交所全股票日线覆盖。每条保留原查询URL、TRADE_ID和公开营业部名称/金额。代表表优先日榜，连续多日榜单列，不把日榜和3日榜相加。阳光照明有两种原因且金额相同，不把净额翻倍。匿名“机构专用”不同金额行保留，不把同名机构当成同一账户；买卖两侧相同经济行去重。

{lhb_table}

这些是公开前五席位合计，**不是全市场资金净流入**。媒体宁波东力“6557万元”等与本次日榜1281.79万元口径冲突，保留原数字并追查期间，不能择大引用。供应商EXPLAIN中的“成功率”、RISE_PROBABILITY_3DAY等未经本体系验证的统计不用于判断。

## 5只独立龙虎榜观察（非正式综合组）

{chr(10).join(watch_lines)}

利欧股份虽榜净买居前，原三季报显示前三季亏损3.7186亿元、经营现金净流出9.2025亿元，且有减值公告；只作为“席位买入能否覆盖经营风险”的反例，不能升级正式推荐。阳光照明虽榜净买正，公开机构卖出与高位价格位置需要同时看，不因单一净买列为优选。顺灏机构净买约9729万元并不确认锁仓或机构账户身份。通富/三利谱不因未上榜而被视为资金未进场。

## 席位画像与上一批验证

本轮只确认公开营业部行及其买卖方向；湛江万豪世家等名称是营业部事实，市场俗称与真实交易人并非同一事实。单日两侧均有金额只支持“同日双向交易可见”，不能断定做T、对倒或持仓未变。持仓周期、首板/接力偏好与胜率需要连续完整样本，不据今日一榜新造画像。

11/04无完整已冻结龙虎榜观察组，因此不能用今日上涨股补作其T+1胜率。既存10/30正式与影子样本的日线结果已进入学习复核，组别不混算；未知竞价/成交保持未知。新5只从本次实际冻结之后开始验证，只记录未来路径，若一字无成交不能算买入成功。

## 剩余原始披露缺口

交易所原接口返回403/503，尚未逐项核对62只原始文件与券商字段。同花顺/新闻对照只能辅助，不能把东财转录当官方原文。完整证券制度、封单/竞价及次日可成交未核，因此partial，eligible_for_integrated_research=false。
"""

    shadow_table=table(["组别","代码/名称","T收盘参考","观察模型","主要反证"],
                        [[r["task_id"],r["code"]+" "+r["name"],r["reference_price"],r["hypothesis"],r["risk"]] for r in shadow])
    shadow_cards="\n\n".join(f"### {r['code']} {r['name']}\n\n- 参考价：{r['reference_price']}元，{r['reference_as_of']}历史收盘；冻结于{stamp}，D={PLAN}。\n- 观察条件：{r['trigger']}\n- 失效/放弃：{r['invalid']}\n- 风险：{r['risk']}\n- T+1：若D买入，最早2026-11-09开市后首个能证明可成交的报价退出；不能挑最高价，无成交则净收益空缺。" for r in shadow)
    bodies["combined_pair"]=standard+f"""## 独立综合裁决与研究轨

四份同T完整前置仍未满足：市场/量价/低位已补充实质量价，龙虎榜已有62只双侧转录，但全A覆盖、点时板块与官方原始披露仍不齐。**正式综合候选0，是证据不完整的blocked裁决，不是完整审核后宣称市场无机会。** 不改变正式风险门槛。

市场强也继续研究。本轮在147只已交叉核验历史池和公开资料比较池中，按低位量能、业绩与实际反证挑出两只**相对观察对象**，不是全A最优排名。先比较国际实业/西部建设的亏损与现金流风险、巨星科技利润下滑、立讯精密现金流及尾盘，再保留通富微电、三利谱。未核查所有147只全部公告，所以不能给经过完整风险审核的买入结论。固定新版本manual_recovery_shadow_v1，后续仅前推，不重解释旧结果。

{shadow_table}

{shadow_cards}

## 四模块证据如何参与

市场：同日普涨底色支持扩散，但高成交触板回落较多。量价：通富120日位置较低、成交放大，三利谱量增与三季报改善有共振；两者尾盘均不是无条件强承接。低位：通富符合结构筛查，三利谱不冒充120日底部，归为推进/平台观察。龙虎榜：不要求观察股必须上榜，也不将其他股机构买入套到这两只。

## 样本冻结和评价口径

三只影子记录独立保存在recovery-20261105-shadow-manifest.json，2只属于综合，1只属于独立打板；不写入正式recommendations.json。价格仅为T历史参考，不是D入场。D真实买卖条件和T+1最早退出独立；可观察报价→未来收盘与实际交易净收益分开。H3全板块证据缺失不强称成立。

原11/05的early/late记录均no_signal，仍只有旧动量对照；这次新样本用于11/06之后，绝非昨日两组盘中推荐补单。原样本不改，正式空仓事件、候选不足和对照均保留。
"""
    limit_comparison=table(["比较股","日线结构","放弃/保留原因"],[["603699 纽威股份","120日位置21.5%、RVOL20约2.81，主板换手首板代理","仅保留影子；Q3净利下降20.14%、现金流下降，正式条件未核"],
                         ["002131 利欧股份","低位放量首板、龙虎榜榜净买较大","前三季亏损与现金净流出，排除优选"],
                         ["600261 阳光照明","主板封板、高位置，换手较高","此前异动/风险提示，机构卖出，非低位安全例子"],
                         ["603212 赛伍技术","主板首板代理、RVOL20不足1","量能与经营风险未完成核查，未选"],
                         ["003033 征和工业","尾盘推进、已属进阶段","高位/连续加速风险，不按低位首板同组替代"]])
    bodies["limitup_single"]=standard+f"""## v2情绪、梯队和独立裁决

当前普涨修复，但多数分支存在触板回落。旧事件页称最高4板/21只连板，原130事件名单并非独立全量核对，且本次发现两处收盘封板分类错误，所以不把第三方总数直接做已核实层级分母。缺T前20实际交易日全市场最高连板、T-1逐层晋级名单及连续三日完整情绪矩阵；高度/空间板状态保持待核，不编晋级率。

正式limitup_single_v2候选0、blocked。独立影子1只，检验低位换手首板后首分歧假设；与综合两只分组、样本和退出规则分别保留。

## 至少三只真实备选比较

{limit_comparison}

## 唯一影子卡

{shadow_cards.split('### 603699',1)[1]}

规则仍为原v2：竞价0—5%、09:35—10:30、累计换手2—12%、第一次开板后60秒守住当日verified_upper×98%及成交均价；预设参考603278/002724均≥+3%且高标无跌停。不因新卡而更改阈值，参考同伴的题材一致性本轮没有完全验证，是不能晋级正式的额外缺口。五分钟K线不能验证60秒承接或排队；T上限39.39不能作D上限，D必须查权威报价/证券制度。缺一项即不认定触发，不能假定买入。

纽威前三季盈利仍为正但增长停滞、Q3明显下降，已作为卡片反证；这是一条待证伪的技术研究样本，不是忽略财报的买入推荐。D观察未触发、涨停排队未成交、次日跌停卖不掉都如实保留。前20—30个实际交易日只做首轮复核，不声称胜率优势。
"""

    learning_table=table(["成熟周期","去重证券日N","收盘观察均值%","中位%","路径最差MAE%"],
                        [[r["h"],r["n"],fmt(r["mean_close_pct"]),fmt(r["median_close_pct"]),fmt(r["worst_path_mae_pct"])] for r in learning_stats])
    intraday_rows=[]
    for slot in ("early_pair","late_pair"):
        p=production[f"/api/intraday-live?slot={slot}&limit=15"]
        r=next(x for x in p["items"] if x["date"]==DAY)
        intraday_rows.append([slot,r["started_at"],r["status"],r["scanned"],r["fresh_quotes"],r["daily_checked"],len(r["candidates"]),r["reason_code"]])
    bodies["learning_review"]=standard+f"""## 学习复核已执行

本次追加forward-learning-2026-11-05独立快照，使用23只相关证券的真实未复权历史日线，缺源0。31条原推荐记录中22条可观察、9条为回顾性样本而排除；按证券+信号日去重16个独立证券日，只有7个信号日期。跨策略重叠不相加当独立成交。

{learning_table}

这些是原信号日期收盘代理至未来收盘的价格观察，不是原推荐价成交或可执行净收益。样本未达到36个证券日、20个独立日期门槛，仍shadow_only，未自动调参、未修改实盘权重。长期负收益和尾部不利波动保留，不能从单日普涨推出模型有效。

## 低位结构与新样本

原低位结构实验4只、1个独立日期，T+10结果已全部成熟，T+30待12/03；不算30天验证完成。原量价28只上一日验证单独统计，不能与正式组重复算策略收益。本轮新的综合2+打板1属于11/06之前冻结的新影子版本，不混进已经结束的11/05结果。

## 11/05原盘中记录读回

{table(['时段','原始启动时间','原状态','扫描','新鲜报价','历史深查','候选','原因'],intraday_rows)}

原始记录存于Railway持久卷。每轮各只扫63只，日线源错误造成候选0；不是全A扫描，也不是“市场差所以取消”。当前扩容代码已在既有线上版本，但下一次真实9:50/14:40才能验证，不能盘后重跑伪装昨日。旧动量对照仍为对照，不改成新推荐。

## 修复优先级和验收

本轮实质补足了28只深池的五分钟证据、62只龙虎榜双侧席位、独立低位研究与前推影子清单；所有旧报告及回执只追加。六模块完整门槛继续保留，剩余北交所普查、点时板块、交易所原披露和打板秒级证据逐项列明，不能以排程completed冒充研究completed。

本学习报告的completed仅表示本次学习审计分析已做完，不满足综合交易前置，不意味着六项交易研究全部完成。仓库归档、CI、精确SHA部署和线上API读回仍须分别验收。
"""

    titles={"market_review":"市场复盘补做：5217只日线、原28事件复核及两处纠错",
            "volume_price":"量价补做：28只完整5分钟与上一批全样本验证",
            "low_position":"低位启动补做：结构清单、亏损反例与长期节点",
            "dragon_tiger":"龙虎榜补做：62只双侧席位、去重与5只观察",
            "combined_pair":"综合双标补做：正式受阻、11月6日两只影子冻结",
            "limitup_single":"独立打板补做：v2证据审查与一只影子冻结",
            "learning_review":"学习复核补做：31条原记录、16个独立证券日与失败归因"}
    report_ids=[]
    for task, body in bodies.items():
        rid=f"{PREFIX}-{task}-v1";run=f"{PREFIX}-{task}-manual-v1"
        is_learning=task=="learning_review"
        status="completed" if is_learning else "blocked" if task in ("combined_pair","limitup_single") else "partial"
        filename=f"docs/research/{PREFIX}-{task}.md"
        (ROOT/filename).write_text("# "+titles[task]+"\n\n"+body+"\n\n## 证据与来源\n\n- 汇总可复算证据：`docs/research/recovery-20261105-evidence.json`\n- 原始日线/5分钟、席位、公告和线上原记录见汇总中的source_files，逐项保留查询URL。\n- 官方公告全文："+"；".join("https://static.cninfo.com.cn/"+a["adjunctUrl"] for c in ["002156","002876","603699"] for a in ann[c]["rows"] if "三季度报告" in a["announcementTitle"])+"\n")
        sources=[filename,"docs/research/recovery-20261105-evidence.json",*evidence["source_files"]]
        own_shadow=[r for r in shadow if r["task_id"]==task]
        report={"id":rid,"date":DAY,"market_date":DAY,"task_id":task,
                "track":task if task in ("low_position","dragon_tiger","volume_price") else "market_review",
                "title":titles[task],"summary":("学习审计完成，31条/16个证券日/7个日期，策略不晋级。" if is_learning else "实际补做已归档；保留完整研究门槛，剩余源缺口逐项可见。"),
                "body":(ROOT/filename).read_text(),"sources":sources,"run_id":run,"status":status,
                "report_type":"learning_review" if is_learning else "manual_recovery_source_bounded_research",
                "analysis_completed":is_learning,"eligible_for_integrated_research":False,
                "execution_scope":"independent_learning_audit" if is_learning else "partial_research_universe",
                "published_at":stamp,"recorded_at":stamp,"data_cutoff_at":stamp,
                "market_data_cutoff_at":DAY+"T15:00:00+08:00","provenance":"actual_manual_recovery_not_original_scheduled_execution",
                "candidate_count":0,"recommendation_ids":[],"formal_decision_status":"blocked_incomplete_evidence",
                "research_shadow_candidates":own_shadow,"shadow_candidate_count":len(own_shadow),
                "evidence_file":"docs/research/recovery-20261105-evidence.json","planned_entry_date":PLAN,
                "earliest_legal_exit_date_if_bought":"2026-11-09","codes":[r["code"] for r in own_shadow],
                "full_a_market_scan":False,"trade_execution_verified":False,"strategy_active_rules_changed":False}
        research["items"].append(report)
        runs["items"].append({"id":run+"-"+status,"run_id":run,"task_id":task,"date":DAY,"trigger":"manual_backfill",
                              "started_at":STARTED,"completed_at":stamp,"recorded_at":stamp,"status":status,
                              "summary":titles[task]+"；"+report["summary"],"report_ids":[rid],"recommendation_ids":[],
                              "analysis_completed":is_learning,"eligible_for_integrated_research":False,"trade_executed":False,
                              "delivery_status":"repository_prepared_production_verification_pending","sources":sources[:2]})
        report_ids.append(rid)
    write("backend/data/research.json",research)
    write("backend/data/task_runs.json",runs)
    index="""# 11月5日定时任务人工补做交付\n\n"""+standard+"\n\n"+table(["模块","本轮实际成果","严格状态"],
        [["复盘","5217只日线、28事件补证、2处封板分类纠正","partial"],["量价","147只历史交叉核验、28/28深池完整5分钟、28只上一批验证","partial"],
         ["低位","独立结构清单、公告否决与4只原结构实验T+10","partial"],["龙虎榜","62只A股/68原因（原始69含B股）、62只双侧席位、5只观察","partial"],
         ["综合双标","正式0（证据受阻）、D11/06影子2","blocked"],["独立打板","正式0（证据受阻）、D11/06影子1","blocked"],
         ["学习复核","31条原记录、16个独立证券日/7日期、全部失败保留","completed（仅学习审计）"]])+"\n\n## 逐项报告\n\n"+"\n".join(f"- [{titles[t]}]({PREFIX}-{t}.md)" for t in bodies)+"\n\n## 原始资料与未完成范围\n\n"+"\n".join("- "+x for x in evidence["remaining"])+"\n\n汇总证据：`recovery-20261105-evidence.json`；影子冻结：`recovery-20261105-shadow-manifest.json`。六项严格完整交付仍不合格，不能关闭Issue #25。新增研究数据不要求重装APK；只有生产SHA与各报告ID读回后才称APP同步。\n"
    (DOC/(PREFIX+"-index.md")).write_text(index)
    print(json.dumps({"report_ids":report_ids,"shadow":[(r["task_id"],r["code"]) for r in shadow],
                      "frozen_at":stamp,"coverage":evidence["coverage"],"strict_full_delivery":False},ensure_ascii=False))


if __name__=="__main__":
    main()
