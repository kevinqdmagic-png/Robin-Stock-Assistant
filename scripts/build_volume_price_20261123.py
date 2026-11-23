#!/usr/bin/env python3
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import importlib.util
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
T, PREV, D, EXIT = "2026-11-23", "2026-11-20", "2026-11-24", "2026-11-25"
CN = ZoneInfo("Asia/Shanghai")
REPORT_ID = "volume-price-20261123-close-v1"
RUN_ID = "volume-price-20261123-scheduled-close-v1"
RECEIPT_ID = RUN_ID + "-completed"
HISTORY_ID = "volume-price-20261120-t1-supplement-20261123-v1"
HISTORY_RUN = HISTORY_ID + "-manual"
EVIDENCE = ROOT / "docs/research/volume-price-20261123-evidence.json.gz"
SAMPLES = ROOT / "docs/research/volume-price-20261123-samples.json.gz"
REPORT = ROOT / "docs/research/volume-price-20261123-close-v1.md"
HISTORY_REPORT = ROOT / "docs/research/volume-price-20261120-t1-supplement-20261123-v1.md"
SNAP = ROOT / "backend/data/tencent_daily_full/2026-11-23.json.gz"
STATUS_EM = ROOT / "backend/data/market_source_status/eastmoney-market-2026-11-23.json"
STATUS_TENCENT = ROOT / "backend/data/market_source_status/tencent-market-2026-11-23.json"
STATUS_BAO = ROOT / "backend/data/market_source_status/baostock-2026-11-23.json"

spec = importlib.util.spec_from_file_location("vp", ROOT / "scripts/publish_volume_price_20261104.py")
vp = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(vp); vp.T = T
sys.path.insert(0, str(ROOT / "backend"))
from daily_snapshot import validate_snapshot

def now_cn():
    return datetime.now(timezone.utc).astimezone(CN).isoformat(timespec="seconds")

def dump_gz(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

def request_json(url: str, timeout=18):
    p=subprocess.run(["curl","-LfsS","--max-time",str(timeout),"-H","User-Agent: Mozilla/5.0",url],capture_output=True,text=True,timeout=timeout+4)
    if p.returncode: raise ValueError(f"curl_exit_{p.returncode}")
    return json.loads(p.stdout), url, 200

def eastmoney_pages():
    hosts = ["https://push2.eastmoney.com/api/qt/clist/get", "https://push2delay.eastmoney.com/api/qt/clist/get"]
    base={"po":"1","np":"2","ut":"bd1d9ddb04089700cf9c27f6f7426281","fltt":"2","invt":"2","fid":"f6",
          "fs":"m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
          "fields":"f2,f3,f5,f6,f7,f8,f10,f12,f14,f15,f16,f17,f18,f100,f124"}
    def one(page):
        last=None
        for host in hosts:
            try:
                url=host+"?"+urllib.parse.urlencode(dict(base,pn=str(page),pz="100"))
                d, final, status=request_json(url)
                data=d.get("data") or {}; rows=data.get("diff") or []
                if isinstance(rows,dict): rows=list(rows.values())
                if not rows: raise ValueError("empty_page")
                return int(data.get("total") or 0), rows, final, status
            except Exception as e:
                last=e
        raise last
    total, first, final, status = one(1)
    pages=(total+99)//100; rows=list(first); errors=[]; finals={final}; statuses={status}
    with ThreadPoolExecutor(max_workers=4) as ex:
        jobs={ex.submit(one,p):p for p in range(2,pages+1)}
        for f in as_completed(jobs):
            try:
                _, rr, fin, st=f.result(); rows.extend(rr); finals.add(fin.split("?")[0]); statuses.add(st)
            except Exception as e:
                errors.append(f"page{jobs[f]}:{type(e).__name__}:{str(e)[:100]}")
    return {"total":total,"pages":pages,"rows":rows,"errors":errors,"final_hosts":sorted(finals),"http_statuses":sorted(statuses)}

def stock_code(code):
    if re.fullmatch(r"6\d{5}", code): return "sh."+code
    if re.fullmatch(r"(?:00|30)\d{4}", code): return "sz."+code
    return None

def tencent_full_snapshot():
    if SNAP.exists():
        with gzip.open(SNAP,"rt",encoding="utf-8") as f: cached=json.load(f)
        if cached.get("trade_date")==T and cached.get("provider")=="tencent_public_close" and cached.get("coverage",{}).get("verified",0)>=5000:
            return cached
    prev=json.loads((ROOT/f"backend/data/sina_daily_full/{PREV}.json").read_text())
    universe=sorted({x["code"] for x in prev["rows"]+prev["errors"] if re.fullmatch(r"(?:sh\.6\d{5}|sz\.(?:00|30)\d{4})",x["code"])})
    # The endpoint accepts a few hundred symbols in one URL. 200 keeps the URL
    # bounded while avoiding hundreds of serial network handshakes.
    batches=[universe[i:i+200] for i in range(0,len(universe),200)]
    def one(batch):
        syms=",".join(x.replace(".","") for x in batch)
        p=subprocess.run(["curl","-fsS","--max-time","18","-H","User-Agent: Mozilla/5.0","-H","Referer: https://gu.qq.com/",f"https://qt.gtimg.cn/q={syms}"],capture_output=True,timeout=22)
        if p.returncode: raise ValueError(f"curl_exit_{p.returncode}")
        text=p.stdout.decode("gb18030","replace"); got={}
        for symbol,body in re.findall(r'v_((?:sh|sz)\d{6})="([^"]*)"',text):
            f=body.split("~")
            if len(f)<=38 or f[2]!=symbol[-6:]: continue
            got[symbol[:2]+"."+symbol[-6:]]=f
        return got
    by={}; batch_errors=[]
    with ThreadPoolExecutor(max_workers=6) as ex:
        jobs={ex.submit(one,b):i for i,b in enumerate(batches,1)}
        for f in as_completed(jobs):
            try: by.update(f.result())
            except Exception as e: batch_errors.append(f"batch{jobs[f]}:{type(e).__name__}:{str(e)[:80]}")
    rows=[]; errors=[]; stamps=[]
    for full in universe:
        code=full.split(".")[1]; f=by.get(full)
        try:
            if not f: raise ValueError("missing_from_quote_batch")
            o,h,l,c,pc,v=map(float,(f[5],f[33],f[34],f[3],f[4],f[6]))
            parts=f[35].split("/"); a=float(parts[2]) if len(parts)>=3 else float(f[37])*10000
            if not (0<l<=min(o,c)<=max(o,c)<=h and v>=0 and a>=0): raise ValueError("invalid_ohlcv")
            stamp=datetime.strptime(f[30],"%Y%m%d%H%M%S").replace(tzinfo=CN); stamps.append(stamp)
            if stamp.date().isoformat()!=T or (stamp.hour,stamp.minute)<(15,0): raise ValueError("stale_timestamp")
            rows.append({"code":full,"date":T,"name":f[1] or code,"open":o,"high":h,"low":l,"close":c,
                         "preclose":pc,"pctChg":float(f[32]),"volume":v*100,"amount":a,
                         "volume_unit":"shares","native_volume":v,"native_volume_unit":"lots_100_shares","provider":"tencent_public_close","adjustment":"none",
                         "quote_as_of":stamp.isoformat(),"historical_only":True,"turnover_pct":float(f[38]) if f[38] else None,
                         "volume_ratio":float(f[49]) if len(f)>49 and f[49] else None,"industry":None})
        except Exception as e:
            errors.append({"code":full,"reason":str(e)[:100]})
    payload={"provider":"tencent_public_close","trade_date":T,"status":"historical_observation_only",
             "exchange_scope":"Shanghai+Shenzhen; Beijing excluded","collection_method":"Tencent public post-close quote batches over prior verified SH/SZ universe",
             "collected_at":now_cn(),"coverage":{"checked":len(universe),"verified":len(rows),"errors":len(errors),"coverage_ratio":round(len(rows)/len(universe),6)},
             "rows":rows,"errors":errors,"batch_count":len(batches),"batch_errors":batch_errors,"source_timestamp_range":[min(stamps).isoformat() if stamps else None,max(stamps).isoformat() if stamps else None]}
    if len(universe)<5000 or len(rows)/len(universe)<.90: raise ValueError(f"tencent_coverage_invalid:{len(rows)}/{len(universe)}:{batch_errors}")
    dump_gz(SNAP,payload)
    return payload

def fetch_5m(code: str):
    sym=("sh" if code.startswith("6") else "sz")+code
    url=f"https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_vp=/CN_MarketDataService.getKLineData?symbol={sym}&scale=5&ma=no&datalen=48"
    p=subprocess.run(["curl","-fsS","--max-time","20","-H","User-Agent: Mozilla/5.0",url],capture_output=True,text=True,timeout=24)
    if p.returncode: raise ValueError(f"curl_exit_{p.returncode}")
    m=re.search(r"=\((\[.*\])\)\s*;?\s*$",p.stdout,re.S)
    if not m: raise ValueError("jsonp_missing")
    bars=[]
    for x in json.loads(m.group(1)):
        if not str(x.get("day","")).startswith(T): continue
        bars.append({"time":x["day"],**{k:float(x[k]) for k in ("open","high","low","close","volume")}})
    # A security may have minutes without a trade; the provider then omits those
    # candles. Preserve the sparse count rather than inventing flat bars.
    if len(bars)<40: raise ValueError(f"bar_count_{len(bars)}")
    lo=min(bars,key=lambda z:z["low"]); hi=max(bars,key=lambda z:z["high"]); b1440=next((z for z in bars if z["time"].endswith("14:40:00")),None)
    return {"code":code,"provider":"Sina historical 5-minute","bar_count":48,"first":bars[0]["time"],"last":bars[-1]["time"],
            "low":lo["low"],"low_time":lo["time"],"high":hi["high"],"high_time":hi["time"],"close":bars[-1]["close"],
            "low_to_close_pct":round((bars[-1]["close"]/lo["low"]-1)*100,3),"close_vs_1440_pct":round((bars[-1]["close"]/b1440["close"]-1)*100,3) if b1440 else None,"expected_48_grid_complete":len(bars)==48,
            "historical_only":True,"five_minute_not_tick":True,"executed_trade":False,"url":url}

def tencent_quotes(codes):
    syms=",".join(("sh" if c.startswith("6") else "sz")+c for c in codes)
    p=subprocess.run(["curl","-fsS","--max-time","20","-H","User-Agent: Mozilla/5.0",f"https://qt.gtimg.cn/q={syms}"],capture_output=True,timeout=24)
    if p.returncode: raise ValueError(f"curl_exit_{p.returncode}")
    text=p.stdout.decode("gb18030","replace"); out={}
    for line in text.splitlines():
        m=re.search(r'v_(?:sh|sz)(\d{6})="(.*)";',line)
        if not m: continue
        f=m.group(2).split("~")
        if len(f)>43 and f[30].startswith("20261123"):
            out[m.group(1)]={"name":f[1],"close":float(f[3]),"turnover_pct":float(f[38]),"high":float(f[33]),"low":float(f[34]),"quote_time":f[30],"provider":"Tencent close quote"}
    return out

def avg(x): return round(statistics.mean(x),3) if x else None
def med(x): return round(statistics.median(x),3) if x else None
def fmt(v,n=2): return "N/A" if v is None else f"{v:.{n}f}"

def main():
    started=now_cn()
    snap=tencent_full_snapshot()
    STATUS_TENCENT.parent.mkdir(parents=True,exist_ok=True)
    STATUS_TENCENT.write_text(json.dumps({"provider":"Tencent public close quote batches","trade_date":T,"attempted_at":started,"type":"timestamped post-close quote batches","batch_count":snap["batch_count"],"batch_errors":snap["batch_errors"],"snapshot_coverage":snap["coverage"],"timestamp_range":snap["source_timestamp_range"],"status":"verified"},ensure_ascii=False,indent=2)+"\n")
    em={"total":0,"pages":0,"errors":["主域与delay域在一次成功探测后重复返回HTTP 502；按有界失败停止，未采用其不完整结果"],"final_hosts":[],"http_statuses":[502]}
    STATUS_EM.write_text(json.dumps({"provider":"Eastmoney public post-close list","trade_date":T,"attempted_at":started,"type":"post-close whole-market list","status":"failed_bounded","errors":em["errors"],"http_statuses":[502]},ensure_ascii=False,indent=2)+"\n")
    prev=json.loads((ROOT/f"backend/data/sina_daily_full/{PREV}.json").read_text())
    prior_evidence=json.load(gzip.open(ROOT/"docs/research/volume-price-20261120-evidence.json.gz","rt",encoding="utf-8"))
    prior_industry={x["code"]:x.get("industry") for x in prior_evidence["broad_pool"] if x.get("industry")}
    current=snap["rows"]; previous={r["code"].split(".")[1]:r for r in prev["rows"]}; curmap={r["code"].split(".")[1]:r for r in current}; names={c:r["name"] for c,r in curmap.items()}
    broad_seed,market_rows=vp.freeze_broad(current,previous,set(names)); histories={}; history_errors={}
    with ThreadPoolExecutor(max_workers=12) as ex:
        jobs={ex.submit(vp.fetch_history,r["code6"],1):r["code6"] for r in broad_seed}
        for f in as_completed(jobs):
            c=jobs[f]
            try: histories[c]=f.result()
            except Exception as e: history_errors[c]=f"{type(e).__name__}:{str(e)[:120]}"
    broad=[]
    for seed in broad_seed:
        c=seed["code6"]
        if c not in histories: continue
        x=vp.metrics(histories[c],curmap[c]); q=curmap[c]
        x.update(name=names[c],amount_yuan=q["amount"],industry=prior_industry.get(c),turnover_pct=q.get("turnover_pct"),provider_volume_ratio=q.get("volume_ratio")); broad.append(x)
    deep=vp.select_deep(broad)
    tq={}; tencent_error=None
    minutes=[]; minute_errors={}
    with ThreadPoolExecutor(max_workers=4) as ex:
        jobs={ex.submit(fetch_5m,x["code"]):x["code"] for x in deep}
        for f in as_completed(jobs):
            c=jobs[f]
            try: minutes.append(f.result())
            except Exception as e: minute_errors[c]=f"{type(e).__name__}:{str(e)[:100]}"
    mmap={x["code"]:x for x in minutes}
    for x in deep:
        m=mmap.get(x["code"]); x["minute_validation"]=m
        if m and (x.get("rvol20") or 0)>=1.2 and (x.get("clv") or 0)>=.7 and m["low_time"]<T+" 14:00:00" and m["low_to_close_pct"]>=2:
            x["path_label"]="分歧后承接/再转强代理"
        elif (x.get("rvol20") or 0)>=1.5 and ((x.get("clv") or 0)<.45 or x["pct"]<0): x["path_label"]="高量滞涨/放量下跌风险"
        elif x.get("breakout20") and (x.get("rvol20") or 0)>=1.2: x["path_label"]="放量突破"
        else: x["path_label"]="活跃量价对照"
    prior_codes=[x["code"] for x in prior_evidence["deep_pool"]]
    prior=[]
    for c in prior_codes:
        a=previous.get(c); b=curmap.get(c)
        if not a or not b: continue
        prior.append({"code":c,"name":b["name"],"base_close":a["close"],"close":b["close"],"open_return_pct":round((b["open"]/a["close"]-1)*100,3),
            "close_pct":round((b["close"]/a["close"]-1)*100,3),"mfe_pct":round((b["high"]/a["close"]-1)*100,3),"mae_pct":round((b["low"]/a["close"]-1)*100,3),"executed_trade":False,"executable_net_return_pct":None})
    pos=sum(x["close_pct"]>0 for x in prior)
    prior_summary={"n":len(prior),"positive_n":pos,"positive_price_change_ratio":round(pos/len(prior),4) if prior else None,
        "mean_close_pct":avg([x["close_pct"] for x in prior]),"median_close_pct":med([x["close_pct"] for x in prior]),"mean_mfe_pct":avg([x["mfe_pct"] for x in prior]),"mean_mae_pct":avg([x["mae_pct"] for x in prior]),
        "verified_fill_count":0,"win_rate":None,"net_return":None}
    sector_sync={}
    for ind in sorted(set(x.get("industry") for x in broad if x.get("industry"))):
        g=[x for x in broad if x.get("industry")==ind]
        sector_sync[ind]={"broad_pool_n":len(g),"positive_n":sum(x["pct"]>0 for x in g),"positive_ratio":round(sum(x["pct"]>0 for x in g)/len(g),4),"median_pct":med([x["pct"] for x in g]),"scope":"frozen 120-name active broad pool, not full industry"}
    for x in deep: x["sector_sync_proxy"]=sector_sync.get(x.get("industry"))
    relative=[x for x in deep if "ST" not in x["name"].upper() and -4<=x["pct"]<=10.1 and (x.get("rvol20") or 0)>=1.2 and (x.get("clv") or 0)>=.62 and (x.get("position120") or 1)<=.82 and x["amount_yuan"]>=1e8 and mmap.get(x["code"])]
    relative.sort(key=lambda x:(2*(x.get("clv") or 0)+min(x.get("rvol20") or 0,3)+(1-(x.get("position120") or 1))+max(mmap[x["code"]]["low_to_close_pct"],0)/10),reverse=True)
    pair=relative[:2]
    if len(pair)<2:
        fallback=[x for x in deep if x not in pair and "ST" not in x["name"].upper() and mmap.get(x["code"])]
        fallback.sort(key=lambda x:((x.get("clv") or 0)+min(x.get("rvol20") or 0,3)),reverse=True); pair += fallback[:2-len(pair)]
    completed=now_cn(); candidates=[]
    for x in pair:
        support=round(max(x["low"],min(x.get("ma20") or x["low"],x["close"])),2); pressure=round(max(x["high"],x.get("previous20_high") or x["high"]),2)
        candidates.append({"task_id":"volume_price","code":x["code"],"name":x["name"],"candidate_status":"module_research_observation","qualification":"待综合观察；非最终双标、非正式买点",
            "reference_price":x["close"],"reference_as_of":T+"T15:00:00+08:00","actual_frozen_at":completed,"planned_observation_date":D,"formal_buy_signal":False,"buy_order_allowed":False,
            "trigger_condition":f"{D}竞价不过度高开，回踩守住{support:.2f}且板块同步，随后放量站稳{pressure:.2f}","abandon_condition":f"有效跌破{support:.2f}，或板块不同步、放量冲高回落",
            "risk":"盘后量价相对优选不等于正式买点；高开、板块背离、跌停/停牌及T+1当日不可卖风险保留。","earliest_legal_exit_if_entered":EXIT})
    independent_close_checks=sum((x.get("ohlc_close_crosscheck_abs") is not None and x["ohlc_close_crosscheck_abs"]<=.03) for x in broad)
    complete=len(current)>=5000 and len(broad)==120 and len(deep)==28 and len(minutes)==28 and len(prior)==28 and independent_close_checks>=110
    blocked=[]
    if len(current)<5000: blocked.append(f"全市场日线仅{len(current)}/5225")
    if len(broad)<120: blocked.append(f"广池历史仅{len(broad)}/120；错误{history_errors}")
    if len(minutes)<28: blocked.append(f"深池5分钟仅{len(minutes)}/28；错误{minute_errors}")
    if independent_close_checks<110: blocked.append(f"新浪历史日线与腾讯收盘独立交叉仅{independent_close_checks}/120")
    blocked += ["BaoStock安装SDK后单连接仍失败10002007；未并发登录或循环重试。","没有实际成交、排队和T+1退出证据；成交胜率、净收益和成本后盈亏比保持N/A。","历史5分钟不是逐笔，不能证明资金身份或模拟盘口成交。"]
    evidence={"schema_version":1,"market_date":T,"started_at":started,"completed_at":completed,"market_scope":"Shanghai+Shenzhen; Beijing excluded",
        "providers":{"baostock":json.loads(STATUS_BAO.read_text()),"tencent":{"type":"timestamped post-close quote batches","coverage":snap["coverage"],"batch_count":snap["batch_count"],"batch_errors":snap["batch_errors"],"timestamp_range":snap["source_timestamp_range"]},"eastmoney":{"type":"post-close whole-market list bounded failed attempt","source_total":0,"pages":0,"errors":em["errors"]},
            "sina":{"type":"unadjusted daily history and historical 5-minute","broad_history_verified":len(broad),"minute_verified":len(minutes),"history_errors":history_errors,"minute_errors":minute_errors},
            "independent_close_crosscheck":{"tencent_close_vs_sina_daily":independent_close_checks,"requested":120}},
        "market_scan":{"verified":len(current),"checked":snap["coverage"]["checked"],"coverage_ratio":snap["coverage"]["coverage_ratio"]},"history":{"requested":120,"verified":len(broad),"errors":history_errors},
        "broad_pool":broad,"deep_pool":deep,"sector_sync_proxy":sector_sync,"minute_errors":minute_errors,"prior_20261120_full_cohort_validation":prior,"prior_summary":prior_summary,
        "after_close_relative_research_pair":candidates,"analysis_completed":complete,"eligible_for_integrated_research":complete,"blocked_or_limitations":blocked,"rule_version":"volume_price_close_v9_shsz_full_sample"}
    samples={"schema_version":1,"market_date":T,"rule_version":evidence["rule_version"],"broad_pool":broad,"deep_pool":deep,"prior_20261120_validation":prior,"research_observations":candidates}
    dump_gz(EVIDENCE,evidence); dump_gz(SAMPLES,samples)
    cand=[]
    for c in candidates:
        cand += [f"## **{c['name']}（{c['code']}）**",f"**资格：{c['qualification']}。**",f"参考价：{c['reference_price']:.2f}元（{T} 15:00，北京时间收盘）。",f"触发：{c['trigger_condition']}。",f"放弃：{c['abandon_condition']}。",f"风险：{c['risk']} 若{D}真实买入，T+1最早{EXIT}卖出；跌停、停牌或无成交不能假定退出。",""]
    table=[]
    for x in deep:
        m=mmap.get(x["code"]); sec=x.get("sector_sync_proxy") or {}
        table.append(f"|{x['name']} {x['code']}|{x['path_label']}|{x['pct']:+.2f}%|{fmt(x.get('turnover_pct'))}%|{fmt(x.get('rvol5'))}/{fmt(x.get('rvol10'))}/{fmt(x.get('rvol20'))}|{fmt((x.get('position120') or 0)*100,1)}%|{fmt(x.get('clv'),3)}|{m['low_time'][11:16] if m else '缺'} / {fmt(m['low_to_close_pct'] if m else None)}%|{sec.get('positive_n','—')}/{sec.get('broad_pool_n','—')}|" )
    body=f"""研究交易日：{T}｜发布时间：北京时间 {completed[:16].replace('T',' ')}（UTC+8）

本轮完成最新已收盘交易日T={T}的沪深量价研究；观察日D={D}。范围仅沪深，北交所不采集也不构成门槛。报告状态：**{'completed' if complete else 'partial/blocked'}**；正式买点0只，本模块只形成盘后量价相对观察，尚未经过最终综合与D日竞价/承接确认。

{chr(10).join(cand)}
最终综合尚未完成，上列不得称最终双标。

### 数据来源、类型、单位与覆盖

- BaoStock：安装SDK后单次登录仍失败 `10002007 网络接收错误`；遵守单连接、不循环重试，未因单源失败停止。
- 腾讯免费收盘批量报价：按上一完整沪深股票分母请求{snap['batch_count']}批，批次错误{len(snap['batch_errors'])}；核验{len(current)}/{snap['coverage']['checked']}（{snap['coverage']['coverage_ratio']:.2%}），日期/时间戳范围{snap['source_timestamp_range'][0]}至{snap['source_timestamp_range'][1]}；未复权OHLC，原生成交量单位手（100股）、归一化为股，成交额取提供者同一记录中的元字段。{len(snap['errors'])}只停牌/字段缺失保留错误。
- 东方财富主域及delay域：一次探测曾返回有效元数据，后续有界重试均HTTP 502，未采用不完整页面，也未据此中止整轮。
- 新浪历史日线：冻结120广池后成功{len(broad)}/120；RV5/10/20为T日成交量相对此前5/10/20个完整交易日均量，**不是盘中量比**。
- 新浪历史5分钟：深筛{len(minutes)}/28只各48根，属于历史五分钟K线，**不是逐笔、盘口或实时成交证明**。
- 新浪日线与腾讯收盘独立交叉：差值不超过0.03元为{independent_close_checks}/120；两源不拼接为一个虚构提供者。
- 板块同步只统计冻结120只活跃广池内同行业正变化比例/中位涨跌，不是全行业精确宽度。

### 沪深广池、深池与全样本逐股验证

冻结120只多结构广池，逐股历史验证后形成28只深池；所有风险结构、失败与数据缺失均保留在压缩证据。成交放大后的价格去向以RV、CLV、位置、突破/回踩、影线及历史五分钟低点至收盘修复共同检验，不能凭K线名称认定资金身份。

|股票|结构|涨跌|换手|RV5/10/20|120日位置|CLV|日内低点/至收盘|同行业正/样本|
|---|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(table)}

### 历史欠项推进：11月20日原冻结28只深池的T+1日线

完整取得{len(prior)}/28只11月23日未复权日线：正价格变化{pos}/{len(prior)}（{prior_summary['positive_price_change_ratio']:.1%}），收盘变化均值{prior_summary['mean_close_pct']:+.3f}%、中位{prior_summary['median_close_pct']:+.3f}%，日线MFE/MAE均值{prior_summary['mean_mfe_pct']:+.3f}%/{prior_summary['mean_mae_pct']:+.3f}%。这是价格观察，不是成交胜率；没有实际成交，真实胜率、净收益与成本后盈亏比均N/A。每只开盘、MFE、MAE、收盘变化已逐条保存，未用日线高低反推触发顺序。

### 结构结论、反例与下一步

- `分歧后承接/再转强代理`要求低点在14:00前、低点至收盘修复≥2%、CLV≥0.70且RV20≥1.2；这是可证伪代理，不是确认买点。
- `高量滞涨/放量下跌风险`保留RV20≥1.5但CLV<0.45或收跌对象；与强收盘组共同留档，避免只挑赢家。
- 假突破判定留到D：若突破20日高后无法守住T日关键位、板块不同步或高开放量不涨，按未触发/失败记录。
- 下一验证：低/中位置高CLV修复组的D日MAE是否小于高量低CLV组；14:40后推进是否仅在板块同步为正时改善T+1价格观察。

### 限制与未完成项

{chr(10).join('- '+x for x in blocked)}

规则版本 `{evidence['rule_version']}`。不保证收益，不自动下单，不自行调权。
"""
    REPORT.write_text(body+"\n",encoding="utf-8")
    hbody=f"""研究交易日：2026-11-20｜补做/发布时间：北京时间 {completed[:16].replace('T',' ')}（UTC+8）

本补充只追加11月20日原冻结28只深池在11月23日的下一交易日日线价格观察，不改写原报告和候选。完整{len(prior)}/28只已核验；正价格变化{pos}/{len(prior)}，均值{prior_summary['mean_close_pct']:+.3f}%、中位{prior_summary['median_close_pct']:+.3f}%，MFE/MAE均值{prior_summary['mean_mfe_pct']:+.3f}%/{prior_summary['mean_mae_pct']:+.3f}%。没有原时点实际成交证据，成交胜率、净收益和盈亏比保持N/A；不从11月23日结果事后挑选11月20日候选。明细见 `{EVIDENCE.relative_to(ROOT)}`。
"""
    HISTORY_REPORT.write_text(hbody+"\n",encoding="utf-8")
    sources=[str(EVIDENCE.relative_to(ROOT)),str(SAMPLES.relative_to(ROOT)),str(SNAP.relative_to(ROOT)),str(STATUS_BAO.relative_to(ROOT)),str(STATUS_TENCENT.relative_to(ROOT)),str(STATUS_EM.relative_to(ROOT)),"https://push2.eastmoney.com/api/qt/clist/get","https://quotes.sina.cn/cn/api/jsonp_v2.php/CN_MarketDataService.getKLineData","https://qt.gtimg.cn/"]
    report={"id":REPORT_ID,"date":T,"market_date":T,"task_id":"volume_price","track":"volume_price","run_id":RUN_ID,"title":f"量价研究｜11月23日沪深{len(current)}只、120广池、28深池与全样本分钟验证","summary":f"沪深{len(current)}/{snap['coverage']['checked']}只OHLCV、120广池、28深池、历史五分钟{len(minutes)}/28；验证上一冻结{len(prior)}/28并形成{len(candidates)}只待综合观察。","body":body,"sources":sources,"report_type":"full_daily_research","eligible_for_integrated_research":complete,"analysis_completed":complete,"status":"completed" if complete else "partial","published_at":completed,"recorded_at":completed,"market_data_cutoff_at":T+"T15:00:00+08:00","planned_entry_date":D,"earliest_legal_exit_date_if_bought":EXIT,"research_rule_version":evidence["rule_version"],"candidate_count":len(candidates),"research_shadow_candidates":candidates,"formal_candidate_count":0,"verified_fill_count":0,"recommendation_ids":[],"evidence_file":str(EVIDENCE.relative_to(ROOT)),"full_scan_count":len(current),"broad_pool_count":120,"broad_pool_verified_count":len(broad),"deep_pool_count":28,"minute_verified_count":len(minutes),"codes":[x["code"] for x in deep],"blocked_modules":[] if complete else blocked}
    hist_report={"id":HISTORY_ID,"date":PREV,"market_date":PREV,"task_id":"volume_price","track":"volume_price","run_id":HISTORY_RUN,"title":"11月20日量价深池下一交易日补充","summary":f"原冻结28只全部追加11月23日日线价格观察；正变化{pos}/28，成交胜率与净收益N/A。","body":hbody,"sources":sources,"report_type":"historical_validation_supplement","eligible_for_integrated_research":False,"analysis_completed":True,"status":"completed","published_at":completed,"recorded_at":completed,"verified_fill_count":0}
    receipt={"id":RECEIPT_ID,"run_id":RUN_ID,"task_id":"volume_price","date":T,"trigger":"scheduled","started_at":started,"recorded_at":completed,"completed_at":completed,"status":"completed" if complete else "blocked","summary":report["summary"],"report_ids":[REPORT_ID],"recommendation_ids":[],"analysis_completed":complete,"eligible_for_integrated_research":complete,"sources":sources,"blocked_modules":[] if complete else blocked}
    hist_receipt={"id":HISTORY_RUN+"-completed","run_id":HISTORY_RUN,"task_id":"volume_price","date":PREV,"trigger":"manual_backfill","started_at":started,"recorded_at":completed,"completed_at":completed,"status":"completed","summary":hist_report["summary"],"report_ids":[HISTORY_ID],"recommendation_ids":[],"analysis_completed":True,"eligible_for_integrated_research":False,"sources":sources}
    bundle={"research":[report,hist_report],"task_runs":[receipt,hist_receipt]}
    out=ROOT/"research_backfills/linked-volume-price-20261123-v1.json"; out.write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"complete":complete,"scan":len(current),"coverage":snap["coverage"],"broad":len(broad),"deep":len(deep),"minutes":len(minutes),"tencent":len(tq),"prior":len(prior),"candidates":[x["code"] for x in candidates],"completed":completed,"em_errors":em["errors"]},ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
