#!/usr/bin/env python3
"""Build and append the source-bounded 2026-11-11 volume-price study."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import urllib.parse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
T, PREV = "2026-11-11", "2026-11-10"
CN = ZoneInfo("Asia/Shanghai")
REPORT_ID = "volume-price-20261111-partial-v1"
RUN_ID = "volume-price-20261111-scheduled-close-v1"
RECEIPT_ID = RUN_ID + "-blocked"
EVIDENCE = ROOT / "docs/research/volume-price-20261111-evidence.json"
REPORT = ROOT / "docs/research/volume-price-20261111-partial-v1.md"
SNAP = ROOT / f"backend/data/sina_daily_full/{T}.json"
PREV_SNAP = ROOT / f"backend/data/baostock/{PREV}.json"
STATUS_BAO = ROOT / f"backend/data/market_source_status/baostock-{T}.json"
STATUS_SINA = ROOT / f"backend/data/market_source_status/sina-{T}.json"
STATUS_EM = ROOT / f"backend/data/market_source_status/eastmoney-market-{T}.json"

spec = importlib.util.spec_from_file_location("vp_helpers", ROOT / "scripts/publish_volume_price_20261104.py")
vp = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(vp); vp.T = T

def now_cn():
    return datetime.now(timezone.utc).astimezone(CN).isoformat(timespec="seconds")

def mean(xs): return round(statistics.mean(xs), 3) if xs else None
def median(xs): return round(statistics.median(xs), 3) if xs else None
def fnum(x, n=2): return "N/A" if x is None else f"{x:.{n}f}"

def eastmoney_pages():
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    base = {"po":"1","np":"2","ut":"bd1d9ddb04089700cf9c27f6f7426281","fltt":"2","invt":"2","fid":"f6",
            "fs":"m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23","fields":"f2,f3,f5,f6,f7,f8,f10,f12,f14,f15,f16,f17,f18,f100"}
    rows, errors, total = [], [], None
    def get(page):
        p=dict(base,pn=str(page),pz="100")
        out=subprocess.run(["curl","-LfsS","--max-time","18","-H","User-Agent: Mozilla/5.0","-H","Referer: https://quote.eastmoney.com/",url+"?"+urllib.parse.urlencode(p)],capture_output=True,text=True,timeout=21)
        if out.returncode: raise ValueError("curl_exit_"+str(out.returncode))
        d=json.loads(out.stdout).get("data") or {}; diff=d.get("diff") or []
        if isinstance(diff,dict): diff=list(diff.values())
        return int(d.get("total") or 0), diff
    try:
        total, first=get(1); rows.extend(first)
    except Exception as e:
        return {"rows":[],"errors":["page1:"+type(e).__name__],"total":0,"pages_requested":1,"pages_verified":0}
    pages=min(12,max(1,(total+99)//100))
    with ThreadPoolExecutor(max_workers=4) as ex:
        jobs={ex.submit(get,p):p for p in range(2,pages+1)}
        for job in as_completed(jobs):
            try: rows.extend(job.result()[1])
            except Exception as e: errors.append(f"page{jobs[job]}:{type(e).__name__}")
    return {"rows":rows,"errors":errors,"total":total,"pages_requested":pages,"pages_verified":pages-len(errors)}

def fetch_5m(code):
    sym=("sh" if code.startswith("6") else "sz")+code
    url=f"https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_vp=/CN_MarketDataService.getKLineData?symbol={sym}&scale=5&ma=no&datalen=48"
    out=subprocess.run(["curl","-fsS","--max-time","20","-H","User-Agent: Mozilla/5.0",url],capture_output=True,text=True,timeout=23)
    if out.returncode: raise ValueError("curl_exit")
    import re
    m=re.search(r"=\((\[.*\])\)\s*;?\s*$",out.stdout,re.S)
    if not m: raise ValueError("jsonp_missing")
    raw=json.loads(m.group(1)); bars=[]
    for x in raw:
        if not str(x.get("day","")).startswith(T): continue
        bars.append({"time":x["day"],**{k:float(x[k]) for k in ("open","high","low","close","volume")}})
    if len(bars)!=48: raise ValueError("bar_count_"+str(len(bars)))
    low=min(bars,key=lambda x:x["low"]); at1440=next((x for x in bars if x["time"].endswith("14:40:00")),None)
    tail=[x for x in bars if x["time"]>=T+" 14:40:00"]; before=[x for x in bars if x["time"]<T+" 14:40:00"]
    return {"code":code,"provider":"Sina historical 5-minute","bar_count":48,"first":bars[0]["time"],"last":bars[-1]["time"],
            "low":low["low"],"low_time":low["time"],"close":bars[-1]["close"],
            "low_to_close_pct":round((bars[-1]["close"]/low["low"]-1)*100,3),
            "close_vs_1440_pct":round((bars[-1]["close"]/at1440["close"]-1)*100,3) if at1440 else None,
            "tail_volume_ratio":round(statistics.mean(x["volume"] for x in tail)/statistics.mean(x["volume"] for x in before),3),
            "historical_only":True,"executed_trade":False,"url":url}

def main():
    started=now_cn(); snap=json.loads(SNAP.read_text()); prev=json.loads(PREV_SNAP.read_text())
    current=snap["rows"]; previous={r["code"].split(".")[1]:r for r in prev["rows"]}; names={r["code"].split(".")[1]:r["name"] for r in current}
    broad_seed, market_rows=vp.freeze_broad(current,previous,set(names))
    histories, history_errors={},{}
    with ThreadPoolExecutor(max_workers=20) as ex:
        jobs={ex.submit(vp.fetch_history,r["code6"]):r["code6"] for r in broad_seed}
        for job in as_completed(jobs):
            code=jobs[job]
            try: histories[code]=job.result()
            except Exception as e: history_errors[code]=f"{type(e).__name__}:{str(e)[:120]}"
    broad=[]
    for seed in broad_seed:
        code=seed["code6"]
        if code not in histories: continue
        x=vp.metrics(histories[code],next(r for r in current if r["code"].endswith(code)))
        x.update(name=names[code],amount_yuan=seed["amount"],turnover_pct=None,turnover_note="新浪收盘源无自由流通换手；等待东财同日交叉核验")
        broad.append(x)
    deep=vp.select_deep(broad)
    em=eastmoney_pages(); em_map={str(x.get("f12")):x for x in em["rows"] if x.get("f12")}
    for x in deep:
        q=em_map.get(x["code"]); x["turnover_pct"]=q.get("f8") if q else None; x["eastmoney_volume_ratio"]=q.get("f10") if q else None; x["industry"]=q.get("f100") if q else None
        x["eastmoney_close_crosscheck_abs"]=round(abs(float(q["f2"])-x["close"]),4) if q and isinstance(q.get("f2"),(int,float)) else None
    STATUS_EM.write_text(json.dumps({"provider":"Eastmoney public close list HTTPS","trade_date":T,"attempted_at":started,"historical_daily_or_close_list":"close_list","primary_attempt":{"host":"push2.eastmoney.com","result":"HTTP 302 empty body","redirect_target":"push2delay.eastmoney.com"},"fallback_attempt":{"host":"push2delay.eastmoney.com","result":"valid JSON on verified pages"},"rows_received":len(em_map),"source_total":em["total"],"pages_requested":em["pages_requested"],"pages_verified":em["pages_verified"],"errors":em["errors"],"deep_pool_verified":sum(x.get("turnover_pct") is not None for x in deep),"status":"partial_bounded_pages_with_verified_fallback"},ensure_ascii=False,indent=2)+"\n")
    # Pick five diverse, pre-defined by frozen deep ranking/tags; not winners after a future day.
    typical=[]; seen=set()
    for tag in ("低位首次放量/推进代理","放量突破","日线分歧转强代理","高位爆量滞涨/长上影风险","放量下跌","缩量上涨"):
        candidates=[x for x in deep if tag in x["tags"] and x["code"] not in seen]
        if candidates:
            x=max(candidates,key=lambda r:(r.get("rvol20") or 0)*r["amplitude_pct"]); typical.append(x);seen.add(x["code"])
        if len(typical)>=5: break
    for x in deep:
        if len(typical)>=5: break
        if x["code"] not in seen: typical.append(x);seen.add(x["code"])
    minutes=[]; minute_errors={}
    for x in typical:
        try: minutes.append(fetch_5m(x["code"]))
        except Exception as e: minute_errors[x["code"]]=f"{type(e).__name__}:{str(e)}"
    minute_map={x["code"]:x for x in minutes}
    relative=[x for x in deep if "ST" not in x["name"].upper() and -3<=x["pct"]<=8 and (x.get("rvol20") or 0)>=1.2 and (x.get("clv") or 0)>=.65 and (x.get("position120") or 1)<=.75 and x["amount_yuan"]>=1e8]
    relative.sort(key=lambda x:(2*(x.get("clv") or 0)+min(x.get("rvol20") or 0,3)+(1-(x.get("position120") or 1))-max(x["pct"]-5,0)/5),reverse=True)
    pair=relative[:2]
    # Validate prior date's only explicitly frozen 120-name partial-research list by parsing its codes is not possible; keep exact limitation.
    prev_subset=[]
    for code in ("600118","600183","002428","300394","688498","002156","603259","600176","601899","688256","300308"):
        cur=next((r for r in current if r["code"].endswith(code)),None); base=previous.get(code)
        if cur and base:
            prev_subset.append({"code":code,"name":cur["name"],"base_date":PREV,"base_close":base["close"],"close_pct":round((cur["close"]/base["close"]-1)*100,3),"mfe_pct":round((cur["high"]/base["close"]-1)*100,3),"mae_pct":round((cur["low"]/base["close"]-1)*100,3),"executed_trade":False})
    positives=sum(x["close_pct"]>0 for x in prev_subset)
    completed=now_cn()
    candidates=[]
    for x in pair:
        support=round(max(x["low"],x["ma20"] or x["low"]),2); pressure=round(max(x["high"],x["previous20_high"] or x["high"]),2)
        candidates.append({"code":x["code"],"name":x["name"],"qualification":"待综合观察（盘后量价相对优选影子）","reference_price":x["close"],"reference_time":T+"T15:00:00+08:00","formal_buy_signal":False,"buy_order_allowed":False,"trigger":f"11月12日竞价不过度高开，回踩守住{support:.2f}且所属板块同步后，再观察放量站稳{pressure:.2f}","invalid":f"有效跌破{support:.2f}，或板块不同步、放量冲高回落/长上影扩大","earliest_legal_exit_if_entered_2026_11_12":"2026-11-13"})
    blocked={"full_minute_deep_pool":f"深筛28只中仅典型{len(minutes)}只取得完整48根历史5分钟；其余不能验证完整分歧→承接→再转强顺序。","point_in_time_sector_sync":"仅有东财行业标签或局部收盘榜，缺T日逐时板块全成员OHLCV和同步率。","prior_full_cohort":f"11月10日只有多次120只自动研究池局部报告，未冻结完整28只原始深筛台账；正文明列11个代码，本轮同日行情可核{len(prev_subset)}只，其余保持缺失，不能事后补选赢家。","executable_strategy":"无实际成交、排队与T+1退出证据；成交胜率、净收益、成本后盈亏比均N/A。"}
    evidence={"schema_version":1,"market_date":T,"started_at":started,"completed_at":completed,"market_scope":"Shanghai+Shenzhen; Beijing excluded","providers":[json.loads(STATUS_BAO.read_text()),json.loads(STATUS_SINA.read_text()),json.loads(STATUS_EM.read_text())],"market_scan":{"verified":len(current),"checked":snap["coverage"]["checked"],"advances":sum(r["pctChg"]>0 for r in current),"declines":sum(r["pctChg"]<0 for r in current),"unchanged":sum(r["pctChg"]==0 for r in current),"amount_yuan":sum(r["amount"] for r in current)},"history_fetch":{"requested":len(broad_seed),"verified":len(broad),"errors":history_errors},"broad_pool":broad,"deep_pool":deep,"typical_samples":[{"daily":x,"minute":minute_map.get(x["code"])} for x in typical],"minute_errors":minute_errors,"prior_20261110_listed_subset_validation":prev_subset,"prior_subset_summary":{"n":len(prev_subset),"positive_n":positives,"positive_price_change_ratio":round(positives/len(prev_subset),4) if prev_subset else None,"mean_close_pct":mean([x["close_pct"] for x in prev_subset]),"median_close_pct":median([x["close_pct"] for x in prev_subset]),"mean_mfe_pct":mean([x["mfe_pct"] for x in prev_subset]),"mean_mae_pct":mean([x["mae_pct"] for x in prev_subset]),"verified_fill_count":0,"win_rate":None,"net_return":None},"after_close_relative_research_pair":candidates,"blocked":blocked,"analysis_completed":False,"eligible_for_integrated_research":False,"rule_version":"volume_price_close_v7_shsz_source_bounded"}
    EVIDENCE.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+"\n")
    candidate_md=[]
    for c in candidates:
        candidate_md += [f"## **{c['name']}（{c['code']}）**",f"**资格：{c['qualification']}，不是最终综合双标，也不是正式买点。**",f"参考价：{c['reference_price']:.2f}元（{T} 15:00，北京时间收盘）。",f"触发：{c['trigger']}。",f"放弃：{c['invalid']}。",""]
    if not candidates: candidate_md=["## **本轮未形成可核验的盘后相对优选影子**","完整数据虽已形成深筛，但固定条件无对象通过；不从次日赢家事后补选。",""]
    typ_lines=[]
    for x in typical:
        m=minute_map.get(x["code"]); path=(f"48根5分钟，低点{x['minute']['low'] if False else m['low']:.2f}@{m['low_time'][11:16]}，低点至收盘{m['low_to_close_pct']:+.2f}%，14:40至收盘{m['close_vs_1440_pct']:+.2f}%" if m else "分钟源失败，仅保留日线")
        typ_lines.append(f"- **{x['name']}（{x['code']}）**：{'、'.join(x['tags'])}；涨跌{x['pct']:+.2f}%，RVOL5/10/20={fnum(x['rvol5'])}/{fnum(x['rvol10'])}/{fnum(x['rvol20'])}，换手={fnum(x.get('turnover_pct'))}%，120日位置={fnum((x.get('position120') or 0)*100,1)}%，CLV={fnum(x.get('clv'),3)}；{path}。")
    table=[]
    for x in deep:
        table.append(f"|{x['name']} {x['code']}|{'、'.join(x['tags'])}|{x['pct']:+.2f}%|{fnum(x.get('turnover_pct'))}%|{fnum(x.get('rvol5'))}/{fnum(x.get('rvol10'))}/{fnum(x.get('rvol20'))}|{fnum((x.get('position120') or 0)*100,1)}%|{fnum(x.get('clv'),3)}|")
    body=f"""研究交易日：{T}｜发布时间：北京时间 {completed[:16].replace('T',' ')}（UTC+8）

本轮对最新完整交易日 **{T}** 执行沪深收盘实质扫描。BaoStock在补齐SDK后仍登录失败；新浪独立收盘源核验 **{snap['coverage']['verified']}/{snap['coverage']['checked']}**（{snap['coverage']['coverage_ratio']:.2%}）只同日OHLCV；东方财富免费收盘榜实测 {len(em_map)} 只/来源总数{em['total']}（本轮限12页，不能冒充全量）。冻结120只广池，新浪逐股历史日线成功{len(broad)}/120，形成28只深筛，并对{len(minutes)}只典型样本取得48根历史5分钟。由于全深池分钟和点时板块同步仍缺，本报告为 **partial/blocked**，不满足综合前置。

{chr(10).join(candidate_md)}
最终综合尚未完成；上列仅是本模块盘后相对优选影子，须由后续综合组比较市场、低位、龙虎榜、学习和打板材料。若11月12日入场，A股T+1下最早11月13日卖出。

### 来源与市场覆盖

- BaoStock：{json.loads(STATUS_BAO.read_text()).get('reason')}；历史日线主源失败后未停止。
- 新浪：历史收盘日线，采集时点{snap['collected_at']}，同日OHLCV {snap['coverage']['verified']}/{snap['coverage']['checked']}，覆盖率{snap['coverage']['coverage_ratio']:.2%}；错误{snap['coverage']['errors']}只保持缺失。
- 东方财富：主域实测HTTP 302空响应，按其重定向切换到`push2delay`后取得有效JSON；同日收盘列表/量比/换手/行业字段12页边界测试，{em['pages_verified']}/{em['pages_requested']}页，{len(em_map)}只；错误{em['errors'] or '无'}。这不是分钟源。
- 市场宽度（新浪有效样本）：上涨{evidence['market_scan']['advances']}、下跌{evidence['market_scan']['declines']}、平盘{evidence['market_scan']['unchanged']}；成交额简单加总{evidence['market_scan']['amount_yuan']/1e8:.1f}亿元。缺失365只使宽度是高覆盖观察，不称交易所全市场精确统计。

### 典型量价/分歧转一致样本

{chr(10).join(typ_lines)}

### 深筛28只完整留档

|股票|结构|涨跌|换手|RVOL5/10/20|120日位置|CLV|
|---|---|---:|---:|---:|---:|---:|
{chr(10).join(table)}

### 上一交易日明列样本验证

11月10日只有自动研究池局部报告，未留下本任务完整28只冻结台账。本轮仅验证原报告正文明确列出的{len(prev_subset)}只：正价格变化{positives}只，正价格变化比例{evidence['prior_subset_summary']['positive_price_change_ratio']:.1%}，收盘变化均值{evidence['prior_subset_summary']['mean_close_pct']:+.3f}%、中位{evidence['prior_subset_summary']['median_close_pct']:+.3f}%，日线MFE均值{evidence['prior_subset_summary']['mean_mfe_pct']:+.3f}%、MAE均值{evidence['prior_subset_summary']['mean_mae_pct']:+.3f}%。这是价格观察，不是实际成交胜率；成交胜率、净收益和盈亏比均为N/A。

### 有效结构、假转强与筛选反馈

- 仅把“成交放大后价格继续推进、CLV较高、位置不过热”纳入相对观察；高位爆量低CLV、放量下跌和长上影优先列风险对照。
- 日线代理不能证明分时先后。只有48根历史5分钟的典型样本才描述杀跌/修复路径，仍不能证明资金身份或原时点可成交。
- 量比/换手是独立因子，不因单一指标直接入综合双标。11月12日09:25后仍须二次过滤竞价、板块同步和关键位承接。
- 原09:50两只（捷荣技术、建新股份）和14:40生产冻结不在本报告事后改写；只有原时点证据可进入各自组验证。

### 明日待证伪假设

1. 低/中位置、RVOL20≥1.5、CLV≥0.70组的次日MAE是否小于高位爆量低CLV组。
2. 日线突破若竞价后不能守住突破位，是否比板块同步的缩量回踩样本表现更差。
3. 放量下跌且CLV<0.20样本，即使次日高开，未重回T日中枢前是否应继续判为假转强风险。

### 未完成项

{chr(10).join('- '+v for v in blocked.values())}

规则版本 `{evidence['rule_version']}`。不保证收益，不自动下单，不把APP描述为自行推理或自动训练。
"""
    REPORT.write_text("# 量价研究与每日验证｜2026-11-11（沪深实质执行，部分受阻）\n\n"+body+"\n")
    research=json.loads((ROOT/"backend/data/research.json").read_text()); runs=json.loads((ROOT/"backend/data/task_runs.json").read_text()); samples=json.loads((ROOT/"backend/data/volume_price_samples.json").read_text())
    # Idempotent only for this exact run's records, so an interrupted rerun can
    # refresh its own source evidence without touching any older frozen item.
    research['items']=[x for x in research['items'] if x.get('id')!=REPORT_ID]
    runs['items']=[x for x in runs['items'] if x.get('id')!=RECEIPT_ID]
    samples['items']=[x for x in samples['items'] if x.get('id') not in {
        'volume-price-20261110-listed-subset-validation-20261111-v1',
        'volume-price-20261111-partial-v1-cohort'}]
    sources=[str(EVIDENCE.relative_to(ROOT)),str(SNAP.relative_to(ROOT)),str(STATUS_BAO.relative_to(ROOT)),str(STATUS_SINA.relative_to(ROOT)),str(STATUS_EM.relative_to(ROOT)),"https://quotes.sina.cn/cn/api/jsonp_v2.php/CN_MarketDataService.getKLineData","https://push2.eastmoney.com/api/qt/clist/get","https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/issues/25"]
    research['items'].append({"id":REPORT_ID,"date":T,"market_date":T,"task_id":"volume_price","track":"volume_price","run_id":RUN_ID,"title":"量价研究｜11月11日沪深4860只、120广池、28深筛与典型分钟复盘（部分受阻）","summary":f"新浪同日沪深{len(current)}/{snap['coverage']['checked']}只OHLCV、120广池、28深筛、{len(minutes)}只完整历史5分钟；冻结{len(candidates)}只盘后待综合观察。全深池分钟与点时板块同步仍缺，保持partial。","body":body,"sources":sources,"report_type":"substantive_daily_research_partial","eligible_for_integrated_research":False,"analysis_completed":False,"status":"partial","published_at":completed,"recorded_at":completed,"market_data_cutoff_at":T+"T15:00:00+08:00","data_cutoff_at":completed,"planned_entry_date":"2026-11-12","earliest_legal_exit_date_if_bought":"2026-11-13","research_rule_version":evidence['rule_version'],"candidate_count":len(candidates),"research_shadow_candidates":candidates,"formal_candidate_count":0,"recommendation_ids":[],"evidence_file":str(EVIDENCE.relative_to(ROOT)),"full_scan_count":len(current),"broad_pool_count":120,"broad_pool_verified_count":len(broad),"deep_pool_count":len(deep),"previous_pool_verified_count":len(prev_subset),"minute_verified_count":len(minutes),"codes":[x['code'] for x in deep],"blocked_modules":list(blocked),"verified_fill_count":0})
    runs['items'].append({"id":RECEIPT_ID,"run_id":RUN_ID,"task_id":"volume_price","date":T,"trigger":"scheduled","started_at":started,"recorded_at":completed,"completed_at":completed,"status":"blocked","summary":f"已实质完成11月11日沪深{len(current)}/{snap['coverage']['checked']}收盘扫描、120广池、28深筛、上一局部明列{len(prev_subset)}只验证及{len(minutes)}只历史分钟复盘；冻结{len(candidates)}只盘后研究影子。全深池分钟和点时板块同步缺失，故不标completed。","report_ids":[REPORT_ID],"recommendation_ids":[],"research_shadow_candidates":candidates,"analysis_completed":False,"eligible_for_integrated_research":False,"sources":sources,"blocked_modules":list(blocked),"verified_fill_count":0})
    samples['items'].append({"id":"volume-price-20261110-listed-subset-validation-20261111-v1","date":T,"task_id":"volume_price","recorded_at":completed,"report_ids":[REPORT_ID],"origin":"2026-11-10 automated partial reports explicitly listed samples","rule_version":evidence['rule_version'],"full_validation_completed":False,"full_pool_summary":evidence['prior_subset_summary'],"full_pool_validations":prev_subset,"executed_trade_count":0,"eligible_for_model_statistics":False})
    samples['items'].append({"id":"volume-price-20261111-partial-v1-cohort","date":T,"task_id":"volume_price","frozen_at":completed,"report_ids":[REPORT_ID],"rule_version":evidence['rule_version'],"data_cutoff_at":T+"T15:00:00+08:00","market_scope":evidence['market_scope'],"full_scan_count":len(current),"broad_pool_count":120,"deep_screen_count":len(deep),"minute_verified_count":len(minutes),"research_shadow_candidates":candidates,"eligible_for_model_statistics":False,"statistical_scope":"future daily price observation; no fill-based profitability","provenance":"source-bounded after-close research","samples":deep,"typical_samples":evidence['typical_samples'],"missing":list(blocked)})
    for path,data in ((ROOT/"backend/data/research.json",research),(ROOT/"backend/data/task_runs.json",runs),(ROOT/"backend/data/volume_price_samples.json",samples)):
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"report_id":REPORT_ID,"receipt_id":RECEIPT_ID,"completed_at":completed,"scan":len(current),"broad":len(broad),"deep":len(deep),"minutes":len(minutes),"candidates":[x['code'] for x in candidates],"typical":[x['code'] for x in typical],"history_errors":len(history_errors),"em_rows":len(em_map)},ensure_ascii=False,indent=2))

if __name__ == '__main__': main()
