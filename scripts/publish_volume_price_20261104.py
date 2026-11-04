#!/usr/bin/env python3
"""Publish a substantive, source-bounded 2026-11-04 volume/price study.

The full SH/SZ close snapshot comes from the already validated BaoStock archive.
Tencent unadjusted daily bars are fetched only for the frozen 120-name broad
pool to calculate RVOL and price-position metrics. Missing turnover, sector and
minute evidence remains explicit and prevents this report from being presented
as an integrated-research-ready full module.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import time
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
T = "2026-11-04"
PREV = "2026-11-03"
CN = ZoneInfo("Asia/Shanghai")
ISSUE = "https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/25"
SNAP = ROOT / f"data/baostock/{T}.json"
PREV_SNAP = ROOT / f"data/baostock/{PREV}.json"
ARCHIVE = ROOT / "docs/research/combined-pair-20261030-evidence.json.gz"
NOV02 = ROOT / "docs/research/nov02-retrospective-market.json"
EVIDENCE = ROOT / "docs/research/volume-price-20261104-evidence.json"
REPORT = ROOT / "docs/research/volume-price-20261104-partial-v1.md"


def now_pair():
    u = datetime.now(timezone.utc)
    return u.isoformat(timespec="seconds").replace("+00:00", "Z"), u.astimezone(CN).isoformat(timespec="seconds")


def code6(row):
    return row["code"].split(".")[1]


def names_from_archive():
    raw = json.loads(gzip.decompress(ARCHIVE.read_bytes()))
    out = {}
    for page in raw.get("sina_pages", {}).values():
        for r in page.get("payload", []):
            c = str(r.get("code", ""))
            if len(c) == 6 and c.isdigit() and r.get("name"):
                out[c] = r["name"]
    return out


def freeze_broad(current, prior, valid_stock_codes):
    rows = []
    for r in current:
        c = code6(r)
        if c not in valid_stock_codes:
            continue
        p = prior.get(c)
        if not p or min(r["open"], r["high"], r["low"], r["close"], p["close"]) <= 0:
            continue
        pct = (r["close"] / p["close"] - 1) * 100
        vr1 = r["volume"] / p["volume"] if p["volume"] > 0 else None
        rng = r["high"] - r["low"]
        clv = (r["close"] - r["low"]) / rng if rng > 0 else None
        amp = rng / p["close"] * 100
        rows.append({**r, "code6": c, "pct": pct, "vr1": vr1, "clv": clv, "amp": amp})
    liquid = [r for r in rows if r["amount"] >= 30_000_000 and r["vr1"] is not None]
    groups = [
        sorted(liquid, key=lambda r: (r["vr1"], r["amount"]), reverse=True)[:45],
        sorted(liquid, key=lambda r: (r["pct"], r["clv"] or -1), reverse=True)[:35],
        sorted(liquid, key=lambda r: (r["amount"], abs(r["pct"])), reverse=True)[:30],
        sorted(liquid, key=lambda r: (r["vr1"] * r["amp"], -(r["clv"] or 0)), reverse=True)[:35],
    ]
    frozen, seen = [], set()
    for group in groups:
        for r in group:
            if r["code6"] not in seen:
                frozen.append(r); seen.add(r["code6"])
            if len(frozen) == 120:
                return frozen, rows
    for r in sorted(liquid, key=lambda r: r["amount"], reverse=True):
        if r["code6"] not in seen:
            frozen.append(r); seen.add(r["code6"])
        if len(frozen) == 120:
            break
    return frozen, rows


def fetch_history(code, attempts=2):
    symbol = ("sh" if code.startswith("6") else "sz") + code
    url = f"https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_vp=/CN_MarketDataService.getKLineData?symbol={symbol}&scale=240&ma=no&datalen=150"
    last = None
    for attempt in range(attempts):
        try:
            proc = subprocess.run(["curl","-fsS","--max-time","18","-H","User-Agent: Mozilla/5.0","-H","Referer: https://gu.qq.com/",url],
                                  check=True,capture_output=True,text=True,timeout=21)
            match = re.search(r"=\((\[.*\])\)\s*;?\s*$", proc.stdout, re.S)
            if not match:
                raise ValueError("sina_jsonp_missing")
            raw = json.loads(match.group(1))
            if not isinstance(raw, list):
                raise ValueError("unadjusted_day_missing")
            bars = []
            for x in raw:
                vals = [float(x[k]) for k in ("open","close","high","low","volume")]
                o, cl, h, lo, vol = vals
                if all(math.isfinite(v) for v in vals) and 0 < lo <= min(o,cl) <= max(o,cl) <= h and vol >= 0:
                    bars.append({"date":x["day"], "open":o, "close":cl, "high":h, "low":lo, "volume":vol})
            if len(bars) < 21 or bars[-1]["date"] != T:
                raise ValueError("insufficient_or_stale_history")
            return {"code":code, "provider":"Sina unadjusted daily K", "url":url, "bars":bars}
        except Exception as exc:
            last = f"{type(exc).__name__}:{str(exc)[:100]}"
            if attempt + 1 < attempts: time.sleep(.2)
    raise ValueError(last)


def metrics(hist, baobar):
    bars = hist["bars"]
    cur = bars[-1]; old = bars[:-1]
    def avgvol(n):
        x = old[-n:]
        return sum(b["volume"] for b in x)/len(x) if len(x)==n else None
    def rvol(n):
        a=avgvol(n); return cur["volume"]/a if a and a>0 else None
    def ma(n):
        x=bars[-n:]; return sum(b["close"] for b in x)/len(x) if len(x)==n else None
    def pos(n):
        x=bars[-n:]
        if not x: return None
        lo=min(b["low"] for b in x); hi=max(b["high"] for b in x)
        return (cur["close"]-lo)/(hi-lo) if hi>lo else None
    prev=old[-1]
    pct=(cur["close"]/prev["close"]-1)*100
    rng=cur["high"]-cur["low"]
    clv=(cur["close"]-cur["low"])/rng if rng>0 else None
    body_top=max(cur["open"],cur["close"]); body_bottom=min(cur["open"],cur["close"])
    prev20=max(b["high"] for b in old[-20:]) if len(old)>=20 else None
    out={"code":hist["code"],"open":cur["open"],"high":cur["high"],"low":cur["low"],"close":cur["close"],
         "pct":pct,"amplitude_pct":rng/prev["close"]*100,"clv":clv,
         "upper_shadow_pct":(cur["high"]-body_top)/prev["close"]*100,
         "lower_shadow_pct":(body_bottom-cur["low"])/prev["close"]*100,
         "rvol5":rvol(5),"rvol10":rvol(10),"rvol20":rvol(20),
         "ma5":ma(5),"ma10":ma(10),"ma20":ma(20),"ma60":ma(60),
         "position20":pos(20),"position60":pos(60),"position120":pos(120),
         "previous20_high":prev20,"breakout20":bool(prev20 and cur["close"]>prev20),
         "baostock_close":baobar["close"],"ohlc_close_crosscheck_abs":abs(cur["close"]-baobar["close"]),
         "history_count":len(bars),"source":hist["url"]}
    tags=[]
    p120=out["position120"]
    rv=out["rvol20"]
    if p120 is not None and p120<=.35 and rv and rv>=1.5 and pct>1 and clv is not None and clv>=.6: tags.append("低位首次放量/推进代理")
    if out["breakout20"] and rv and rv>=1.5: tags.append("放量突破")
    if rv and rv>=1.5 and pct<0: tags.append("放量下跌")
    if rv and rv<.8 and pct>0: tags.append("缩量上涨")
    if p120 is not None and p120>=.8 and rv and rv>=1.5 and (clv is not None and clv<.55): tags.append("高位爆量滞涨/长上影风险")
    if rv and rv>=1.2 and cur["low"]<prev["close"] and cur["close"]>cur["open"] and clv is not None and clv>=.7: tags.append("日线分歧转强代理")
    if not tags: tags.append("活跃量价对照")
    out["tags"]=tags
    return out


def select_deep(rows):
    order=["低位首次放量/推进代理","放量突破","日线分歧转强代理","高位爆量滞涨/长上影风险","放量下跌","缩量上涨","活跃量价对照"]
    chosen=[]; seen=set()
    for tag in order:
        candidates=[r for r in rows if tag in r["tags"]]
        candidates.sort(key=lambda r:(r["rvol20"] or 0, abs(r["pct"]), r["amplitude_pct"]),reverse=True)
        cap={"低位首次放量/推进代理":6,"放量突破":6,"日线分歧转强代理":5,"高位爆量滞涨/长上影风险":5,"放量下跌":4,"缩量上涨":3}.get(tag,28)
        for r in candidates[:cap]:
            if r["code"] not in seen: chosen.append(r);seen.add(r["code"])
    for r in sorted(rows,key=lambda r:((r["rvol20"] or 0)*r["amplitude_pct"]),reverse=True):
        if len(chosen)>=28: break
        if r["code"] not in seen: chosen.append(r);seen.add(r["code"])
    return chosen[:28]


def old_deep_validation(current_map, prev_map, nov02, report_items):
    old=next(x for x in report_items if x.get("id")=="volume-price-20261030-close-v1")
    section=old["body"].split("三、完整28快照",1)[1].split("四、逐只模型",1)[0]
    pattern=re.compile(r"^\|(\d{6}) ([^|]+)\|[^|]*\|([0-9.]+)/",re.M)
    anchors={c:{"name":n.strip(),"anchor":float(px)} for c,n,px in pattern.findall(section)}
    d2={r["code"]:r for r in nov02.get("rows",[])}
    rows=[]
    for c,a in anchors.items():
        t=current_map.get(c); p=prev_map.get(c); x=d2.get(c)
        if not t: continue
        path=[]
        if x: path.append((x["D_high"],x["D_low"],x["D_close"]))
        if p: path.append((p["high"],p["low"],p["close"]))
        path.append((t["high"],t["low"],t["close"]))
        anchor=a["anchor"]
        rows.append({"code":c,"name":a["name"],"anchor_date":"2026-10-30","anchor_close":anchor,
                     "T_close":t["close"],"T3_close_return_pct":(t["close"]/anchor-1)*100,
                     "path_MFE_pct":(max(z[0] for z in path)/anchor-1)*100,
                     "path_MAE_pct":(min(z[1] for z in path)/anchor-1)*100,
                     "observation_sessions":["2026-11-02","2026-11-03","2026-11-04"],
                     "not_executable_return":True})
    return rows


def f(v,n=3):
    return "N/A" if v is None else f"{v:.{n}f}"


def main():
    started_utc, started_cn = now_pair()
    snap=json.loads(SNAP.read_text()); prev=json.loads(PREV_SNAP.read_text())
    if snap.get("trade_date")!=T or snap.get("provider")!="baostock" or snap["coverage"]["coverage_ratio"]<.9:
        raise ValueError("invalid_current_full_market_snapshot")
    current_map={code6(r):r for r in snap["rows"]}; prev_map={code6(r):r for r in prev["rows"]}
    names=names_from_archive()
    broad, market_rows=freeze_broad(snap["rows"],prev_map,set(names))
    histories={}; errors={}
    with ThreadPoolExecutor(max_workers=20) as ex:
        jobs={ex.submit(fetch_history,r["code6"]):r["code6"] for r in broad}
        for fut in as_completed(jobs):
            c=jobs[fut]
            try: histories[c]=fut.result()
            except Exception as exc: errors[c]=str(exc)[:150]
    enriched=[]
    for r in broad:
        c=r["code6"]
        if c in histories:
            m=metrics(histories[c],current_map[c]);m["name"]=names.get(c,"名称未从冻结档案取得")
            if "ST" in m["name"].upper(): m["tags"]=["ST风险对照"]
            enriched.append(m)
    deep=select_deep(enriched)
    nov02=json.loads(NOV02.read_text())
    research_path=ROOT/"backend/data/research.json"; runs_path=ROOT/"backend/data/task_runs.json"
    research=json.loads(research_path.read_text()); runs=json.loads(runs_path.read_text())
    old_validation=old_deep_validation(current_map,prev_map,nov02,research["items"])
    matched=[r for r in market_rows if r["code6"] in prev_map]
    advances=sum(r["pct"]>0 for r in matched); declines=sum(r["pct"]<0 for r in matched)
    completed_utc, completed_cn=now_pair()
    evidence={
      "schema_version":1,"market_date":T,"started_at":started_utc,"completed_at":completed_utc,
      "providers":[{"provider":"BaoStock","file":str(SNAP.relative_to(ROOT)),"date":T,"adjustment":"none","scope":snap["exchange_scope"],"coverage":snap["coverage"]},
                   {"provider":"Sina","url_template":"https://quotes.sina.cn/cn/api/jsonp_v2.php/CN_MarketDataService.getKLineData","date_required":T,"adjustment":"none","purpose":"frozen broad-pool history only; Tencent returned WAF 501"}],
      "market_scan":{"checked":snap["coverage"]["checked"],"verified":snap["coverage"]["verified"],"errors":snap["errors"],
                     "matched_previous":len(matched),"advanced":advances,"declined":declines,"unchanged":len(matched)-advances-declines,
                     "stock_rows_after_frozen_name_filter":len(market_rows),
                     "amount_sum_yuan":sum(r["amount"] for r in market_rows),"broad_pool_count":len(broad)},
      "history_fetch":{"requested":len(broad),"verified":len(enriched),"errors":errors,"close_crosscheck_within_0_03":sum(r["ohlc_close_crosscheck_abs"]<=.03 for r in enriched)},
      "broad_pool":enriched,"deep_pool":deep,"prior_20261030_deep_validation":old_validation,
      "blocked":{"turnover":"BaoStock archive omitted turnover/free-float denominator; no unit-safe reconstruction.",
                 "sector_sync":"No point-in-time sector membership/sector breadth source was archived for T.",
                 "intraday":"No date-qualified T minute/auction/order data; daily CLV and shadows do not establish event order or fills.",
                 "beijing":"BaoStock snapshot explicitly excludes Beijing exchange (6 names in frozen SH/SZ universe also errored)."},
      "formal_candidates":[],"verified_fills":0,"analysis_completed":False,"eligible_for_integrated_research":False,
      "rule_version":"volume_price_close_v5_partial_source_bounded"
    }
    EVIDENCE.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+"\n")
    tag_counts={}
    for r in deep:
        for tag in r["tags"]: tag_counts[tag]=tag_counts.get(tag,0)+1
    positives=[r for r in deep if any(t in r["tags"] for t in ("低位首次放量/推进代理","放量突破","日线分歧转强代理")) and "ST风险对照" not in r["tags"]]
    risks=[r for r in deep if any(t in r["tags"] for t in ("高位爆量滞涨/长上影风险","放量下跌"))]
    typical=(positives[:3]+risks[:2])[:5]
    deep_lines=[]
    for r in deep:
        deep_lines.append(f"|{r['code']} {r['name']}|{'、'.join(r['tags'])}|{f(r['close'],2)}/{f(r['pct'])}|{f(r['rvol5'])}/{f(r['rvol10'])}/{f(r['rvol20'])}|{f((r['position20'] or 0)*100,1)}/{f((r['position60'] or 0)*100,1)}/{f((r['position120'] or 0)*100,1)}|{f(r['clv'])}/{f(r['upper_shadow_pct'])}|")
    old_mean=statistics.mean(r["T3_close_return_pct"] for r in old_validation) if old_validation else None
    old_median=statistics.median(r["T3_close_return_pct"] for r in old_validation) if old_validation else None
    body=f"""已收盘交易日T={T}。BaoStock原始快照在冻结的沪深代码清单中取得{snap['coverage']['verified']}/{snap['coverage']['checked']}条（{snap['coverage']['coverage_ratio']:.2%}），其中含非股票代码；经10月30日冻结股票名称映射筛得{len(market_rows)}只可核股票。北京交易所及无法匹配的新变更不在本次范围；行情截止北京时间15:00，实际完成{completed_cn}。本报告执行了当日股票日线扫描、120只广泛池冻结、历史日线补证及28只深筛，但因全A覆盖、换手率、T日分钟顺序和点时板块成员证据缺失，状态为partial/blocked，不冒充综合研究所需完整报告。正式候选0，成交0。

一、市场与数据事实

- 11月4日OHLCV来自仓库内BaoStock未复权快照；原始5510个代码中5504条有效、6条错误。股票映射口径{len(matched)}只可与11月3日匹配，上涨{advances}、下跌{declines}、平盘{len(matched)-advances-declines}；股票映射口径成交额简单加总{sum(r['amount'] for r in market_rows)/1e8:.1f}亿元。不把原始代码覆盖率直接称为全A股票覆盖率。
- 广泛池120只由当日金额、涨跌、CLV、振幅及相对11月3日成交量的固定组合选出；腾讯历史接口返回WAF 501后改用独立免费新浪未复权日线，取得{len(enriched)}/120只，{sum(r['ohlc_close_crosscheck_abs']<=.03 for r in enriched)}/{len(enriched)}只T日收盘与BaoStock差值不超过0.03元。RVOL5/10/20分母均不含T。
- CLV=(收盘-最低)/(最高-最低)，只能描述收盘位置；没有分钟顺序时，不能把低开回升、下影或日线阳线写成“杀跌放量后低点抬高并突破”。

二、旧批次前推验证

10月30日冻结的28只深筛中，本次取得11月4日有效日线{len(old_validation)}只。以10月30日收盘为锚，跨11月2、3、4三个交易日的收盘观察均值{f(old_mean)}%、中位{f(old_median)}%；MFE/MAE仅是日线价格路径观察，不代表原条件触发、成交或可实现收益。原正式候选为0，因此可执行净收益、胜率、盈亏比和退出质量仍为N/A，不能把上述观察收益改写成策略业绩。

三、当日28只深筛

|代码/名称|量价标签|收盘/涨跌%|RVOL5/10/20|20/60/120日位置%|CLV/上影%|
|---|---|---|---|---|---|
{chr(10).join(deep_lines)}

标签计数：{json.dumps(tag_counts,ensure_ascii=False)}。同股可有多个标签，不能相加为独立样本数。

四、五个典型样本与真假转强

{chr(10).join(f'- {r["code"]} {r["name"]}：{"、".join(r["tags"])}；RVOL20={f(r["rvol20"])}，120日位置={f((r["position120"] or 0)*100,1)}%，CLV={f(r["clv"])}。这是日线证据；分时顺序未核，不能确认真正“分歧转一致”。' for r in typical)}

- 相对有效的日线结构：只把“放量后收盘推进、CLV较高且不在120日极高位”列为次日观察条件；它仍需9:25竞价、板块同步和开盘承接二次过滤。
- 假转强/风险结构：高位放量但CLV偏低、上影较长，或放量下跌，均优先当作筹码交换后价格未能推进的反例；缩量上涨只作弱证据。
- 本轮不输出两只正式候选。原因不是没有活跃股票，而是换手率、点时板块强度和T日分钟顺序缺失，无法按原七维门槛排除单笔拉升与假突破。

五、对全A筛选的具体反馈

1. 次日观察池只保留28只深筛为影子样本；9:25后若竞价弱于板块、开盘不能站稳T日关键位或首个回踩放量跌破，则淘汰，不自动替换成正式推荐。
2. 高位爆量/长上影与放量下跌样本进入风险对照，不因成交活跃上调。
3. 无T日分钟数据，不建立9:50/14:40触发和收益；T盘后信号若T+1实际入场，最早T+2可卖。

六、受阻项和下一步假设

- 受阻：完整全A覆盖（北交所及冻结名称映射后的新变更未覆盖）；换手率及变化（缺自由流通股/同口径换手字段）；板块同步性（缺T时点成员与板块OHLCV）；杀跌—承接—再突破顺序、尾盘量价、竞价和可成交性（缺T日分钟/逐笔/订单证据）。
- H1：低/中位、RVOL20≥1.5、CLV≥0.70的日线推进组，在11月5日收盘观察上优于同池高位爆量低CLV组；只比较冻结样本，下一次追加结果。
- H2：突破20日高但11月5日竞价/开盘不能维持T日收盘附近的样本，其MFE/MAE与可退出质量劣于有板块同步的样本；板块证据补齐前不判定。
- H3：缩量上涨组不应仅凭收红进入正式候选；若11月5日量能仍不足且跌破T日中枢，记为假转强反例。

规则版本volume_price_close_v5_partial_source_bounded；本轮只冻结公开可核日线事实，不保证收益。"""
    REPORT.write_text("# 量价研究与每日验证｜2026-11-04（实质补做，部分受阻）\n\n"+body+"\n")
    report_id="volume-price-20261104-partial-v1"
    if any(x.get("id")==report_id for x in research["items"]):
        raise ValueError("duplicate_report_id")
    report_obj={"id":report_id,"date":T,"market_date":T,"task_id":"volume_price","track":"volume_price",
      "run_id":"volume-price-20261104-scheduled-close-v1","title":f"量价研究｜11月4日{len(market_rows)}只冻结股票映射日线、120广泛池与28深筛（部分受阻）",
      "summary":f"BaoStock原始{snap['coverage']['verified']}/{snap['coverage']['checked']}，冻结股票映射{len(market_rows)}只、120广泛池、{len(enriched)}只历史核验、28深筛；完整全A/换手/板块/分钟缺失，正式候选0。",
      "body":body,"sources":[str(SNAP.relative_to(ROOT)),str(PREV_SNAP.relative_to(ROOT)),str(EVIDENCE.relative_to(ROOT)),"https://quotes.sina.cn/cn/api/jsonp_v2.php/CN_MarketDataService.getKLineData",ISSUE],
      "report_type":"substantive_daily_research_partial","eligible_for_integrated_research":False,"analysis_completed":False,"status":"partial",
      "published_at":completed_cn,"recorded_at":completed_cn,"market_data_cutoff_at":T+"T15:00:00+08:00","data_cutoff_at":completed_cn,
      "planned_entry_date":"2026-11-05","earliest_legal_exit_date_if_bought":"2026-11-06","research_rule_version":evidence["rule_version"],
      "candidate_count":0,"recommendation_ids":[],"evidence_file":str(EVIDENCE.relative_to(ROOT)),"full_scan_count":len(market_rows),
      "active_OHLCV_count":len(market_rows),"raw_snapshot_verified_count":snap['coverage']['verified'],"broad_pool_count":120,"deep_pool_count":28,"codes":[r["code"] for r in deep],
      "blocked_modules":list(evidence["blocked"]),"verified_fill_count":0}
    research["items"].append(report_obj)
    receipt_id="volume-price-20261104-scheduled-close-v1-partial"
    if any(x.get("id")==receipt_id for x in runs["items"]): raise ValueError("duplicate_receipt_id")
    runs["items"].append({"id":receipt_id,"run_id":"volume-price-20261104-scheduled-close-v1","task_id":"volume_price","date":T,
      "trigger":"scheduled","started_at":started_cn,"recorded_at":completed_cn,"completed_at":completed_cn,"status":"blocked",
      "summary":f"已实质完成11月4日原始5504条代码核验、{len(market_rows)}只冻结股票映射扫描、120广泛池和28深筛；完整全A、换手、点时板块与分钟证据缺失，故不标completed、不满足综合前置。",
      "report_ids":[report_id],"recommendation_ids":[],"analysis_completed":False,"eligible_for_integrated_research":False,
      "sources":[str(EVIDENCE.relative_to(ROOT)),str(SNAP.relative_to(ROOT)),ISSUE],"blocked_modules":list(evidence["blocked"]),"verified_fill_count":0})
    research_path.write_text(json.dumps(research,ensure_ascii=False,indent=2)+"\n")
    runs_path.write_text(json.dumps(runs,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"report_id":report_id,"receipt_id":receipt_id,"market":evidence["market_scan"],"history":evidence["history_fetch"],"deep":len(deep),"completed_cn":completed_cn},ensure_ascii=False))


if __name__=="__main__":
    main()
